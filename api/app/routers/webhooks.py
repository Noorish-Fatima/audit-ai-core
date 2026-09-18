import uuid
from fastapi import APIRouter

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.get("/health", include_in_schema=False)
async def webhooks_health():
    return {"status": "ok", "service": "webhooks"}


@router.post("/documents/{document_id}/callback")
async def document_callback(document_id: uuid.UUID):
    return {"message": "Document callback endpoint - not implemented yet", "document_id": document_id}


@router.post("/analysis/{analysis_id}/callback")
async def analysis_callback(analysis_id: uuid.UUID):
    return {"message": "Analysis callback endpoint - not implemented yet", "analysis_id": analysis_id}