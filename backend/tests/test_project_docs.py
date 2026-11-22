"""Per-project documentation: the generated business agreement, team pages and the project-scoped assistant."""

from sqlalchemy import select

from app.agents.docs_assistant import answer_question
from app.api import project_docs as project_docs_api
from app.models import Document, DocumentChunk, Lead, RequirementVersion, Role, Stage
from app.rag.guides import index_guide, sync_builtin
from app.rag.project_docs import AGREEMENT, PROJECT, agreement_markdown, ensure_agreement
from app.schemas.requirements import RequirementDoc
from tests.test_api_roles import client, make_user  # noqa: F401  (fixture)

DOC = RequirementDoc.model_validate(
    {
        "epics": [{"id": "E-1", "title": "Bookings", "description": "Online appointments"}],
        "stories": [
            {
                "id": "US-1",
                "epic_id": "E-1",
                "as_a": "patient",
                "i_want": "to cancel an appointment",
                "so_that": "the slot is freed",
                "acceptance_criteria": ["Cancellation is allowed up to 24 hours before"],
            }
        ],
        "nfrs": [{"id": "NFR-1", "category": "legal", "text": "GDPR compliant"}],
        "out_of_scope": ["Native mobile app"],
        "ambiguities": [
            {
                "id": "A-1",
                "question": "Is payment online?",
                "status": "resolved",
                "resolution": "No, at the clinic.",
            },
            {"id": "A-2", "question": "Unanswered?", "status": "open"},
        ],
        "summary": "Booking system for clinics.",
    }
)


async def project(session, name: str = "Acme Health", doc: RequirementDoc = DOC, version: int = 1) -> Lead:
    lead = Lead(name=name, email=f"{name.split()[0].lower()}@x.io", stage=Stage.commercial)
    session.add(lead)
    await session.flush()
    session.add(
        RequirementVersion(lead_id=lead.id, version=version, doc=doc.model_dump(mode="json"), sha256="a" * 64)
    )
    await session.commit()
    return lead


async def test_agreement_page_contains_the_business_logic(session):
    lead = await project(session)
    version = await session.scalar(select(RequirementVersion).where(RequirementVersion.lead_id == lead.id))
    md = agreement_markdown(DOC, version, lead.name)

    assert md.startswith("# Business agreement: Acme Health")
    assert "requirements version 1" in md
    assert "### US-1" in md and "so that the slot is freed" in md
    assert "- Cancellation is allowed up to 24 hours before" in md
    assert "| NFR-1 | legal | GDPR compliant |" in md
    assert "- Native mobile app" in md
    # Resolved questions become decisions; open ones are not business logic yet
    assert "**Is payment online?** No, at the clinic." in md
    assert "Unanswered?" not in md


async def test_agreement_is_created_once_and_refreshed_on_new_versions(session, llm):
    lead = await project(session)
    doc = await ensure_agreement(session, lead.id)
    assert doc.source == AGREEMENT and doc.kind == PROJECT and doc.lead_id == lead.id
    await index_guide(session, llm, doc)
    await session.commit()
    assert await ensure_agreement(session, lead.id) is None  # unchanged → nothing to do

    v2 = DOC.model_copy(update={"out_of_scope": ["Native mobile app", "Payments"]})
    session.add(
        RequirementVersion(lead_id=lead.id, version=2, doc=v2.model_dump(mode="json"), sha256="b" * 64)
    )
    await session.commit()
    updated = await ensure_agreement(session, lead.id)
    assert (
        updated.id == doc.id
        and "requirements version 2" in updated.content
        and "- Payments" in updated.content
    )


async def test_assistant_only_uses_the_projects_own_docs(session, llm, tmp_path):
    other = DOC.model_copy(update={"out_of_scope": ["Loyalty points programme"], "summary": "Retail store."})
    a, b = await project(session, "Acme Health"), await project(session, "Globex Retail", doc=other)
    for lead in (a, b):
        await index_guide(session, llm, await ensure_agreement(session, lead.id))
    (tmp_path / "01-guide.md").write_text("# Guide\n\n## Rules\n\nSystem rule.\n", encoding="utf-8")
    await sync_builtin(session, llm, tmp_path)
    await session.commit()

    llm.say("Payment happens at the clinic [C1].")
    ans = await answer_question(
        session, llm, "Is payment online?", [], kinds=(PROJECT,), lead_id=a.id, scope="x"
    )

    excerpts = llm.chat_calls[0][0]["content"]
    assert "Native mobile app" in excerpts or "Booking system" in excerpts
    assert (
        "Loyalty points" not in excerpts and "Retail store" not in excerpts and "System rule" not in excerpts
    )
    assert ans.grounded
    doc_ids = {d.id for d in (await session.scalars(select(Document).where(Document.lead_id == a.id))).all()}
    assert {c.document_id for c in ans.citations} <= doc_ids


async def test_project_docs_api(client, session, llm, monkeypatch):  # noqa: F811
    lead = await project(session)
    enqueued = []
    monkeypatch.setattr(project_docs_api, "_enqueue_agreement", lambda lead_id: enqueued.append(lead_id))
    monkeypatch.setattr(project_docs_api, "get_llm", lambda: llm)
    dev_h = await make_user(session, Role.developer, "dev@h.gh")
    reg = await client.post(
        "/api/auth/register", json={"name": "C", "email": "c@c.io", "password": "secret123"}
    )
    client_h = {"Authorization": f"Bearer {reg.json()['token']}"}
    base = f"/api/projects/{lead.id}/docs"

    assert (await client.get(base, headers=client_h)).status_code == 403
    assert (
        await client.get(f"/api/projects/{reg.json()['user']['lead_id']}/docs", headers=dev_h)
    ).status_code == 404

    # First visit creates the agreement page and queues its indexing
    docs = (await client.get(base, headers=dev_h)).json()
    assert [d["source"] for d in docs] == ["agreement"] and enqueued == [lead.id]
    agreement_id = docs[0]["id"]

    page = {
        "title": "Cancellation rules",
        "content": "# Cancellation rules\n\n## Late cancellations\n\nCount as no-shows.",
    }
    created = (await client.post(base, json=page, headers=dev_h)).json()
    assert created["source"] == "page" and created["status"] == "ready" and created["chunk_count"] == 1

    edited = await client.put(
        f"{base}/{created['id']}",
        json={**page, "content": page["content"] + "\n\nThree no-shows block the account."},
        headers=dev_h,
    )
    assert edited.status_code == 200 and "Three no-shows" in edited.json()["content"]
    chunks = (
        await session.scalars(select(DocumentChunk).where(DocumentChunk.document_id == created["id"]))
    ).all()
    assert any("Three no-shows" in c.content for c in chunks)

    assert (await client.put(f"{base}/{agreement_id}", json=page, headers=dev_h)).status_code == 409
    assert (await client.delete(f"{base}/{agreement_id}", headers=dev_h)).status_code == 409

    # Project pages never show up in the system documentation
    assert all(
        d["id"] not in (agreement_id, created["id"])
        for d in (await client.get("/api/docs", headers=dev_h)).json()
    )

    llm.say("Late cancellations count as no-shows [C1].")
    ans = (
        await client.post(f"{base}/ask", json={"question": "What about late cancellations?"}, headers=dev_h)
    ).json()
    assert ans["grounded"] and ans["citations"][0]["document_id"] == created["id"]
    assert 'the project "Acme Health"' in llm.chat_calls[-1][0]["content"]

    assert (await client.delete(f"{base}/{created['id']}", headers=dev_h)).status_code == 200
    assert [d["source"] for d in (await client.get(base, headers=dev_h)).json()] == ["agreement"]
