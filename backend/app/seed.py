"""Datos de ejemplo: configuración, proyectos históricos y documentos. `python -m app.seed`"""

import asyncio
import shutil
import uuid
from pathlib import Path

from sqlalchemy import delete, func, select

from app.core.config import get_settings
from app.core.db import task_session
from app.core.security import hash_password
from app.models import Document, HistoricalTask, QualificationCriterion, Role, TaskType, User
from app.repo import put_setting
from app.schemas.config import CommercialRules, Complexity, QualificationThresholds, TeamConfig
from app.schemas.qualification import CriterionKey

TASK_TYPES = [
    ("backend", 6, 24, Complexity.medium),
    ("frontend", 4, 20, Complexity.medium),
    ("integration", 8, 32, Complexity.high),
    ("qa", 2, 8, Complexity.low),
    ("devops", 4, 16, Complexity.medium),
    ("design", 4, 16, Complexity.low),
]

CRITERIA = [
    (CriterionKey.need_clarity, "What would you like to build, and what problem does it solve?", 15),
    (CriterionKey.company, "Which company do you work for?", 10),
    (
        CriterionKey.decision_maker,
        "Are you the one who decides on hiring us, or are other people involved?",
        20,
    ),
    (CriterionKey.budget, "Do you have an approximate budget in mind?", 30),
    (CriterionKey.timeline, "When would you need it by?", 15),
    (CriterionKey.corporate_email, "Could you leave me a contact email?", 10),
]

# (proyecto, título, tipo, estimadas, reales)
HISTORICAL = [
    ("Dental Clinic Bookings", "Appointment data model and REST API", "backend", 16, 19),
    ("Dental Clinic Bookings", "Email and password authentication", "backend", 10, 12),
    ("Dental Clinic Bookings", "Availability calendar in React", "frontend", 14, 18),
    ("Dental Clinic Bookings", "SMS reminders with Twilio", "integration", 12, 15),
    ("Dental Clinic Bookings", "End-to-end tests for the booking flow", "qa", 6, 5),
    ("Dental Clinic Bookings", "CI/CD pipeline and deployment to AWS", "devops", 10, 9),
    ("Handmade Goods Marketplace", "Product catalogue with filters and search", "backend", 18, 22),
    ("Handmade Goods Marketplace", "Stripe payment gateway", "integration", 20, 26),
    ("Handmade Goods Marketplace", "Cart and checkout", "frontend", 16, 17),
    ("Handmade Goods Marketplace", "Seller dashboard to manage products", "frontend", 18, 21),
    ("Handmade Goods Marketplace", "UI design and component system", "design", 12, 14),
    ("Handmade Goods Marketplace", "Google social login", "backend", 6, 8),
    ("Handmade Goods Marketplace", "Payment and webhook tests", "qa", 5, 7),
    ("Logistics App", "Real-time shipment tracking with websockets", "backend", 20, 24),
    ("Logistics App", "Carrier API integration", "integration", 24, 31),
    ("Logistics App", "Route map in the web dashboard", "frontend", 12, 13),
    ("Logistics App", "Push notifications", "integration", 10, 9),
    ("Logistics App", "Infrastructure with Docker and Kubernetes", "devops", 14, 18),
    ("Logistics App", "Load testing", "qa", 6, 6),
    ("HR Portal", "User, role and permission management", "backend", 14, 16),
    ("HR Portal", "Payroll import from Excel", "backend", 10, 14),
    ("HR Portal", "Absence dashboard with charts", "frontend", 12, 12),
    ("HR Portal", "SSO integration with Microsoft Entra", "integration", 14, 20),
    ("HR Portal", "Wireframes and clickable prototype", "design", 10, 9),
    ("HR Portal", "Report export to PDF", "backend", 8, 9),
    ("HR Portal", "WCAG AA accessibility in forms", "frontend", 8, 11),
]

SEED_DOCS = Path(__file__).parent.parent / "seed_docs"

# Cuentas internas de ejemplo (los clientes se registran desde la web). Cambia las contraseñas fuera de local.
TEAM_USERS = [
    ("admin@holly.app", "Laura Admin", Role.admin, "admin1234"),
    ("dev@holly.app", "Marco Dev", Role.developer, "dev12345"),
]


async def seed() -> None:
    from app.tasks.ingest import embed_historical_task, ingest_document_task, sync_builtin_docs_task

    async with task_session() as session:
        await session.execute(delete(TaskType))
        session.add_all(
            TaskType(name=n, min_hours=lo, max_hours=hi, complexity=c) for n, lo, hi, c in TASK_TYPES
        )
        await session.execute(delete(QualificationCriterion))
        session.add_all(QualificationCriterion(key=k, question=q, weight=w) for k, q, w in CRITERIA)
        await put_setting(session, "team", TeamConfig())
        await put_setting(session, "commercial", CommercialRules())
        await put_setting(session, "qualification", QualificationThresholds())

        if not await session.scalar(select(func.count(HistoricalTask.id))):
            session.add_all(
                HistoricalTask(project=p, title=t, task_type=k, estimated_hours=e, actual_hours=a)
                for p, t, k, e, a in HISTORICAL
            )

        for email, name, role, password in TEAM_USERS:
            if not await session.scalar(select(User.id).where(User.email == email)):
                session.add(User(email=email, name=name, role=role, password_hash=hash_password(password)))

        new_docs = []
        folder = get_settings().storage_dir / "documents"
        folder.mkdir(parents=True, exist_ok=True)
        for path, kind in [
            (SEED_DOCS / "contract_template.md", "contract"),
            (SEED_DOCS / "policies.md", "policy"),
        ]:
            exists = await session.scalar(select(Document.id).where(Document.filename == path.name))
            if exists:
                continue
            target = folder / f"{uuid.uuid4().hex}{path.suffix}"
            shutil.copy(path, target)
            doc = Document(filename=path.name, kind=kind, path=str(target))
            session.add(doc)
            new_docs.append(doc)
        await session.commit()

        embed_historical_task.delay()
        sync_builtin_docs_task.delay()
        for doc in new_docs:
            ingest_document_task.delay(doc.id)
    print(
        f"Seed OK: {len(TASK_TYPES)} task types, {len(HISTORICAL)} historical tasks, {len(new_docs)} documents queued"
    )
    for email, _, role, password in TEAM_USERS:
        print(f"  {role}: {email} / {password}")


if __name__ == "__main__":
    asyncio.run(seed())
