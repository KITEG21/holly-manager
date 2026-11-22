"""LLM provider chain: configurable order, credentials, status and per-provider tests."""

from types import SimpleNamespace

import pytest

from app.api import admin as admin_api
from app.core import llm as llm_mod
from app.core.config import Settings
from app.models import Role
from tests.test_api_roles import client, make_user  # noqa: F401  (fixture)


def settings(**kw) -> Settings:
    base = dict(gemini_api_key=None, anthropic_api_key=None, openai_api_key=None, _env_file=None)
    return Settings(**(base | kw))


def build(monkeypatch, **kw) -> llm_mod.LiteLLMClient:
    s = settings(**kw)
    monkeypatch.setattr(llm_mod, "get_settings", lambda: s)
    return llm_mod.LiteLLMClient()


def test_chain_order_is_validated_and_deduplicated():
    assert llm_mod.chain_order(settings(llm_chain="Claude, openai ,claude,ollama")) == [
        "claude",
        "openai",
        "ollama",
    ]
    with pytest.raises(ValueError, match="unknown LLM_CHAIN providers: mistral"):
        llm_mod.chain_order(settings(llm_chain="claude,mistral"))


def test_providers_without_credentials_are_skipped(monkeypatch):
    only_local = build(monkeypatch)
    assert only_local._chain == [("ollama", "ollama_chat/qwen2.5:7b")]

    full = build(monkeypatch, gemini_api_key="g", anthropic_api_key="a", openai_api_key="o")
    assert [n for n, _ in full._chain] == ["gemini", "gemini_secondary", "claude", "openai", "ollama"]

    partial = build(monkeypatch, anthropic_api_key="a", openai_api_key="o", llm_chain="openai,claude,ollama")
    assert partial._chain == [
        ("openai", "openai/gpt-5"),
        ("claude", "anthropic/claude-sonnet-5-5"),
        ("ollama", "ollama_chat/qwen2.5:7b"),
    ]
    # Each remote provider fails fast instead of waiting for a saturated API
    claude = partial._providers["claude"].params()
    assert claude == {
        "model": "anthropic/claude-sonnet-5-5",
        "api_key": "a",
        "timeout": llm_mod.REMOTE_TIMEOUT,
    }


def test_empty_chain_falls_back_to_the_local_model(monkeypatch):
    client_ = build(monkeypatch, llm_chain="claude")  # Claude listed but without a key
    assert client_._chain == [("ollama", "ollama_chat/qwen2.5:7b")]


def test_status_reports_position_and_cooldown(monkeypatch):
    client_ = build(monkeypatch, anthropic_api_key="a", llm_chain="claude,openai,ollama")
    client_._record("claude", "qwen2.5:7b")  # Claude failed and the local model answered
    status = {p["name"]: p for p in client_.status()}
    assert status["claude"]["position"] == 1 and status["claude"]["cooling_down_seconds"] > 0
    assert status["openai"]["configured"] is False and status["openai"]["position"] is None
    assert status["ollama"]["position"] == 2
    assert client_._entry() == "ollama"


async def test_ping_tests_one_provider_and_clears_its_cooldown(monkeypatch):
    client_ = build(monkeypatch, anthropic_api_key="a", llm_chain="claude,ollama")
    client_._record("claude", "qwen2.5:7b")
    calls = []

    async def fake_acompletion(**kw):
        calls.append(kw)
        return SimpleNamespace(model="claude-sonnet-5-5")

    monkeypatch.setattr("litellm.acompletion", fake_acompletion)
    result = await client_.ping("claude")
    assert result["ok"] and result["model"] == "claude-sonnet-5-5"
    assert calls[0]["model"] == "anthropic/claude-sonnet-5-5" and calls[0]["api_key"] == "a"
    assert client_._entry() == "claude"
    assert (await client_.ping("openai")) == {
        "ok": False,
        "error": "not configured (missing API key or model)",
    }


async def test_llm_admin_endpoints(client, session, monkeypatch):  # noqa: F811
    llm_client = build(monkeypatch, anthropic_api_key="a")
    monkeypatch.setattr(admin_api, "get_llm", lambda: llm_client)
    dev_h = await make_user(session, Role.developer, "dev@h.gh")
    admin_h = await make_user(session, Role.admin, "admin@h.gh")

    assert (await client.get("/api/admin/llm", headers=dev_h)).status_code == 403
    status = (await client.get("/api/admin/llm", headers=admin_h)).json()
    assert [p["name"] for p in status if p["position"]] == ["claude", "ollama"]
    assert (await client.post("/api/admin/llm/mistral/test", headers=admin_h)).status_code == 404
    assert (await client.post("/api/admin/llm/openai/test", headers=admin_h)).json()["ok"] is False


async def test_ping_gives_up_on_a_provider_that_hangs(monkeypatch):
    import asyncio

    client_ = build(monkeypatch)  # only the local model

    async def hanging(**kw):
        await asyncio.sleep(5)

    monkeypatch.setattr("litellm.acompletion", hanging)
    monkeypatch.setattr(llm_mod, "PING_TIMEOUT", 0.05)
    result = await client_.ping("ollama")
    assert result["ok"] is False and result["error"] == "no response after 0.05 s"
