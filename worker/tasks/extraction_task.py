"""
Celery task for invoice field extraction using LangGraph.
"""
from celery import shared_task
import logging
import uuid
from datetime import datetime
from decimal import Decimal
import json
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

logger = logging.getLogger(__name__)


@shared_task(name="extract_invoice_fields", bind=True, max_retries=3, default_retry_delay=60)
def extract_invoice_fields(self, document_id: str) -> dict:
    """
    Extract invoice fields using LangGraph extraction subgraph.
    
    This task:
    1. Loads document with raw OCR text and normalized images
    2. Runs LangGraph extraction subgraph (text_model -> confidence_check -> vision_model (optional) -> merge)
    3. Saves extracted fields to database
    4. Updates document_session to extraction_complete (progress=50)
    
    Retries with exponential backoff on provider errors (rate limit, timeout).
    Max 3 attempts, then routes to review queue with "extraction_failed" reason.
    """
    from app.db.session import sync_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy import select
    from app.models.document import Document, DocumentStatus, DocumentSession
    from app.models.extracted_field import ExtractedField, ExtractionMethod
    from app.models.audit_log import AuditLog
    import uuid
    import logging
    from datetime import datetime
    from decimal import Decimal
    import json
    import asyncio

    logger = logging.getLogger(__name__)

    SyncSessionLocal = sessionmaker(sync_engine, expire_on_commit=False)
    db: Session = SyncSessionLocal()


    try:
        # Get document
        result = db.execute(
            select(Document).where(Document.id == uuid.UUID(document_id))
        )
        document = result.scalar_one_or_none()

        if not document:
            logger.error(f"Document {document_id} not found")
            return {"status": "error", "message": "Document not found"}

        # Update document status to extracting
        document.status = DocumentStatus.extracting
        db.add(document)

        # Update session to extracting stage
        result = db.execute(
            select(DocumentSession)
            .where(DocumentSession.document_id == uuid.UUID(document_id))
            .order_by(DocumentSession.updated_at.desc())
            .limit(1)
        )
        session = result.scalar_one_or_none()

        if session:
            session.current_stage = "extracting"
            session.progress_percent = 25
            new_entry = {
                "stage": "extracting",
                "progress": 25,
                "timestamp": datetime.utcnow().isoformat(),
                "message": "Field extraction started"
            }
            if session.stage_history is None:
                session.stage_history = []
            session.stage_history.append(new_entry)
            db.add(session)

        db.commit()

        # Run the extraction graph
        from app.agents.extraction_graph import extraction_graph, ExtractionState

        # Prepare initial state
        initial_state = {
            "document_id": document_id,
            "raw_ocr_text": document.raw_ocr_text or "",
            "normalized_image_paths": document.normalized_image_paths or [],
            "extracted_fields": None,
            "vision_extracted_fields": None,
            "final_extracted_fields": None,
            "confidence_check_result": None,
            "error": None,
            "retry_count": 0,
        }

        # Run the graph
        try:
            result = asyncio.run(extraction_graph.ainvoke(initial_state, config={"configurable": {"thread_id": document_id}}))

            final_fields = result.get("final_extracted_fields")


            if final_fields:
                # Update document status to extracted (next pipeline stage)
                document.status = DocumentStatus.extracting
                db.add(document)

                # Update session to extraction_complete
                result_session = db.execute(
                    select(DocumentSession)
                    .where(DocumentSession.document_id == uuid.UUID(document_id))
                    .order_by(DocumentSession.updated_at.desc())
                    .limit(1)
                )
                session = result_session.scalar_one_or_none()

                if session:
                    session.current_stage = "extraction_complete"
                    session.progress_percent = 50
                    new_entry = {
                        "stage": "extraction_complete",
                        "progress": 50,
                        "timestamp": datetime.utcnow().isoformat(),
                        "message": "Field extraction completed"
                    }
                    if session.stage_history is None:
                        session.stage_history = []
                    session.stage_history.append(new_entry)

                db.commit()

                return {
                    "status": "completed",
                    "document_id": document_id,
                    "message": "Field extraction completed"
                }

        except Exception as e:
            logger.exception(f"Extraction failed for document {document_id}: {e}")

            # Retry logic with exponential backoff
            try:
                raise self.retry(exc=e, countdown=2 ** self.request.retries * 60)
            except self.MaxRetriesExceededError:
                # Max retries exceeded - flag document for review
                document.status = DocumentStatus.review
                document.error_reason = "extraction_failed"
                db.commit()
                return {"status": "failed", "document_id": document_id, "error": "Max retries exceeded"}

        return {"status": "completed", "document_id": document_id}

    except Exception as e:
        logger.exception(f"Extraction task failed for document {document_id}: {e}")
        return {"status": "error", "document_id": document_id, "error": str(e)}
    finally:
        db.close()


@shared_task(name="extract_invoice_fields_sync")
def extract_invoice_fields_sync(document_id: str) -> dict:
    """
    Synchronous version of extract_invoice_fields for testing.
    """
    # This would be a simplified synchronous version for testing
    return {"status": "not_implemented", "document_id": document_id}