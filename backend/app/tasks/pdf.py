"""Borrador de propuesta y contrato en PDF (Jinja2 + WeasyPrint)."""

import asyncio
from datetime import date
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import task_session
from app.domain.summary import format_money
from app.models import DocumentChunk, Lead, Offer, Proposal, RequirementVersion
from app.models import Estimate as EstimateRow
from app.schemas.commercial import CommercialOffer
from app.schemas.requirements import RequirementDoc
from app.worker import celery_app

TEMPLATES = Environment(
    loader=FileSystemLoader(Path(__file__).parent.parent / "templates"), autoescape=select_autoescape()
)
TEMPLATES.filters["money"] = format_money


async def render_html(session, proposal: Proposal) -> str:
    offer_row = await session.get(Offer, proposal.offer_id)
    estimate = await session.get(EstimateRow, offer_row.estimate_id)
    version = await session.get(RequirementVersion, estimate.requirement_version_id)
    lead = await session.get(Lead, proposal.lead_id)
    contract = (
        await session.scalars(
            select(DocumentChunk).where(DocumentChunk.kind == "contract").order_by(DocumentChunk.id)
        )
    ).all()
    return TEMPLATES.get_template("proposal.html").render(
        lead=lead,
        offer=CommercialOffer.model_validate(offer_row.terms),
        doc=RequirementDoc.model_validate(version.doc),
        version=version,
        contract=contract,
        company=get_settings().company_name,
        today=date.today(),
    )


@celery_app.task(name="render_proposal_pdf")
def render_proposal_pdf(proposal_id: int) -> str | None:
    async def _run() -> str | None:
        async with task_session() as session:
            proposal = await session.get(Proposal, proposal_id)
            try:
                from weasyprint import HTML

                html = await render_html(session, proposal)
                out = get_settings().storage_dir / "proposals" / f"proposal-{proposal.id}.pdf"
                out.parent.mkdir(parents=True, exist_ok=True)
                HTML(string=html).write_pdf(out)
                proposal.status, proposal.pdf_path = "ready", str(out)
            except Exception as e:  # noqa: BLE001
                proposal.status, proposal.error = "failed", str(e)[:2000]
            await session.commit()
            return proposal.pdf_path

    return asyncio.run(_run())
