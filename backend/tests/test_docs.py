"""Documentation: Markdown chunking, built-in sync, the grounded assistant and the API permissions."""

from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.agents.docs_assistant import (
    NOT_FOUND,
    NOT_FOUND_REPLY,
    UNGROUNDED_REPLY,
    Turn,
    answer_question,
    retrieval_query,
)
from app.api import docs as docs_api
from app.core.config import get_settings
from app.models import Document, DocumentChunk, Role
from app.rag.guides import sync_builtin
from app.rag.markdown import chunk_markdown, title_of
from tests.test_api_roles import client, make_user  # noqa: F401  (fixture)

GUIDE_MD = """# Estimation

Intro paragraph.

## Step 1: breakdown

The model breaks stories into tasks.

### Validation

Unknown types are rejected.

## Step 2: price

Price = committed hours x hourly rate.
"""


def test_markdown_chunks_keep_the_heading_path():
    chunks = chunk_markdown(GUIDE_MD, "Estimation")
    assert [c.section for c in chunks] == [
        None,
        "Step 1: breakdown",
        "Step 1: breakdown > Validation",
        "Step 2: price",
    ]
    assert chunks[2].text.startswith("Estimation > Step 1: breakdown > Validation")
    assert title_of(GUIDE_MD, "x") == "Estimation"


def test_long_sections_are_split_and_code_blocks_kept_whole():
    body = "\n\n".join(f"Paragraph {i} " + "word " * 60 for i in range(10))
    md = f"# Doc\n\n## Long\n\n{body}\n\n```\n# not a heading\n```\n"
    chunks = chunk_markdown(md, "Doc")
    assert len(chunks) > 1
    assert all(c.section == "Long" for c in chunks)
    assert any("# not a heading" in c.text for c in chunks)


async def test_sync_builtin_adds_updates_skips_and_removes(session, llm, tmp_path: Path):
    (tmp_path / "01-estimation.md").write_text(GUIDE_MD, encoding="utf-8")
    (tmp_path / "02-roles.md").write_text(
        "# Roles\n\n## Admin\n\nAdmins can do everything.\n", encoding="utf-8"
    )

    stats = await sync_builtin(session, llm, tmp_path)
    assert stats == {"added": 2, "updated": 0, "unchanged": 0, "removed": 0}
    est = await session.scalar(select(Document).where(Document.slug == "estimation"))
    assert est.title == "Estimation" and est.status == "ready" and est.chunk_count == 4

    assert (await sync_builtin(session, llm, tmp_path))["unchanged"] == 2

    (tmp_path / "01-estimation.md").write_text(
        GUIDE_MD + "\n## Step 3: sprints\n\nFirst fit.\n", encoding="utf-8"
    )
    (tmp_path / "02-roles.md").unlink()
    stats = await sync_builtin(session, llm, tmp_path)
    assert stats == {"added": 0, "updated": 1, "unchanged": 0, "removed": 1}
    assert (
        await session.scalar(select(func.count(DocumentChunk.id)).where(DocumentChunk.document_id == est.id))
        == 5
    )
    assert await session.scalar(select(func.count(Document.id))) == 1


async def _indexed(session, llm, tmp_path: Path):
    (tmp_path / "05-estimation.md").write_text(GUIDE_MD, encoding="utf-8")
    await sync_builtin(session, llm, tmp_path)


async def test_assistant_returns_only_cited_sources(session, llm, tmp_path):
    await _indexed(session, llm, tmp_path)
    llm.say("Prices are committed hours times the hourly rate [C1].")

    ans = await answer_question(session, llm, "How is the price calculated?", [])

    assert ans.grounded
    assert [c.id for c in ans.citations] == [1]
    assert ans.citations[0].title == "Estimation"
    # The excerpts given to the model carry their markers and labels
    assert "[C1] (Estimation" in llm.chat_calls[0][0]["content"]


async def test_uncited_answer_is_retried_then_rejected(session, llm, tmp_path):
    await _indexed(session, llm, tmp_path)
    llm.say("It's hours times rate.")
    llm.say("Still no citation.")

    ans = await answer_question(session, llm, "How is the price calculated?", [])

    assert not ans.grounded
    assert ans.answer == UNGROUNDED_REPLY
    assert ans.citations  # related sections are still suggested
    assert "rejected" in llm.chat_calls[1][-1]["content"]


async def test_invented_citation_marker_is_not_accepted(session, llm, tmp_path):
    await _indexed(session, llm, tmp_path)
    llm.say("See [C99].")
    llm.say("The rate applies to committed hours [C2].")

    ans = await answer_question(session, llm, "price?", [])
    assert ans.grounded and [c.id for c in ans.citations] == [2]


async def test_not_found_is_reported_honestly(session, llm, tmp_path):
    await _indexed(session, llm, tmp_path)
    llm.say(NOT_FOUND)
    ans = await answer_question(session, llm, "What is the office wifi password?", [])
    assert not ans.grounded and ans.answer == NOT_FOUND_REPLY and ans.citations == []


async def test_without_documentation_the_model_is_not_called(session, llm):
    ans = await answer_question(session, llm, "anything", [])
    assert not ans.grounded and llm.chat_calls == []


def test_short_follow_ups_reuse_the_previous_question():
    history = [Turn(role="user", content="How is the price calculated?"), Turn(role="assistant", content="…")]
    assert retrieval_query("and the deposit?", history) == "How is the price calculated? and the deposit?"
    long_q = "What happens when a client asks for a bigger discount than allowed?"
    assert retrieval_query(long_q, history) == long_q
    # Short but unrelated questions are searched on their own
    assert (
        retrieval_query("What is the office wifi password?", history) == "What is the office wifi password?"
    )
    assert retrieval_query("why is that?", history).startswith("How is the price")


async def test_docs_api_permissions_and_management(client, session, llm, tmp_path, monkeypatch):  # noqa: F811
    await _indexed(session, llm, tmp_path)
    queued = []
    monkeypatch.setattr("app.tasks.ingest.ingest_guide_task.delay", lambda doc_id: queued.append(doc_id))
    monkeypatch.setattr(docs_api, "get_llm", lambda: llm)
    monkeypatch.setattr(get_settings(), "storage_dir", tmp_path / "storage")

    client_h = {
        "Authorization": "Bearer "
        + (
            await client.post(
                "/api/auth/register", json={"name": "C", "email": "c@c.io", "password": "secret123"}
            )
        ).json()["token"]
    }
    dev_h = await make_user(session, Role.developer, "dev@h.gh")
    admin_h = await make_user(session, Role.admin, "admin@h.gh")

    assert (await client.get("/api/docs", headers=client_h)).status_code == 403
    docs = (await client.get("/api/docs", headers=dev_h)).json()
    assert [d["slug"] for d in docs] == ["estimation"]
    detail = (await client.get(f"/api/docs/{docs[0]['id']}", headers=dev_h)).json()
    assert detail["content"].startswith("# Estimation")

    llm.say("Committed hours times rate [C1].")
    ans = (await client.post("/api/docs/ask", json={"question": "price?"}, headers=dev_h)).json()
    assert ans["grounded"] and ans["citations"][0]["document_id"] == docs[0]["id"]

    upload = {"file": ("runbook.md", b"# Runbook\n\n## Deploy\n\nRun the pipeline.\n", "text/markdown")}
    assert (await client.post("/api/docs", files=upload, headers=dev_h)).status_code == 403
    r = await client.post("/api/docs", files=upload, headers=admin_h)
    assert r.status_code == 200 and r.json()["source"] == "upload" and queued == [r.json()["id"]]
    bad = {"file": ("virus.exe", b"x", "application/octet-stream")}
    assert (await client.post("/api/docs", files=bad, headers=admin_h)).status_code == 422

    assert (await client.delete(f"/api/docs/{docs[0]['id']}", headers=admin_h)).status_code == 409
    assert (await client.delete(f"/api/docs/{r.json()['id']}", headers=dev_h)).status_code == 403
    assert (await client.delete(f"/api/docs/{r.json()['id']}", headers=admin_h)).status_code == 200


@pytest.mark.parametrize("name", ["01-overview.md", "05-estimation.md", "12-architecture-and-operations.md"])
def test_shipped_docs_have_a_title_and_sections(name):
    text = (get_settings().docs_dir / name).read_text(encoding="utf-8")
    chunks = chunk_markdown(text, title_of(text, name))
    assert title_of(text, "") and len(chunks) >= 3


def test_llm_circuit_breaker_skips_a_failing_model(monkeypatch):
    from app.core import llm as llm_mod

    router = object.__new__(llm_mod.LiteLLMClient)
    router._chain = [
        ("primary", "gemini/gemini-x-flash"),
        ("secondary", "gemini/gemini-x-flash-lite"),
        ("fallback", "ollama_chat/qwen2.5:7b"),
    ]
    router._down_until = {}
    clock = [1000.0]
    monkeypatch.setattr(llm_mod.time, "monotonic", lambda: clock[0])

    assert router._entry() == "primary"
    router._record("primary", "gemini-x-flash")  # served by the primary: nothing changes
    assert router._entry() == "primary"
    router._record("primary", "gemini-x-flash-lite")  # the router fell back: skip the primary for a while
    assert router._entry() == "secondary"
    router._record("secondary", "qwen2.5:7b")
    assert router._entry() == "fallback"
    clock[0] += llm_mod.COOLDOWN_SECONDS + 1
    assert router._entry() == "primary"
