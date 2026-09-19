from pathlib import Path
from typing import Optional
from datetime import datetime
from fastapi import APIRouter, Depends, File, UploadFile, HTTPException, Query, Response
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
from sqlalchemy.orm import selectinload
import uuid
import os
import shutil

from app.tier_config import settings
from app.db.session import get_session
from app.dependencies.auth import get_current_user
from app.models.document import Document, DocumentSession, DocumentStatus
from app.models.user import User

router = APIRouter(prefix="/documents", tags=["documents"])

ALLOWED_MIME_TYPES = set(settings.ALLOWED_MIME_TYPES)
MAX_FILE_SIZE = settings.MAX_FILE_SIZE
STORAGE_ROOT = Path(settings.STORAGE_ROOT)


def sanitize_filename(filename: str) -> str:
    """Sanitize filename to prevent path traversal."""
    filename = os.path.basename(filename)
    filename = "".join(c for c in filename if c.isalnum() or c in "._- ")
    return filename[:255]


def validate_file_type(mime_type: str) -> None:
    if mime_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type: {mime_type}. Allowed types: {', '.join(sorted(ALLOWED_MIME_TYPES))}",
        )


def validate_file_size(file_size: int) -> None:
    if file_size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File size {file_size} bytes exceeds maximum allowed size of {MAX_FILE_SIZE} bytes",
        )


def get_storage_path(ext: str) -> Path:
    """Generate a safe storage path with UUID filename."""
    STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
    unique_name = f"{uuid.uuid4()}{ext}"
    return STORAGE_ROOT / unique_name


def get_file_extension(mime_type: str) -> str:
    """Get file extension from MIME type."""
    mime_to_ext = {
        "application/pdf": ".pdf",
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/tiff": ".tiff",
    }
    return mime_to_ext.get(mime_type, ".bin")


async def enqueue_processing_chain(document_id: str):
    """Enqueue the Celery OCR normalization task for a document."""
    try:
        # Use Celery's send_task to avoid import issues between API and worker containers
        from celery import Celery
        from app.config import settings
        celery_app = Celery(
            "audit_ai_api",
            broker=settings.CELERY_BROKER_URL,
            backend=settings.CELERY_RESULT_BACKEND,
        )
        celery_app.send_task("ocr_normalize", args=[document_id])
    except Exception:
        import logging
        logging.getLogger(__name__).exception(f"Failed to enqueue processing for document {document_id}")


@router.get("/health", include_in_schema=False)
async def documents_health():
    return {"status": "ok", "service": "documents"}


@router.post("/upload", status_code=202)
async def upload_document(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Upload a document and start processing."""
    validate_file_type(file.content_type)
    
    # Read file content to check size
    content = await file.read()
    validate_file_size(len(content))
    
    # Reset file pointer for storage
    ext = get_file_extension(file.content_type)
    storage_path = get_storage_path(ext)
    
    # Write file to storage
    with open(storage_path, "wb") as f:
        f.write(content)
    
    # Create document record
    document = Document(
        original_filename=sanitize_filename(file.filename),
        storage_path=str(storage_path),
        mime_type=file.content_type,
        file_size=len(content),
        status=DocumentStatus.pending,
        uploaded_by=current_user.id,
    )
    db.add(document)
    await db.flush()
    
    # Create initial session
    session = DocumentSession(
        document_id=document.id,
        current_stage="uploaded",
        progress_percent=0,
        stage_history=[{
            "stage": "uploaded",
            "progress": 0,
            "timestamp": datetime.utcnow().isoformat(),
            "message": "Document uploaded successfully"
        }],
    )
    db.add(session)
    await db.commit()
    
    # Enqueue processing chain
    await enqueue_processing_chain(document.id)
    
    return {
        "document_id": document.id,
        "status": "accepted",
        "message": "Document uploaded successfully. Processing started."
    }


@router.get("/{document_id}/session")
async def get_document_session(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Get current processing session for a document."""
    result = await db.execute(
        select(DocumentSession)
        .where(DocumentSession.document_id == document_id)
        .order_by(DocumentSession.updated_at.desc())
        .limit(1)
    )
    session = result.scalar_one_or_none()
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return {
        "document_id": document_id,
        "current_stage": session.current_stage,
        "progress_percent": session.progress_percent,
        "stage_history": session.stage_history,
        "updated_at": session.updated_at.isoformat() if session.updated_at else None,
    }


@router.get("/{document_id}")
async def get_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Get full document detail including extracted fields.
    
    Note: Document visibility is intentionally shared across all authenticated users
    within the same deployment (any role: admin, approver, auditor). This matches
    the team-wide review queue workflow where any team member can view any document.
    Do not restrict this in v1.
    """
    result = await db.execute(
        select(Document)
        .options(
            selectinload(Document.extracted_fields),
            selectinload(Document.sessions),
        )
        .where(Document.id == document_id)
    )
    document = result.scalar_one_or_none()
    
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    return {
        "id": document.id,
        "original_filename": document.original_filename,
        "mime_type": document.mime_type,
        "file_size": document.file_size,
        "status": document.status.value,
        "uploaded_by": document.uploaded_by,
        "created_at": document.created_at.isoformat() if document.created_at else None,
        "updated_at": document.updated_at.isoformat() if document.updated_at else None,
        "raw_ocr_text": document.raw_ocr_text,
        "normalized_image_paths": document.normalized_image_paths,
        "extracted_fields": [
            {
                "id": ef.id,
                "field_name": ef.field_name,
                "value": getattr(ef, "field_value", getattr(ef, "value", None)),
                "confidence": getattr(ef, "confidence_score", getattr(ef, "confidence", 0.0)),
                "bbox": getattr(ef, "bbox", None),
            }
            for ef in document.extracted_fields
        ],
        "latest_session": {
            "current_stage": document.sessions[0].current_stage if document.sessions else None,
            "progress_percent": document.sessions[0].progress_percent if document.sessions else None,
            "stage_history": document.sessions[0].stage_history if document.sessions else None,
        } if document.sessions else None,
    }


@router.get("")
async def list_documents(
    status: Optional[str] = Query(None, description="Filter by document status"),
    uploaded_by: Optional[str] = Query(None, description="Filter by uploader user ID"),
    date_from: Optional[str] = Query(None, description="Filter by upload date (ISO format)"),
    date_to: Optional[str] = Query(None, description="Filter by upload date (ISO format)"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Paginated list of documents with filters.
    
    Note: Document visibility is intentionally shared across all authenticated users
    within the same deployment (any role: admin, approver, auditor). This matches
    the team-wide review queue workflow where any team member can view any document.
    Filters like `uploaded_by` are for convenience, not access control. Do not
    restrict visibility in v1.
    """
    query = select(Document)
    
    if status:
        try:
            status_enum = DocumentStatus(status)
            query = query.where(Document.status == status_enum)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
    
    if uploaded_by:
        query = query.where(Document.uploaded_by == uploaded_by)
    
    if date_from:
        try:
            dt_from = datetime.fromisoformat(date_from.replace("Z", "+00:00"))
            query = query.where(Document.created_at >= dt_from)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date_from format. Use ISO format.")
    
    if date_to:
        try:
            dt_to = datetime.fromisoformat(date_to.replace("Z", "+00:00"))
            query = query.where(Document.created_at <= dt_to)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date_to format. Use ISO format.")
    
    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)
    
    # Apply pagination and ordering
    query = query.order_by(desc(Document.created_at))
    query = query.offset((page - 1) * page_size).limit(page_size)
    
    result = await db.execute(query)
    documents = result.scalars().all()
    
    return {
        "items": [
            {
                "id": doc.id,
                "original_filename": doc.original_filename,
                "mime_type": doc.mime_type,
                "file_size": doc.file_size,
                "status": doc.status.value,
                "uploaded_by": doc.uploaded_by,
                "created_at": doc.created_at.isoformat() if doc.created_at else None,
            }
            for doc in documents
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size,
    }


@router.get("/{document_id}/file")
async def serve_document_file(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Serve the original document file with path containment check.
    
    Note: File access follows the same shared visibility model as document metadata.
    Any authenticated user can download any document file. The path containment
    check ensures the resolved storage path cannot escape the STORAGE_ROOT directory.
    """
    result = await db.execute(
        select(Document).where(Document.id == document_id)
    )
    document = result.scalar_one_or_none()
    
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Path containment check - ensure resolved path is within storage root
    storage_path = Path(document.storage_path).resolve()
    storage_root = STORAGE_ROOT.resolve()
    
    try:
        storage_path.relative_to(storage_root)
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied: path containment violation")
    
    if not storage_path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")
    
    # Determine media type
    media_type = document.mime_type
    
    return FileResponse(
        path=str(storage_path),
        media_type=media_type,
        filename=document.original_filename,
    )