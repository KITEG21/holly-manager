from celery import Celery
from celery.signals import worker_process_init

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "holly",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.tasks.estimation", "app.tasks.pdf", "app.tasks.ingest"],
)
celery_app.conf.update(task_acks_late=True, worker_prefetch_multiplier=1, task_track_started=True)


@worker_process_init.connect
def _init_tracing(**_) -> None:
    from opentelemetry.instrumentation.celery import CeleryInstrumentor

    from app.core.telemetry import setup_telemetry

    setup_telemetry("worker")
    CeleryInstrumentor().instrument()
