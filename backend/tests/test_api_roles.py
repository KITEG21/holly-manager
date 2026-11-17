"""Login, roles y gestión de tareas y tiempo a través de la API."""

from datetime import date, timedelta

import httpx
import pytest
from sqlalchemy import select

from app.api import dev
from app.core.db import get_session
from app.core.security import create_token, decode_token, hash_password
from app.main import app
from app.models import HistoricalTask, ProjectTask, Role, User
from tests.test_agents import commercial_lead


@pytest.fixture
async def client(session, monkeypatch):
    async def override():
        yield session

    app.dependency_overrides[get_session] = override
    monkeypatch.setattr(dev, "_enqueue_embeddings", lambda: None)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


async def make_user(session, role: Role, email: str, lead_id: int | None = None) -> dict[str, str]:
    user = User(email=email, name=email, role=role, password_hash=hash_password("secret123"), lead_id=lead_id)
    session.add(user)
    await session.commit()
    return {"Authorization": f"Bearer {create_token(user.id, user.role)}"}


def test_token_is_signed_and_expires():
    token = create_token(1, "admin")
    assert decode_token(token)["role"] == "admin"
    payload, sig = token.split(".")
    assert decode_token(payload + "." + sig[:-2] + "xx") is None
    assert decode_token(create_token(1, "admin", ttl_seconds=-1)) is None


async def test_register_creates_client_with_own_conversation(client):
    r = await client.post(
        "/api/auth/register", json={"name": "Ana", "email": "Ana@Acme.io", "password": "secret123"}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["user"]["role"] == "client"
    assert body["user"]["lead_id"]
    headers = {"Authorization": f"Bearer {body['token']}"}
    msgs = await client.get(f"/api/leads/{body['user']['lead_id']}/messages", headers=headers)
    assert msgs.status_code == 200
    assert msgs.json()[0]["content"].startswith("Hi Ana!")

    dup = await client.post(
        "/api/auth/register", json={"name": "x", "email": "ana@acme.io", "password": "secret123"}
    )
    assert dup.status_code == 409


async def test_login_with_wrong_password_fails(client, session):
    await make_user(session, Role.developer, "dev@h.gh")
    ok = await client.post("/api/auth/login", json={"email": "dev@h.gh", "password": "secret123"})
    assert ok.status_code == 200 and ok.json()["user"]["role"] == "developer"
    bad = await client.post("/api/auth/login", json={"email": "dev@h.gh", "password": "nope"})
    assert bad.status_code == 401


async def test_roles_are_enforced(client, session):
    reg = (
        await client.post(
            "/api/auth/register", json={"name": "A", "email": "a@a.io", "password": "secret123"}
        )
    ).json()
    other = (
        await client.post(
            "/api/auth/register", json={"name": "B", "email": "b@b.io", "password": "secret123"}
        )
    ).json()
    client_h = {"Authorization": f"Bearer {reg['token']}"}
    dev_h = await make_user(session, Role.developer, "dev@h.gh")
    admin_h = await make_user(session, Role.admin, "admin@h.gh")

    assert (await client.get("/api/leads", headers=client_h)).status_code == 403
    assert (await client.get("/api/admin/team", headers=dev_h)).status_code == 403
    assert (await client.get("/api/dev/projects", headers=client_h)).status_code == 403
    # Un cliente no puede leer la conversación de otro
    other_lead = other["user"]["lead_id"]
    assert (await client.get(f"/api/leads/{other_lead}/messages", headers=client_h)).status_code == 403
    assert (await client.get(f"/api/leads/{other_lead}/messages", headers=admin_h)).status_code == 200
    assert (await client.get("/api/admin/team", headers=admin_h)).status_code == 200
    assert (await client.get("/api/dev/projects", headers=dev_h)).status_code == 200
    assert (await client.get("/api/leads")).status_code == 401


async def test_developer_logs_time_and_project_is_reestimated(client, session, llm):
    lead = await commercial_lead(session, llm)
    dev_h = await make_user(session, Role.developer, "dev@h.gh")

    projects = (await client.get("/api/dev/projects", headers=dev_h)).json()
    assert [p["lead_id"] for p in projects] == [lead.id]
    detail = (await client.get(f"/api/dev/projects/{lead.id}", headers=dev_h)).json()
    tasks = {t["key"]: t for s in detail["sprints"] for t in s["tasks"]}
    assert set(tasks) == {"T1", "T2", "T3", "T4"}
    assert tasks["T1"]["story"].startswith("Como paciente")
    assert tasks["T2"]["blocked_by"] == ["T1"]

    # No se puede empezar una tarea con dependencias pendientes
    r = await client.post(f"/api/dev/tasks/{tasks['T2']['id']}/time", json={"hours": 2}, headers=dev_h)
    assert r.status_code == 409

    # Ni cerrarla sin horas
    r = await client.patch(f"/api/dev/tasks/{tasks['T1']['id']}", json={"status": "done"}, headers=dev_h)
    assert r.status_code == 422

    # T1 cuesta el doble de lo planificado
    planned = tasks["T1"]["planned_hours"]
    # Dos días de trabajo: como mucho se imputan 24 h por persona y día
    for day in [date.today() - timedelta(days=1), date.today()]:
        r = await client.post(
            f"/api/dev/tasks/{tasks['T1']['id']}/time",
            json={"hours": planned, "work_date": str(day)},
            headers=dev_h,
        )
        assert r.status_code == 200 and r.json()["task"]["status"] == "in_progress"
    r = await client.patch(f"/api/dev/tasks/{tasks['T1']['id']}", json={"status": "done"}, headers=dev_h)
    change = r.json()
    assert change["forecast"]["performance_ratio"] == 2
    assert change["forecast"]["alert"] is True

    # La tarea cerrada entra en el histórico para estimar los próximos proyectos
    row = await session.scalar(
        select(HistoricalTask).where(HistoricalTask.source_task_id == tasks["T1"]["id"])
    )
    assert row.actual_hours == pytest.approx(planned * 2)

    # T2 ya no está bloqueada
    detail = (await client.get(f"/api/dev/projects/{lead.id}", headers=dev_h)).json()
    t2 = next(t for s in detail["sprints"] for t in s["tasks"] if t["key"] == "T2")
    assert t2["blocked_by"] == []

    entries = (await client.get(f"/api/dev/tasks/{tasks['T1']['id']}/time", headers=dev_h)).json()
    assert entries[0]["user"] == "dev@h.gh"

    # Reabrirla la saca del histórico
    await client.patch(f"/api/dev/tasks/{tasks['T1']['id']}", json={"status": "in_progress"}, headers=dev_h)
    assert not await session.scalar(select(HistoricalTask).where(HistoricalTask.source_task_id.is_not(None)))
    assert await session.scalar(select(ProjectTask.status).where(ProjectTask.key == "T1")) == "in_progress"


async def test_timesheet_dashboard_reports_and_assignment(client, session, llm):
    lead = await commercial_lead(session, llm)
    dev_h = await make_user(session, Role.developer, "dev@h.gh")
    other_h = await make_user(session, Role.developer, "otro@h.gh")
    detail = (await client.get(f"/api/dev/projects/{lead.id}", headers=dev_h)).json()
    t1 = next(t for s in detail["sprints"] for t in s["tasks"] if t["key"] == "T1")

    team = (await client.get("/api/dev/team", headers=dev_h)).json()
    other_id = next(m["id"] for m in team if m["name"] == "otro@h.gh")
    r = await client.post(f"/api/dev/tasks/{t1['id']}/assign", json={"user_id": other_id}, headers=dev_h)
    assert r.json()["task"]["assignee"] == "otro@h.gh"
    mine = (await client.get("/api/dev/tasks?mine=true", headers=other_h)).json()
    assert [t["key"] for t in mine] == ["T1"]

    today = date.today()
    yesterday = today - timedelta(days=1)
    await client.post(
        f"/api/dev/tasks/{t1['id']}/time", json={"hours": 3, "work_date": str(yesterday)}, headers=dev_h
    )
    await client.post(f"/api/dev/tasks/{t1['id']}/time", json={"hours": 2}, headers=dev_h)

    future = await client.post(
        f"/api/dev/tasks/{t1['id']}/time",
        json={"hours": 1, "work_date": str(today + timedelta(days=1))},
        headers=dev_h,
    )
    assert future.status_code == 422
    too_much = await client.post(f"/api/dev/tasks/{t1['id']}/time", json={"hours": 23}, headers=dev_h)
    assert too_much.status_code == 422  # 2 h ya imputadas hoy + 23 > 24

    sheet = (await client.get(f"/api/dev/timesheet?week_start={today}", headers=dev_h)).json()
    assert sheet["total"] == 5
    row = sheet["rows"][0]
    assert row["key"] == "T1" and row["hours"][today.weekday()] == 2
    if yesterday >= date.fromisoformat(sheet["week_start"]):
        assert row["hours"][yesterday.weekday()] == 3

    dash = (await client.get("/api/dev/dashboard", headers=dev_h)).json()
    assert dash["today_hours"] == 2
    assert dash["activity"][0]["user"] == "dev@h.gh"
    assert dash["projects"][0]["lead_id"] == lead.id

    # Solo el autor puede borrar su imputación; al borrarla bajan las horas reales
    entry_id = sheet["entries"][0]["id"]
    assert (await client.delete(f"/api/dev/time/{entry_id}", headers=other_h)).status_code == 403
    r = await client.delete(f"/api/dev/time/{entry_id}", headers=dev_h)
    assert r.json()["task"]["actual_hours"] == 3

    await client.patch(f"/api/dev/tasks/{t1['id']}", json={"status": "done"}, headers=dev_h)
    rep = (await client.get("/api/dev/reports", headers=dev_h)).json()
    acc = next(a for a in rep["accuracy_by_type"] if a["task_type"] == "backend")
    assert acc["tasks"] == 1 and acc["actual_hours"] == 3
    assert sum(w["hours"] for w in rep["weekly_hours"]) == 3
    assert rep["projects"][0]["forecast"]["done_tasks"] == 1
