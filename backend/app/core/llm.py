"""Capa LLM sobre LiteLLM: Gemini como principal y un modelo local en Ollama como respaldo.

Los agentes dependen del protocolo `LLMClient`, no de LiteLLM, para poder testearlos con un LLM falso.
"""

import json
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
        model_list = [
            {
                "model_name": "fallback",
                "litellm_params": {"model": s.fallback_model, "api_base": s.ollama_api_base},
            }
        ]
        fallbacks = []
        self._entry = "fallback"
        if s.gemini_api_key:
            # Cadena: modelo principal → segundo modelo de Gemini (picos de demanda) → modelo local
            chain = []
            for name, model in [("primary", s.primary_model), ("secondary", s.secondary_model)]:
                if model:
                    model_list.append(
                        {"model_name": name, "litellm_params": {"model": model, "api_key": s.gemini_api_key}}
                    )
                    chain.append(name)
            fallbacks = [{chain[0]: [*chain[1:], "fallback"]}]
            self._entry = chain[0]
        self._router = Router(model_list=model_list, fallbacks=fallbacks, num_retries=1, timeout=90)

    async def chat(self, messages: list[dict[str, Any]], tools: list[dict] | None = None) -> LLMResponse:
        with tracer.start_as_current_span("llm.chat") as span:
            set_json_attr(span, "llm.prompt", messages[-6:])
            kwargs: dict[str, Any] = {"model": self._entry, "messages": messages, "temperature": 0.2}
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
                    model=self._entry,
                    messages=convo,
                    temperature=0,
                    response_format={"type": "json_object"},
                )
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
