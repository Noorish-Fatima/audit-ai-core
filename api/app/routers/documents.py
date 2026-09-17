from fastapi import APIRouter

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("/health", include_in_schema=False)
async def documents_health():
    return {"status": "ok", "service": "documents"}


@router.post("", status_code=201)
async def create_document():
    return {"message": "Document creation endpoint - not implemented yet"}


@router.get("/{document_id}")
async def get_document(document_id: str):
    return {"message": "Get document endpoint - not implemented yet", "document_id": document_id}


@router.get("")
async def list_documents():
    return {"message": "List documents endpoint - not implemented yet"}