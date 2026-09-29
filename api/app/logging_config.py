"""
Structured JSON logging shared by the API and the Celery worker.

Design: the stdlib root handler is bridged through structlog, so EVERY
existing `logging.getLogger(__name__)` call site automatically emits JSON
without being rewritten. Per-request / per-task context
(request_id, task_id, document_id) is carried in contextvars and merged
into every line, letting an operator trace one document end to end:

    docker logs audit-ai-api | grep '"document_id": "<uuid>"'

Usage for new code:
    from app.logging_config import get_logger
    logger = get_logger(__name__)
    logger.info("document uploaded", document_id=doc_id)
"""
import logging
import sys
import uuid

import structlog

_configured = False


def _ensure_trace_keys(logger, method_name, event_dict):
    """Guarantee every JSON line carries tracing keys.

    request_id is bound by the API middleware, task_id (+document_id) by the
    Celery prerun signal. Outside those contexts (startup, health checks
    before middleware runs) default to None so the keys are still present
    and operators can rely on the schema.
    """
    event_dict.setdefault("request_id", None)
    event_dict.setdefault("task_id", None)
    event_dict.setdefault("document_id", None)
    return event_dict


def configure_logging(level: str = "INFO") -> None:
    global _configured
    if _configured:
        return

    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            _ensure_trace_keys,
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            timestamper,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processor=structlog.processors.JSONRenderer(),
        foreign_pre_chain=[
            structlog.contextvars.merge_contextvars,
            _ensure_trace_keys,
            timestamper,
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    # Celery/uvicorn child loggers must propagate to the root handler.
    for noisy in ("uvicorn.error", "uvicorn.access", "celery", "celery.task"):
        logging.getLogger(noisy).handlers = []
        logging.getLogger(noisy).propagate = True

    _configured = True


def get_logger(name: str):
    configure_logging()
    return structlog.get_logger(name)


def bind_context(**kwargs) -> None:
    """Bind key/values (request_id, task_id, document_id) to all later logs."""
    structlog.contextvars.bind_contextvars(**kwargs)


def clear_context() -> None:
    structlog.contextvars.clear_contextvars()


def new_request_id() -> str:
    return uuid.uuid4().hex[:16]
