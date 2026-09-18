import uuid
from fastapi import APIRouter

router = APIRouter(prefix="/analysis", tags=["analysis"])


@router.get("/health", include_in_schema=False)
async def analysis_health():
    return {"status": "ok", "service": "analysis"}


@router.post("/{document_id}/start", status_code=202)
async def start_analysis(document_id: uuid.UUID):
    return {"message": "Start analysis endpoint - not implemented yet", "document_id": document_id}


@router.get("/{analysis_id}/status")
async def get_analysis_status(analysis_id: uuid.UUID):
    return {"message": "Get analysis status endpoint - not implemented yet", "analysis_id": analysis_id}


@router.get("/{analysis_id}/result")
async def get_analysis_result(analysis_id: uuid.UUID):
    return {"message": "Get analysis result endpoint - not implemented yet", "analysis_id": analysis_id}