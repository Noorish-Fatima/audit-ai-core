from celery import Celery
from celery.signals import worker_ready, worker_shutdown
import logging

from app.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

celery_app = Celery(
    "audit_ai_worker",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "worker.tasks.document_tasks",
        "worker.tasks.analysis_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=100,
    result_expires=86400,
)


@worker_ready.connect
def on_worker_ready(**kwargs):
    logger.info("Worker is ready and accepting tasks")


@worker_shutdown.connect
def on_worker_shutdown(**kwargs):
    logger.info("Worker is shutting down")


@celery_app.task(name="health_check")
def health_check_task():
    return {"status": "ok", "service": "worker"}


if __name__ == "__main__":
    celery_app.start()