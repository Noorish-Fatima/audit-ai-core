from celery import shared_task
import logging

logger = logging.getLogger(__name__)


@shared_task(name="process_document")
def process_document(document_id: str):
    logger.info(f"Processing document: {document_id}")
    return {"status": "completed", "document_id": document_id, "message": "Document processing - not implemented yet"}


@shared_task(name="extract_text")
def extract_text(document_id: str):
    logger.info(f"Extracting text from document: {document_id}")
    return {"status": "completed", "document_id": document_id, "message": "Text extraction - not implemented yet"}


@shared_task(name="classify_document")
def classify_document(document_id: str):
    logger.info(f"Classifying document: {document_id}")
    return {"status": "completed", "document_id": document_id, "message": "Document classification - not implemented yet"}