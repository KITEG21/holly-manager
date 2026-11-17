from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from app.api import admin, auth, dev, escalations, leads
from app.core.config import get_settings
from app.core.db import engine
from app.core.telemetry import instrument_engine, setup_telemetry

setup_telemetry("api")
instrument_engine(engine)

app = FastAPI(title="Holly Manager", description="Sales agents with guardrails, plus task and time tracking")
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(dev.router)
app.include_router(leads.router)
app.include_router(escalations.router)


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


FastAPIInstrumentor.instrument_app(app, excluded_urls="api/health")
