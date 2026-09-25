from pathlib import Path
from typing import Optional, List
from datetime import datetime, timezone
from decimal import Decimal
from fastapi import APIRouter, Depends, File, UploadFile, HTTPException, Query, Response
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, case, and_, or_, String
from sqlalchemy.orm import selectinload
from pydantic import BaseModel
import uuid
import os
import shutil

from app.tier_config import settings
from app.db.session import get_session
from app.dependencies.auth import get_current_user, require_role
from app.models.document import Document, DocumentSession, DocumentStatus
from app.models.user import User, UserRole
from app.models.extracted_field import ExtractedField
from app.models.flag import FraudFlag, DuplicateFlag, DuplicateMatchType
from app.models.rule import RuleViolation
from app.models.audit_log import AuditLog

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
    """Enqueue the full document processing pipeline chain."""
    try:
        # Use Celery's send_task to avoid import issues between API and worker containers
        from celery import Celery, chain
        from app.config import settings
        celery_app = Celery(
            "audit_ai_api",
            broker=settings.CELERY_BROKER_URL,
            backend=settings.CELERY_RESULT_BACKEND,
        )
        # Build and apply the full pipeline chain directly using immutable signatures (si)
        # Use full task names as registered in the worker
        pipeline = chain(
            celery_app.signature("ocr_normalize", args=(document_id,), immutable=True) |
            celery_app.signature("extract_invoice_fields", args=(document_id,), immutable=True) |
            celery_app.signature("worker.tasks.validation_task.validate_critical_fields", args=(document_id,), immutable=True) |
            celery_app.signature("worker.tasks.validation_task.check_duplicates", args=(document_id,), immutable=True) |
            celery_app.signature("worker.tasks.validation_task.evaluate_rules", args=(document_id,), immutable=True) |
            celery_app.signature("worker.tasks.fraud_task.check_fraud_patterns", args=(document_id,), immutable=True) |
            celery_app.signature("worker.tasks.three_way_match_task.three_way_match", args=(document_id,), immutable=True) |
            celery_app.signature("worker.tasks.pipeline_tasks.route_decision", args=(document_id,), immutable=True) |
            celery_app.signature("worker.tasks.pipeline_tasks.audit_log_commit", args=(document_id,), immutable=True)
        )
        pipeline.apply_async()
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


@router.get(
    "/review-queue",
    dependencies=[Depends(require_role(UserRole.admin, UserRole.approver, UserRole.auditor))]
)
async def get_review_queue(
    status: Optional[List[str]] = Query(None, description="Filter by status"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    Get documents requiring review, sorted by priority score.
    Priority = higher severity flags + lower confidence = higher priority (lower number = more urgent)
    """
    # Base query for documents in review-required states
    review_statuses = [DocumentStatus.review, DocumentStatus.flagged, DocumentStatus.duplicate]
    if status:
        try:
            review_statuses = [DocumentStatus(s) for s in status]
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status in list")

    # Convert enum values to strings for proper PostgreSQL enum comparison
    status_values = [s.value for s in review_statuses]
    # Use text cast to avoid enum comparison issues
    query = select(Document).where(Document.status.cast(String).in_(status_values))

    # Join with extracted fields for confidence scores
    # Join with fraud_flags for severity
    # Join with rule_violations for count
    # Join with duplicate_flags for count

    # We'll compute priority in Python for flexibility
    result = await db.execute(query.order_by(desc(Document.created_at)))
    documents = result.scalars().all()

    # Compute priority scores
    doc_data = []
    for doc in documents:
        # Get confidence scores for critical fields
        fields_result = await db.execute(
            select(ExtractedField).where(
                ExtractedField.document_id == doc.id,
                ExtractedField.field_name.in_(["invoice_number", "vendor_name", "total_amount", "invoice_date"])
            )
        )
        fields = fields_result.scalars().all()
        confidences = {f.field_name: f.confidence_score for f in fields}
        avg_confidence = sum(confidences.values()) / len(confidences) if confidences else 0.0
        min_confidence = min(confidences.values()) if confidences else 0.0

        # Get fraud flags
        fraud_result = await db.execute(
            select(FraudFlag).where(FraudFlag.document_id == doc.id)
        )
        fraud_flags = fraud_result.scalars().all()

        # Get rule violations
        violations_result = await db.execute(
            select(RuleViolation).where(RuleViolation.document_id == doc.id)
        )
        violation_count = len(violations_result.scalars().all())

        # Get duplicate flags
        dup_result = await db.execute(
            select(DuplicateFlag).where(DuplicateFlag.document_id == doc.id)
        )
        duplicate_count = len(dup_result.scalars().all())

        # Priority score: lower = more urgent
        # Base priority from status
        status_priority = {"flagged": 0, "review": 1, "duplicate": 2}.get(doc.status.value, 3)
        
        # Adjust by severity and confidence
        priority_score = (
            status_priority * 100 +
            (4 - max(({"critical": 4, "high": 3, "medium": 2, "low": 1}.get(f.severity, 0) for f in fraud_flags), default=0)) * 20 +
            (1 - min_confidence) * 50 +
            violation_count * 10 +
            duplicate_count * 15
        )

        doc_data.append({
            "id": doc.id,
            "original_filename": doc.original_filename,
            "mime_type": doc.mime_type,
            "file_size": doc.file_size,
            "status": doc.status.value,
            "uploaded_by": doc.uploaded_by,
            "created_at": doc.created_at.isoformat() if doc.created_at else None,
            "priority_score": round(priority_score, 2),
            "min_confidence": round(min_confidence, 2),
            "max_fraud_severity": max(({"critical": 4, "high": 3, "medium": 2, "low": 1}.get(f.severity, 0) for f in fraud_flags), default=0),
            "violation_count": violation_count,
            "duplicate_count": duplicate_count,
            "fraud_flag_types": [f.flag_type.value if hasattr(f.flag_type, 'value') else f.flag_type for f in fraud_flags],
        })

    # Sort by priority (lower = more urgent)
    doc_data.sort(key=lambda x: x["priority_score"])

    # Paginate
    total = len(doc_data)
    start = (page - 1) * page_size
    end = start + page_size
    items = doc_data[start:end]

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size,
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
                "original_value": getattr(ef, "original_value", None),
                "is_corrected": getattr(ef, "is_corrected", False),
                "corrected_by": str(getattr(ef, "corrected_by", None)) if getattr(ef, "corrected_by", None) else None,
                "corrected_at": getattr(ef, "corrected_at", None).isoformat() if getattr(ef, "corrected_at", None) else None,
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

    # Join with extracted fields for confidence scores
    # Join with fraud_flags for severity
    # Join with rule_violations for count
    # Join with duplicate_flags for count

    # We'll compute priority in Python for flexibility
    result = await db.execute(query.order_by(desc(Document.created_at)))
    documents = result.scalars().all()

    # Compute priority scores
    doc_data = []
    for doc in documents:
        # Get confidence scores for critical fields
        fields_result = await db.execute(
            select(ExtractedField).where(
                ExtractedField.document_id == doc.id,
                ExtractedField.field_name.in_(["invoice_number", "vendor_name", "total_amount", "invoice_date"])
            )
        )
        fields = fields_result.scalars().all()
        confidences = {f.field_name: f.confidence_score for f in fields}
        avg_confidence = sum(confidences.values()) / len(confidences) if confidences else 0.0
        min_confidence = min(confidences.values()) if confidences else 0.0

        # Get fraud flags
        fraud_result = await db.execute(
            select(FraudFlag).where(FraudFlag.document_id == doc.id)
        )
        fraud_flags = fraud_result.scalars().all()
        max_fraud_severity = 0
        for f in fraud_flags:
            sev_map = {"critical": 4, "high": 3, "medium": 2, "low": 1}
            max_fraud_severity = max(max_fraud_severity, sev_map.get(f.severity, 0))

        # Get rule violations
        violations_result = await db.execute(
            select(RuleViolation).where(RuleViolation.document_id == doc.id)
        )
        violation_count = len(violations_result.scalars().all())

        # Get duplicate flags
        dup_result = await db.execute(
            select(DuplicateFlag).where(DuplicateFlag.document_id == doc.id)
        )
        duplicate_count = len(dup_result.scalars().all())

        # Priority score: lower = more urgent
        # Base priority from status
        status_priority = {"flagged": 0, "review": 1, "duplicate": 2}.get(doc.status.value, 3)
        
        # Adjust by severity and confidence
        priority_score = (
            status_priority * 100 +
            (4 - max_fraud_severity) * 20 +
            (1 - min_confidence) * 50 +
            violation_count * 10 +
            duplicate_count * 15
        )

        doc_data.append({
            "id": doc.id,
            "original_filename": doc.original_filename,
            "mime_type": doc.mime_type,
            "file_size": doc.file_size,
            "status": doc.status.value,
            "uploaded_by": doc.uploaded_by,
            "created_at": doc.created_at.isoformat() if doc.created_at else None,
            "priority_score": round(priority_score, 2),
            "min_confidence": round(min_confidence, 2),
            "max_fraud_severity": max_fraud_severity,
            "violation_count": violation_count,
            "duplicate_count": duplicate_count,
            "fraud_flag_types": [f.flag_type.value for f in fraud_flags],
        })

    # Sort by priority (lower = more urgent)
    doc_data.sort(key=lambda x: x["priority_score"])

    # Paginate
    total = len(doc_data)
    start = (page - 1) * page_size
    end = start + page_size
    items = doc_data[start:end]

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size,
    }


class FieldCorrection(BaseModel):
    field_name: str
    corrected_value: str


class ReviewDecision(BaseModel):
    action: str  # "verify", "flag", "confirm_duplicate"
    corrections: Optional[List[FieldCorrection]] = None
    reason: Optional[str] = None


@router.patch(
    "/{document_id}/review",
    dependencies=[Depends(require_role(UserRole.admin, UserRole.approver))]
)
async def review_document(
    document_id: uuid.UUID,
    decision: ReviewDecision,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    Human review correction endpoint.
    - Accepts corrected field values
    - Preserves original AI value in original_value before overwriting field_value
    - Sets is_corrected=true, corrected_by, corrected_at
    - Writes audit_log with before/after state
    - Allows setting final status: verified / flagged / confirmed_duplicate
    """
    # Validate action
    valid_actions = {"verify", "flag", "confirm_duplicate"}
    if decision.action not in valid_actions:
        raise HTTPException(status_code=400, detail=f"Invalid action. Must be one of: {valid_actions}")

    # Get document
    result = await db.execute(
        select(Document).where(Document.id == document_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Must be in review-required state
    if doc.status not in (DocumentStatus.review, DocumentStatus.flagged, DocumentStatus.duplicate):
        raise HTTPException(status_code=400, detail=f"Document not in review state (current: {doc.status.value})")

    # Capture before state
    before_fields_result = await db.execute(
        select(ExtractedField).where(ExtractedField.document_id == document_id)
    )
    before_fields = before_fields_result.scalars().all()
    before_state = {
        "status": doc.status.value,
        "fields": [
            {
                "field_name": f.field_name,
                "field_value": f.field_value,
                "confidence_score": f.confidence_score,
                "is_corrected": f.is_corrected,
            }
            for f in before_fields
        ]
    }

    # Apply corrections if provided
    if decision.corrections:
        for correction in decision.corrections:
            field_result = await db.execute(
                select(ExtractedField).where(
                    ExtractedField.document_id == document_id,
                    ExtractedField.field_name == correction.field_name
                )
            )
            field = field_result.scalar_one_or_none()
            if field:
                # Preserve original AI value
                field.original_value = field.field_value
                # Apply correction
                field.field_value = correction.corrected_value
                field.is_corrected = True
                field.corrected_by = current_user.id
                field.corrected_at = datetime.now(timezone.utc)
            else:
                # Create new corrected field
                new_field = ExtractedField(
                    document_id=document_id,
                    field_name=correction.field_name,
                    field_value=correction.corrected_value,
                    confidence_score=1.0,  # Human corrected = max confidence
                    extraction_method="human_review",
                    is_corrected=True,
                    original_value=None,
                    corrected_by=current_user.id,
                    corrected_at=datetime.now(timezone.utc),
                )
                db.add(new_field)

    # Set final status
    if decision.action == "verify":
        doc.status = DocumentStatus.verified
    elif decision.action == "flag":
        doc.status = DocumentStatus.flagged
    elif decision.action == "confirm_duplicate":
        doc.status = DocumentStatus.duplicate

    # Write audit log
    after_fields_result = await db.execute(
        select(ExtractedField).where(ExtractedField.document_id == document_id)
    )
    after_fields = after_fields_result.scalars().all()
    after_state = {
        "status": doc.status.value,
        "action": decision.action,
        "reason": decision.reason,
        "corrected_by": current_user.id,
        "fields": [
            {
                "field_name": f.field_name,
                "field_value": f.field_value,
                "confidence_score": f.confidence_score,
                "is_corrected": f.is_corrected,
                "corrected_by": str(f.corrected_by) if f.corrected_by else None,
                "corrected_at": f.corrected_at.isoformat() if f.corrected_at else None,
            }
            for f in after_fields
        ]
    }

    audit = AuditLog(
        document_id=document_id,
        action="human_review",
        before_state=before_state,
        after_state=after_state
    )
    db.add(audit)

    # Update session
    session_result = await db.execute(
        select(DocumentSession)
        .where(DocumentSession.document_id == document_id)
        .order_by(DocumentSession.updated_at.desc())
        .limit(1)
    )
    session_obj = session_result.scalar_one_or_none()
    if session_obj:
        session_obj.current_stage = "review_complete"
        session_obj.progress_percent = 100
        history_entry = {
            "stage": "review_complete",
            "progress": 100,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "message": f"Human review: {decision.action}" + (f" ({decision.reason})" if decision.reason else "")
        }
        updated_history = list(session_obj.stage_history) if session_obj.stage_history else []
        updated_history.append(history_entry)
        session_obj.stage_history = updated_history

    await db.commit()

    return {
        "document_id": str(document_id),
        "status": doc.status.value,
        "message": f"Review completed: {decision.action}",
        "corrections_applied": len(decision.corrections) if decision.corrections else 0,
    }