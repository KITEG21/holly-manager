import json
from decimal import Decimal

import pytest
from sqlalchemy import select, update
from sqlalchemy.exc import DBAPIError

from app.agents.commercial import SAFE_REPLY
from app.agents.router import handle_message
from app.core.llm import LLMResponse
from app.models import (
    Document,
    DocumentChunk,
    Escalation,
    Estimate,
    HistoricalTask,
    Lead,
    Message,
    Offer,
    QualificationCriterion,
    RequirementDraft,
    RequirementVersion,
    Stage,
    TaskType,
)
from app.repo import put_setting
from app.schemas.config import CommercialRules, QualificationThresholds, TeamConfig
from app.schemas.estimation import Decomposition, EstimateResult, TaskDraft
from app.schemas.qualification import CriterionKey, Evidence, QualificationEvidence
from app.schemas.requirements import RequirementDoc
from app.tasks.estimation import run_estimation
from tests.conftest import fake_vector


async def seed_config(session) -> None:
    session.add_all(
        [
            TaskType(name="backend", min_hours=8, max_hours=24, complexity="medium"),
            TaskType(name="frontend", min_hours=6, max_hours=20, complexity="medium"),
            TaskType(name="qa", min_hours=2, max_hours=6, complexity="low"),
        ]
    )
    session.add_all(
        QualificationCriterion(key=k, question=f"¿Pregunta {k}?", weight=w)
        for k, w in [(CriterionKey.budget, 50), (CriterionKey.decision_maker, 30), (CriterionKey.company, 20)]
    )
    await put_setting(session, "team", TeamConfig(capacity_hours_per_sprint=100, velocity_factor=1))
    await put_setting(session, "commercial", CommercialRules(min_price=Decimal("1000")))
    await put_setting(session, "qualification", QualificationThresholds())
    await session.commit()


async def new_lead(session, stage: Stage = Stage.qualification) -> Lead:
    lead = Lead(name="Ana", email="ana@acme.io", stage=stage)
    session.add(lead)
    await session.commit()
    return lead


# --- Cualificación ------------------------------------------------------------------------------


async def test_qualification_asks_for_missing_criterion(session, llm):
    await seed_config(session)
    lead = await new_lead(session)
    llm.structured_handlers[QualificationEvidence] = lambda _: QualificationEvidence(
        company_name=Evidence(value="Acme", quote="trabajo en Acme")
    )
    llm.say("¡Genial, Acme! ¿Tienes un presupuesto aproximado?")

    msg = await handle_message(session, llm, lead, "Hola, trabajo en Acme")

    assert lead.stage == Stage.qualification
    assert lead.qualification_status == "pending"
    assert "presupuesto" in msg.content
    # La pregunta que se le pide redactar al LLM es la configurada para el primer criterio que falta
    assert "¿Pregunta budget?" in llm.chat_calls[0][0]["content"]


async def test_qualified_lead_moves_to_requirements_with_explanation(session, llm):
    await seed_config(session)
    lead = await new_lead(session)
    llm.structured_handlers[QualificationEvidence] = lambda _: QualificationEvidence(
        budget_eur=Evidence(value=30000, quote="unos 30k"),
        is_decision_maker=Evidence(value=True, quote="decido yo"),
        company_name=Evidence(value="Acme"),
    )

    await handle_message(session, llm, lead, "Decido yo, tenemos unos 30k")

    assert lead.stage == Stage.requirements
    assert lead.qualification_score == 100
    assert lead.qualification_detail["explanation"].startswith("Score 100 because")


async def test_qualification_reply_with_prices_is_replaced(session, llm):
    await seed_config(session)
    lead = await new_lead(session)
    llm.structured_handlers[QualificationEvidence] = lambda _: QualificationEvidence()
    llm.say("Normalmente cobramos 5.000 € por proyectos así. ¿Presupuesto?")

    msg = await handle_message(session, llm, lead, "hola")

    assert msg.content == "¿Pregunta budget?"
    assert msg.meta["violations"][0]["code"] == "UNVALIDATED_NUMBER"


# --- Requisitos ---------------------------------------------------------------------------------


async def test_requirements_agent_builds_document_and_validates_summary(session, llm):
    lead = await new_lead(session, Stage.requirements)
    llm.call("upsert_epic", id="E-1", title="Reservas")
    llm.call(
        "upsert_story",
        id="US-1",
        epic_id="E-1",
        as_a="paciente",
        i_want="reservar cita",
        acceptance_criteria=["Recibe confirmación por email"],
        source_message_ids=[1],
    )
    llm.call("flag_ambiguity", question="¿Pago online o en clínica?")
    llm.call("propose_summary", summary="App de reservas")  # rechazado: hay ambigüedad abierta
    llm.say("¿El pago será online o en la clínica?")

    await handle_message(session, llm, lead, "Quiero que los pacientes reserven cita")

    doc = RequirementDoc.model_validate((await session.get(RequirementDraft, lead.id)).doc)
    assert [s.id for s in doc.stories] == ["US-1"]
    assert doc.stories[0].source_message_ids == [1]
    assert doc.summary is None
    assert doc.readiness_problems() == [
        "There is 1 open ambiguity.",
        "The summary for the client is missing.",
    ]
    # El resultado de propose_summary devuelto al modelo explica por qué no se acepta
    tool_results = [m for m in llm.chat_calls[-1] if m["role"] == "tool"]
    assert '"accepted": false' in tool_results[-1]["content"]


async def test_story_with_unknown_epic_is_rejected(session, llm):
    lead = await new_lead(session, Stage.requirements)
    llm.call("upsert_story", id="US-1", epic_id="E-9", as_a="x", i_want="y")
    llm.say("ok")
    await handle_message(session, llm, lead, "algo")
    doc = RequirementDoc.model_validate((await session.get(RequirementDraft, lead.id)).doc)
    assert doc.stories == []


# --- Estimación ---------------------------------------------------------------------------------

DOC = RequirementDoc.model_validate(
    {
        "epics": [{"id": "E-1", "title": "Reservas"}],
        "stories": [
            {
                "id": "US-1",
                "epic_id": "E-1",
                "as_a": "paciente",
                "i_want": "reservar",
                "acceptance_criteria": ["ok"],
            },
            {
                "id": "US-2",
                "epic_id": "E-1",
                "as_a": "admin",
                "i_want": "ver agenda",
                "acceptance_criteria": ["ok"],
            },
        ],
        "out_of_scope": ["App móvil nativa"],
        "summary": "Sistema de reservas",
    }
)

DECOMPOSITION = Decomposition(
    tasks=[
        TaskDraft(id="T1", story_id="US-1", title="API de citas", task_type="backend"),
        TaskDraft(
            id="T2", story_id="US-1", title="Formulario de reserva", task_type="frontend", depends_on=["T1"]
        ),
        TaskDraft(id="T3", story_id="US-2", title="Vista de agenda", task_type="frontend", depends_on=["T1"]),
        TaskDraft(
            id="T4", story_id="US-2", title="Tests de reserva", task_type="qa", depends_on=["T2", "T3"]
        ),
    ]
)


async def commercial_lead(session, llm) -> Lead:
    """Cliente con requisitos confirmados y estimación terminada."""
    await seed_config(session)
    session.add(
        HistoricalTask(
            project="Dental",
            title="API de citas",
            task_type="backend",
            actual_hours=12,
            embedding=fake_vector("API de citas"),
        )
    )
    lead = await new_lead(session, Stage.estimating)
    version = RequirementVersion(lead_id=lead.id, version=1, doc=DOC.model_dump(mode="json"), sha256="x" * 64)
    session.add(version)
    await session.flush()
    est = Estimate(lead_id=lead.id, requirement_version_id=version.id)
    session.add(est)
    await session.commit()
    llm.structured_handlers[Decomposition] = lambda _: DECOMPOSITION
    await run_estimation(session, llm, est.id)
    return lead


async def test_estimation_is_computed_by_code_and_uses_history(session, llm):
    lead = await commercial_lead(session, llm)
    est = await session.scalar(select(Estimate).where(Estimate.lead_id == lead.id))
    result = EstimateResult.model_validate(est.result)

    assert est.status == "done"
    assert lead.stage == Stage.commercial
    t1 = next(t for t in result.tasks if t.task.id == "T1")
    assert t1.likely == 12 and t1.historical_refs[0].project == "Dental"
    # Precio = horas comprometidas * tarifa (o mínimo)
    assert result.quote.list_price == max(
        (Decimal(str(result.totals.committed_hours)) * 55).quantize(Decimal("0.01")), Decimal("1000.00")
    )
    sprint_of = {tid: s.number for s in result.sprints for tid in s.task_ids}
    assert sprint_of["T4"] >= max(sprint_of["T2"], sprint_of["T3"])
    last = await session.scalar(select(Message).where(Message.lead_id == lead.id).order_by(Message.id.desc()))
    assert "weeks" in last.content and "€" in last.content


async def test_invalid_decomposition_is_retried_then_fails_to_human(session, llm):
    await seed_config(session)
    lead = await new_lead(session, Stage.estimating)
    version = RequirementVersion(lead_id=lead.id, version=1, doc=DOC.model_dump(mode="json"), sha256="x" * 64)
    session.add(version)
    await session.flush()
    est = Estimate(lead_id=lead.id, requirement_version_id=version.id)
    session.add(est)
    await session.commit()
    llm.structured_handlers[Decomposition] = lambda _: Decomposition(
        tasks=[TaskDraft(id="T1", story_id="US-1", title="x", task_type="blockchain")]
    )
    with pytest.raises(ValueError, match="not valid"):
        await run_estimation(session, llm, est.id)
    assert est.status == "failed"
    assert await session.scalar(select(Escalation).where(Escalation.lead_id == lead.id))


# --- Comercial ----------------------------------------------------------------------------------


async def test_discount_within_limits_is_offered(session, llm):
    lead = await commercial_lead(session, llm)
    llm.call("propose_offer", discount_pct="5")

    def final(messages):
        # El modelo solo repite el precio que le devuelve la herramienta
        result = json.loads(next(m for m in reversed(messages) if m["role"] == "tool")["content"])
        assert result["status"] == "ok"
        return LLMResponse(
            content=f"Te puedo aplicar un 5% de descuento: quedaría en {result['offer']['price']} €."
        )

    llm.chat_script.append(final)
    msg = await handle_message(session, llm, lead, "¿Me haces un 5% de descuento?")

    assert "5%" in msg.content
    assert msg.meta["violations"] == []
    assert await session.scalar(select(Offer.valid).where(Offer.lead_id == lead.id))
    assert not await session.scalar(select(Escalation).where(Escalation.lead_id == lead.id))


async def test_discount_above_max_escalates_and_agent_cannot_say_yes(session, llm):
    """El escenario del cliente difícil: pide 30% y el modelo intenta aceptarlo dos veces."""
    lead = await commercial_lead(session, llm)
    llm.call("propose_offer", discount_pct="30")
    llm.say("¡Hecho! Te dejo el proyecto con un 30% de descuento, en 9.999 €.")
    llm.say("Vale, entonces 9.999 € con el 30% de descuento.")

    msg = await handle_message(session, llm, lead, "Quiero un 30% de descuento o me voy")

    assert msg.content == SAFE_REPLY
    esc = await session.scalar(select(Escalation).where(Escalation.lead_id == lead.id))
    assert esc.violations[0]["code"] == "DISCOUNT_EXCEEDS_MAX"
    assert esc.client_request == "Quiero un 30% de descuento o me voy"
    offer = await session.scalar(select(Offer).where(Offer.lead_id == lead.id))
    assert offer.valid is False
    assert any(v["code"] == "UNVALIDATED_NUMBER" for v in msg.meta["violations"])


async def test_escalated_reply_may_echo_client_request(session, llm):
    lead = await commercial_lead(session, llm)
    llm.call("propose_offer", discount_pct="30")
    llm.say("Has pedido un 30% de descuento; no puedo aceptarlo yo, lo consulto con el equipo.")

    msg = await handle_message(session, llm, lead, "Quiero un 30% de descuento")

    assert "lo consulto" in msg.content
    assert msg.meta["violations"] != []  # la oferta inválida queda registrada
    assert all(v["code"] != "UNVALIDATED_NUMBER" for v in msg.meta["violations"])


async def test_invented_number_without_tool_is_regenerated(session, llm):
    lead = await commercial_lead(session, llm)
    llm.say("Podemos hacerlo en 4 semanas.")
    llm.say("Lo revisamos y te confirmo el plazo exacto con el equipo.")

    msg = await handle_message(session, llm, lead, "¿Podéis hacerlo en 4 semanas?")

    assert msg.content == "Lo revisamos y te confirmo el plazo exacto con el equipo."
    assert msg.meta["violations"][0]["code"] == "UNVALIDATED_NUMBER"
    # El segundo intento recibe el motivo del bloqueo
    assert "blocked" in llm.chat_calls[-1][-1]["content"]


async def test_contract_answers_must_cite(session, llm):
    lead = await commercial_lead(session, llm)
    doc = Document(filename="contrato.md", kind="contract", path="contrato.md", status="ready")
    session.add(doc)
    await session.flush()
    session.add(
        DocumentChunk(
            document_id=doc.id,
            kind="contract",
            content="Las facturas se abonan en 30 días.",
            meta={"source": "contrato.md", "section": "2. Precio"},
            embedding=fake_vector("pago"),
        )
    )
    await session.commit()
    llm.call("search_contract", query="plazo de pago")
    llm.say("Las facturas se pagan a 30 días.")  # sin cita → bloqueada
    llm.say("Las facturas se pagan en un plazo máximo de 30 días desde su emisión [C1].")

    msg = await handle_message(session, llm, lead, "¿En cuánto tiempo hay que pagar?")

    assert msg.content.endswith("[C1].")
    assert msg.meta["citations"][0]["label"] == "contrato.md · § 2. Precio"
    assert msg.meta["violations"][0]["code"] == "MISSING_CITATION"


async def test_confirmed_requirements_are_immutable(session, llm):
    lead = await new_lead(session)
    session.add(RequirementVersion(lead_id=lead.id, version=1, doc={}, sha256="x" * 64))
    await session.commit()
    with pytest.raises(DBAPIError, match="inmutable"):
        await session.execute(update(RequirementVersion).values(doc={"hacked": True}))
