import json
from typing import Any

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from app.core.config import get_settings

_configured = False


def setup_telemetry(component: str) -> None:
    """Configura el exportador OTLP y la instrumentación automática (httpx cubre las llamadas de LiteLLM)."""
    global _configured
    if _configured:
        return
    _configured = True
    settings = get_settings()
    provider = TracerProvider(
        resource=Resource.create({"service.name": f"{settings.service_name}-{component}"})
    )
    if settings.otel_exporter_otlp_endpoint:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint, insecure=True))
        )
    trace.set_tracer_provider(provider)

    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

    HTTPXClientInstrumentor().instrument()


def instrument_engine(engine: Any) -> None:
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

    SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)


tracer = trace.get_tracer("holly.agents")


def set_json_attr(span: trace.Span, key: str, value: Any, limit: int = 4000) -> None:
    """Los atributos OTel solo admiten primitivos: serializamos y truncamos."""
    text = value if isinstance(value, str) else json.dumps(value, default=str, ensure_ascii=False)
    span.set_attribute(key, text[:limit])
