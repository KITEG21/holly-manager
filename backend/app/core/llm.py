"""Capa LLM sobre LiteLLM con una cadena de respaldo configurable (LLM_CHAIN): Gemini, Claude (Anthropic),
Codex/GPT (OpenAI) y un modelo local en Ollama. Se saltan los proveedores sin credenciales y, durante un rato,
los que acaban de fallar.

Los agentes dependen del protocolo `LLMClient`, no de LiteLLM, para poder testearlos con un LLM falso.
"""

import asyncio
import json
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Literal, Protocol, TypeVar

from pydantic import BaseModel, ValidationError

from app.core.config import get_settings
from app.core.telemetry import set_json_attr, tracer

T = TypeVar("T", bound=BaseModel)


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any]


class LLMResponse(BaseModel):
    content: str | None = None
    tool_calls: list[ToolCall] = []
    model: str | None = None


class LLMClient(Protocol):
    async def chat(self, messages: list[dict[str, Any]], tools: list[dict] | None = None) -> LLMResponse: ...

    async def structured(self, messages: list[dict[str, Any]], schema: type[T]) -> T: ...

    async def embed(self, texts: list[str], purpose: "EmbedPurpose" = "document") -> list[list[float]]: ...


EmbedPurpose = Literal["query", "document"]

# Algunos modelos de embeddings se entrenan con un prefijo por tarea; sin él la recuperación empeora mucho
EMBED_PREFIXES: dict[str, dict[str, str]] = {
    "nomic-embed-text": {"query": "search_query: ", "document": "search_document: "},
}


def with_prefix(model: str, texts: list[str], purpose: EmbedPurpose) -> list[str]:
    prefixes = next((p for name, p in EMBED_PREFIXES.items() if name in model), None)
    return [prefixes[purpose] + t for t in texts] if prefixes else texts


REMOTE_TIMEOUT = 30  # segundos por llamada a un proveedor remoto antes de pasar al siguiente
COOLDOWN_SECONDS = 300
PING_TIMEOUT = 60  # segundos máximos de la prueba de un proveedor desde Settings  # tiempo que se salta un modelo que acaba de fallar


@dataclass(frozen=True)
class Provider:
    """Un proveedor de la cadena: nombre usado en LLM_CHAIN, modelo de LiteLLM y sus credenciales."""

    name: str
    label: str
    model: str
    api_key: str | None = None
    api_base: str | None = None
    remote: bool = True

    @property
    def configured(self) -> bool:
        return bool(self.model) and (not self.remote or bool(self.api_key))

    def params(self) -> dict[str, Any]:
        params: dict[str, Any] = {"model": self.model}
        if self.api_key:
            params["api_key"] = self.api_key
        if self.api_base:
            params["api_base"] = self.api_base
        if self.remote:
            # Un proveedor saturado puede tardar más de un minuto en fallar: mejor pasar al siguiente
            params["timeout"] = REMOTE_TIMEOUT
        return params


def providers(s) -> list[Provider]:
    return [
        Provider("gemini", "Gemini", s.primary_model, api_key=s.gemini_api_key),
        Provider("gemini_secondary", "Gemini (secondary)", s.secondary_model or "", api_key=s.gemini_api_key),
        Provider("claude", "Claude (Anthropic)", s.claude_model, api_key=s.anthropic_api_key),
        Provider("openai", "Codex / GPT (OpenAI)", s.openai_model, api_key=s.openai_api_key),
        Provider("ollama", "Local (Ollama)", s.fallback_model, api_base=s.ollama_api_base, remote=False),
    ]


def chain_order(s) -> list[str]:
    known = {p.name for p in providers(s)}
    order = [n.strip().lower() for n in s.llm_chain.split(",") if n.strip()]
    unknown = [n for n in order if n not in known]
    if unknown:
        raise ValueError(
            f"unknown LLM_CHAIN providers: {', '.join(unknown)} (valid: {', '.join(sorted(known))})"
        )
    return list(dict.fromkeys(order))  # sin duplicados, conservando el orden


class StructuredOutputError(RuntimeError):
    pass


def tool_spec(name: str, description: str, args_model: type[BaseModel]) -> dict:
    schema = args_model.model_json_schema()
    schema.pop("title", None)
    for prop in schema.get("properties", {}).values():
        prop.pop("title", None)
    function: dict[str, Any] = {"name": name, "description": description}
    # Gemini rechaza objetos sin propiedades: una herramienta sin argumentos va sin `parameters`
    if schema.get("properties"):
        function["parameters"] = schema
    return {"type": "function", "function": function}


def _schema_instruction(schema: type[BaseModel]) -> str:
    return (
        "Reply ONLY with a valid JSON object that matches this JSON Schema. "
        "Do not invent data: if something is missing, use null.\n"
        f"{json.dumps(schema.model_json_schema(), ensure_ascii=False)}"
    )


class LiteLLMClient:
    def __init__(self) -> None:
        import litellm
        from litellm import Router

        # Cada proveedor admite parámetros distintos (p. ej. Gemini 3 no acepta temperature): se descartan
        litellm.drop_params = True

        s = get_settings()
        self._settings = s
        self._providers = {p.name: p for p in providers(s)}
        # Cadena en el orden de LLM_CHAIN, solo con los proveedores que tienen credenciales
        usable = [self._providers[n] for n in chain_order(s) if self._providers[n].configured]
        if not usable:
            usable = [self._providers["ollama"]]
        self._chain: list[tuple[str, str]] = [(p.name, p.model) for p in usable]
        model_list = [{"model_name": p.name, "litellm_params": p.params()} for p in usable]
        names = [n for n, _ in self._chain]
        fallbacks = [{n: names[i + 1 :]} for i, n in enumerate(names[:-1])]
        # Sin reintentos sobre el mismo modelo: la resiliencia la da la cadena de respaldo
        self._router = Router(model_list=model_list, fallbacks=fallbacks, num_retries=0, timeout=120)
        self._down_until: dict[str, float] = {}

    def status(self) -> list[dict[str, Any]]:
        """Estado de cada proveedor para la pantalla de Settings."""
        now = time.monotonic()
        names = [n for n, _ in self._chain]
        return [
            {
                "name": p.name,
                "label": p.label,
                "model": p.model,
                "configured": p.configured,
                "position": names.index(p.name) + 1 if p.name in names else None,
                "cooling_down_seconds": max(0, round(self._down_until.get(p.name, 0) - now)),
            }
            for p in self._providers.values()
        ]

    async def ping(self, name: str) -> dict[str, Any]:
        """Prueba un proveedor concreto, sin la cadena de respaldo."""
        from litellm import acompletion

        provider = self._providers[name]
        if not provider.configured:
            return {"ok": False, "error": "not configured (missing API key or model)"}
        started = time.monotonic()
        try:
            # Un modelo local frío puede tardar minutos en cargar: la prueba no debe colgar la pantalla
            resp = await asyncio.wait_for(
                acompletion(
                    **provider.params(),
                    messages=[{"role": "user", "content": "Reply with the word OK."}],
                    max_tokens=20,
                ),
                timeout=PING_TIMEOUT,
            )
        except TimeoutError:
            return {
                "ok": False,
                "latency_ms": round((time.monotonic() - started) * 1000),
                "error": f"no response after {PING_TIMEOUT} s",
            }
        except Exception as e:  # noqa: BLE001  el error se muestra tal cual en Settings
            return {
                "ok": False,
                "latency_ms": round((time.monotonic() - started) * 1000),
                "error": str(e)[:300],
            }
        if name in self._down_until:
            self._down_until.pop(name)  # vuelve a estar disponible
        return {"ok": True, "latency_ms": round((time.monotonic() - started) * 1000), "model": resp.model}

    def _entry(self) -> str:
        """Primer modelo de la cadena que no está en enfriamiento."""
        now = time.monotonic()
        return next((n for n, _ in self._chain if self._down_until.get(n, 0) <= now), self._chain[-1][0])

    def _record(self, entry: str, served_model: str | None) -> None:
        """Circuit breaker: si respondió un modelo posterior al de entrada, el de entrada falló; se salta un rato."""
        names = [n for n, _ in self._chain]
        # Coincidencia más larga: "gemini-x-flash-lite" no debe confundirse con "gemini-x-flash"
        matches = [(len(m), n) for n, m in self._chain if served_model and m.split("/")[-1] in served_model]
        served = max(matches)[1] if matches else entry
        if names.index(served) > names.index(entry):
            for n in names[names.index(entry) : names.index(served)]:
                self._down_until[n] = time.monotonic() + COOLDOWN_SECONDS

    async def chat(self, messages: list[dict[str, Any]], tools: list[dict] | None = None) -> LLMResponse:
        with tracer.start_as_current_span("llm.chat") as span:
            set_json_attr(span, "llm.prompt", messages[-6:])
            entry = self._entry()
            kwargs: dict[str, Any] = {"model": entry, "messages": messages, "temperature": 0.2}
            if tools:
                kwargs["tools"] = tools
            resp = await self._router.acompletion(**kwargs)
            msg = resp.choices[0].message
            calls = [
                ToolCall(
                    id=tc.id or f"call_{i}",
                    name=tc.function.name,
                    arguments=json.loads(tc.function.arguments or "{}"),
                )
                for i, tc in enumerate(msg.tool_calls or [])
            ]
            self._record(entry, resp.model)
            span.set_attribute("llm.model", resp.model or "")
            set_json_attr(span, "llm.completion", msg.content or "")
            set_json_attr(span, "llm.tool_calls", [c.model_dump() for c in calls])
            return LLMResponse(content=msg.content, tool_calls=calls, model=resp.model)

    async def structured(self, messages: list[dict[str, Any]], schema: type[T]) -> T:
        """Salida estructurada validada con Pydantic; si falla, reintenta una vez devolviendo el error al modelo."""
        convo = [{"role": "system", "content": _schema_instruction(schema)}, *messages]
        with tracer.start_as_current_span("llm.structured") as span:
            span.set_attribute("llm.schema", schema.__name__)
            last_error = ""
            for attempt in range(2):
                resp = await self._router.acompletion(
                    model=(entry := self._entry()),
                    messages=convo,
                    temperature=0,
                    response_format={"type": "json_object"},
                )
                self._record(entry, resp.model)
                raw = resp.choices[0].message.content or ""
                try:
                    result = schema.model_validate_json(_strip_fences(raw))
                    set_json_attr(span, "llm.result", result.model_dump(mode="json"))
                    span.set_attribute("llm.attempts", attempt + 1)
                    return result
                except ValidationError as e:
                    last_error = str(e)
                    convo = [
                        *convo,
                        {"role": "assistant", "content": raw},
                        {"role": "user", "content": f"The JSON is not valid: {last_error}. Fix it."},
                    ]
            raise StructuredOutputError(last_error)

    async def embed(self, texts: list[str], purpose: EmbedPurpose = "document") -> list[list[float]]:
        from litellm import aembedding

        s = self._settings
        kwargs: dict[str, Any] = {}
        if s.embedding_model.startswith("ollama"):
            kwargs["api_base"] = s.ollama_api_base
        else:
            kwargs.update(api_key=s.gemini_api_key, dimensions=s.embedding_dim)
        resp = await aembedding(
            model=s.embedding_model, input=with_prefix(s.embedding_model, texts, purpose), **kwargs
        )
        return [d["embedding"] for d in resp.data]


def _strip_fences(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw
        raw = raw.rsplit("```", 1)[0]
    return raw.strip()


@lru_cache
def get_llm() -> LLMClient:
    return LiteLLMClient()
