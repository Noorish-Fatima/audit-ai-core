import os
import uuid
import logging
import numpy as np
from pathlib import Path
from typing import List, Optional
from datetime import datetime
from celery import shared_task
from PIL import Image, ImageOps, ImageEnhance, ExifTags
import cv2
import pytesseract
import pypdfium2 as pdfium
from sqlalchemy.orm import Session

from app.config import settings
from app.db.session import sync_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select
from app.models.document import Document, DocumentStatus, DocumentSession
from app.models.audit_log import AuditLog

logger = logging.getLogger(__name__)

ALLOWED_MIME_TYPES = set(settings.ALLOWED_MIME_TYPES)
STORAGE_ROOT = Path(settings.STORAGE_ROOT)
OCR_STORAGE_ROOT = STORAGE_ROOT / "normalized"
OCR_STORAGE_ROOT.mkdir(parents=True, exist_ok=True)


# Create sync session maker for Celery tasks
SyncSessionLocal = sessionmaker(sync_engine, expire_on_commit=False)


def get_deterministic_paths(document_id: str, page_count: int) -> List[Path]:
    """Generate deterministic normalized image paths for a document."""
    paths = []
    for i in range(page_count):
        filename = f"{document_id}_page_{i}.png"
        paths.append(OCR_STORAGE_ROOT / filename)
    return paths


def auto_orient_image(image: Image.Image) -> Image.Image:
    """Auto-orient image based on EXIF data, with Tesseract OSD fallback."""
    # Try EXIF-based orientation first
    try:
        exif = image.getexif()
        if exif:
            orientation_key = 274  # ExifTags.Base.Orientation
            if orientation_key in exif:
                orientation = exif[orientation_key]
                if orientation == 3:
                    image = image.rotate(180, expand=True)
                elif orientation == 6:
                    image = image.rotate(270, expand=True)
                elif orientation == 8:
                    image = image.rotate(90, expand=True)
                return image
    except Exception:
        pass
    
    # Fallback: Use Tesseract OSD (Orientation and Script Detection) to detect rotation
    try:
        osd = pytesseract.image_to_osd(image, output_type=pytesseract.Output.DICT)
        rotation = osd.get('rotate', 0)
        orientation = osd.get('orientation', 0)
        logger.debug(f"OSD: orientation={orientation}, rotate={rotation}")
        if rotation != 0:
            # Tesseract's 'rotate' indicates degrees to rotate CLOCKWISE
            # to make text upright. PIL's rotate() rotates COUNTER-CLOCKWISE
            # for positive angles. We must negate the angle.
            image = image.rotate(-rotation, expand=True)
            logger.info(f"Auto-oriented image by {-rotation} degrees CCW (={rotation} degrees CW) via OSD")
    except Exception as e:
        logger.warning(f"OSD auto-orient failed: {e}")
    
    return image


def deskew_image(image: Image.Image) -> Image.Image:
    """Deskew image using OpenCV. Only corrects small skew angles (< 5 degrees).
    Large rotations (90/180/270) are handled by auto_orient_image via OSD."""
    try:
        # Convert PIL to OpenCV
        cv_image = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
        gray = cv2.cvtColor(cv_image, cv2.COLOR_BGR2GRAY)
        
        # Threshold
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        
        # Find contours
        contours, _ = cv2.findContours(thresh, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return image
            
        # Find largest contour
        largest_contour = max(contours, key=cv2.contourArea)
        rect = cv2.minAreaRect(largest_contour)
        angle = rect[2]
        
        # Correct angle - minAreaRect returns angle in [-90, 0]
        if angle < -45:
            angle = 90 + angle
        
        # Only correct SMALL skew angles (< 5 degrees)
        # Large rotations (90/180/270) are handled by auto_orient_image via OSD
        if abs(angle) < 0.5:  # Already straight
            return image
        if abs(angle) > 5.0:  # Too large - likely a 90/180/270 rotation, skip deskew
            logger.debug(f"Deskew skipping large angle: {angle:.1f} degrees")
            return image
            
        # Rotate for small skew correction
        (h, w) = cv_image.shape[:2]
        center = (w // 2, h // 2)
        M = cv2.getRotationMatrix2D(center, angle, 1.0)
        rotated = cv2.warpAffine(cv_image, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
        
        # Convert back to PIL
        return Image.fromarray(cv2.cvtColor(rotated, cv2.COLOR_BGR2RGB))
    except Exception:
        logger.warning("Deskew failed, returning original image")
        return image


def adaptive_crop(image: Image.Image) -> Image.Image:
    """Crop to document boundaries using edge detection."""
    try:
        cv_image = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
        gray = cv2.cvtColor(cv_image, cv2.COLOR_BGR2GRAY)
        
        # Edge detection
        edges = cv2.Canny(gray, 50, 150, apertureSize=3)
        
        # Find contours
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return image
            
        # Find largest contour (document)
        largest_contour = max(contours, key=cv2.contourArea)
        area = cv2.contourArea(largest_contour)
        total_area = cv_image.shape[0] * cv_image.shape[1]
        
        # If contour is too small, skip
        if area < 0.1 * total_area:
            return image
            
        # Get bounding rect
        x, y, w, h = cv2.boundingRect(largest_contour)
        
        # Add small padding
        padding = 10
        x = max(0, x - padding)
        y = max(0, y - padding)
        w = min(cv_image.shape[1] - x, w + 2 * padding)
        h = min(cv_image.shape[0] - y, h + 2 * padding)
        
        cropped = cv_image[y:y+h, x:x+w]
        return Image.fromarray(cv2.cvtColor(cropped, cv2.COLOR_BGR2RGB))
    except Exception:
        logger.warning("Adaptive crop failed, returning original image")
        return image


def enhance_contrast(image: Image.Image) -> Image.Image:
    """Enhance contrast for better OCR."""
    try:
        # Convert to grayscale
        gray = image.convert('L')
        
        # Enhance contrast
        enhancer = ImageEnhance.Contrast(gray)
        enhanced = enhancer.enhance(1.5)
        
        # Convert back to RGB
        return enhanced.convert('RGB')
    except Exception:
        logger.warning("Contrast enhancement failed, returning original image")
        return image


def normalize_image(image: Image.Image) -> Image.Image:
    """Full normalization pipeline: deskew -> orient -> crop -> contrast.
    
    Order matters: deskew first to correct small skews, then orient to handle
    90/180/270 degree rotations. If orient runs first, deskew may detect the
    90-degree orientation and rotate the image back to sideways.
    """
    image = deskew_image(image)
    image = auto_orient_image(image)
    image = adaptive_crop(image)
    image = enhance_contrast(image)
    return image


def rasterize_pdf(pdf_path: Path) -> List[Image.Image]:
    """Rasterize PDF pages to images using pypdfium2."""
    images = []
    pdf = pdfium.PdfDocument(str(pdf_path))
    for i in range(len(pdf)):
        page = pdf[i]
        # Render at 300 DPI for good OCR quality
        bitmap = page.render(scale=300/72).to_pil()
        images.append(bitmap)
    return images


def load_image(path: Path) -> Image.Image:
    """Load image from file."""
    return Image.open(path).convert('RGB')


def save_normalized_image(image: Image.Image, output_path: Path) -> None:
    """Save normalized image as PNG."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, format='PNG', optimize=True)


def run_ocr(image: Image.Image) -> str:
    """Run Tesseract OCR on image."""
    try:
        # Use Tesseract with optimized settings for documents
        config = '--oem 3 --psm 6 -l eng'
        text = pytesseract.image_to_string(image, config=config)
        return text.strip()
    except Exception as e:
        logger.error(f"OCR failed: {e}")
        return ""


def _update_session_atomic(db: Session, document_id: str, stage: str, progress: int, message: str, document_status: DocumentStatus):
    """Atomically update session stage + document status in single transaction."""

    from datetime import datetime
    from sqlalchemy import select
    from sqlalchemy.orm.attributes import flag_modified
    from app.models.document import DocumentSession, Document
    
    # Get session
    result = db.execute(
        select(DocumentSession)
        .where(DocumentSession.document_id == uuid.UUID(document_id))
        .order_by(DocumentSession.updated_at.desc())
        .limit(1)
    )
    session = result.scalar_one_or_none()
    
    if session:
        session.current_stage = stage
        session.progress_percent = progress
        new_entry = {
            "stage": stage,
            "progress": progress,
            "timestamp": datetime.utcnow().isoformat(),
            "message": message,
        }
        if session.stage_history is None:
            session.stage_history = []
        # Create new list to ensure SQLAlchemy detects the change
        session.stage_history = session.stage_history + [new_entry]
        db.add(session)
        flag_modified(session, "stage_history")
    
    # Update document status in same transaction
    result = db.execute(select(Document).where(Document.id == uuid.UUID(document_id)))
    document = result.scalar_one_or_none()
    if document:
        document.status = document_status
        db.add(document)
    
    db.commit()


def _update_progress(db: Session, document_id: str, stage: str, progress: int, message: str = ""):
    """Update document session progress (non-atomic, for intermediate updates)."""

    from datetime import datetime
    from sqlalchemy import select
    from app.models.document import DocumentSession
    
    result = db.execute(
        select(DocumentSession)
        .where(DocumentSession.document_id == uuid.UUID(document_id))
        .order_by(DocumentSession.updated_at.desc())
        .limit(1)
    )
    session = result.scalar_one_or_none()
    
    if session:
        session.current_stage = stage
        session.progress_percent = progress
        new_entry = {
            "stage": stage,
            "progress": progress,
            "timestamp": datetime.utcnow().isoformat(),
            "message": message,
        }
        if session.stage_history is None:
            session.stage_history = []
        session.stage_history.append(new_entry)
        db.add(session)
        db.commit()


def flag_document(document_id: str, reason: str, error_msg: str):
    """Flag document and create audit log. Uses a fresh database session."""
    from app.db.session import sync_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy import select
    from app.models.document import Document
    from app.models.audit_log import AuditLog
    from datetime import datetime
    import uuid
    
    # Create a fresh session for this operation
    SyncSessionLocal = sessionmaker(sync_engine, expire_on_commit=False)
    db = SyncSessionLocal()
    
    try:
        result = db.execute(select(Document).where(Document.id == uuid.UUID(document_id)))
        document = result.scalar_one_or_none()
        if document:
            document.status = DocumentStatus.flagged
            db.add(document)
            
            # Create audit log
            audit = AuditLog(
                document_id=uuid.UUID(document_id),
                action="ocr_failed",
                before_state={"status": "ocr_processing"},
                after_state={"status": "flagged", "reason": reason, "error": str(error_msg)[:500]},
            )
            db.add(audit)
            db.commit()
            logger.info(f"Flagged document {document_id} as failed: {reason}")
    except Exception as e:
        logger.exception(f"Failed to flag document {document_id}: {e}")
        db.rollback()
    finally:
        db.close()


@shared_task(name="ocr_normalize", bind=True, max_retries=3, default_retry_delay=60)
def ocr_normalize(self, document_id: str) -> dict:
    """
    OCR and normalization task.
    - Load file, detect type (PDF or image)
    - Normalize images (orient, deskew, crop, contrast)
    - Run Tesseract OCR
    - Store results in document record
    - Update session progress atomically with document status
    - Idempotent via deterministic output paths
    """
    db = SyncSessionLocal()
    
    try:
        # Get document
        result = db.execute(
            select(Document).where(Document.id == uuid.UUID(document_id))
        )
        document = result.scalar_one_or_none()
        
        if not document:
            logger.error(f"Document {document_id} not found")
            return {"status": "error", "message": "Document not found"}
        
        # Update status to processing
        document.status = DocumentStatus.ocr_processing
        db.add(document)
        db.commit()
        
        _update_progress(db, document_id, "ocr_processing", 5, "Starting OCR processing")
        
        # Check if already processed (idempotency)
        existing_paths = document.normalized_image_paths or []
        if existing_paths and all(Path(p).exists() for p in existing_paths):
            logger.info(f"Document {document_id} already processed, skipping")
            document.status = DocumentStatus.extracting
            document.raw_ocr_text = document.raw_ocr_text or ""
            db.add(document)
            db.commit()
            _update_session_atomic(db, document_id, "ocr_complete", 25, "Already processed", DocumentStatus.extracting)
            return {"status": "completed", "document_id": document_id, "skipped": True}
        
        # Load source file
        source_path = Path(document.storage_path)
        if not source_path.exists():
            raise FileNotFoundError(f"Source file not found: {source_path}")
        
        mime_type = document.mime_type
        images = []
        
        # Rasterize PDF or load image
        if mime_type == "application/pdf":
            _update_progress(db, document_id, "ocr_processing", 10, "Rasterizing PDF")
            try:
                images = rasterize_pdf(Path(document.storage_path))
            except Exception as e:
                logger.exception(f"Failed to rasterize PDF for document {document_id}: {e}")
                flag_document(document_id, "corrupted_pdf", e)
                _update_session_atomic(db, document_id, "failed", 0, f"Corrupted PDF: {str(e)[:200]}", DocumentStatus.flagged)
                return {"status": "failed", "document_id": document_id, "error": "Corrupted PDF file"}
        elif mime_type.startswith("image/"):

            _update_progress(db, document_id, "ocr_processing", 10, "Loading image")
            images = [load_image(Path(document.storage_path))]
        else:
            raise ValueError(f"Unsupported MIME type: {mime_type}")
        
        _update_progress(db, document.id, "ocr_processing", 15, f"Processing {len(images)} page(s)")
        
        # Process each page
        normalized_paths = []
        all_ocr_text = []
        
        for i, image in enumerate(images):
            _update_progress(db, document.id, "ocr_processing", 15 + int(50 * i / len(images)), f"Normalizing page {i+1}/{len(images)}")
            
            # Normalize image
            normalized = normalize_image(image)
            
            # Save normalized image
            output_path = OCR_STORAGE_ROOT / f"{document_id}_page_{i}.png"
            save_normalized_image(normalized, output_path)
            normalized_paths.append(str(output_path))
            
            # Run OCR
            text = run_ocr(normalized)
            all_ocr_text.append(f"--- Page {i+1} ---\n{text}")
        
        # Atomic update: save OCR results + transition document to extracting + session to ocr_complete
        document.raw_ocr_text = "\n\n".join(all_ocr_text)
        document.normalized_image_paths = normalized_paths
        document.status = DocumentStatus.extracting  # Next pipeline stage after OCR
        db.add(document)
        
        # Atomically update session with ocr_complete stage AND document status to extracting
        _update_session_atomic(db, document_id, "ocr_complete", 25, "OCR normalization complete", DocumentStatus.extracting)
        
        logger.info(f"OCR completed for document {document_id}")
        return {
            "status": "completed",
            "document_id": document_id,
            "pages": len(images),
            "normalized_paths": normalized_paths,
        }
        
    except Exception as e:
        logger.exception(f"OCR failed for document {document_id}: {e}")
        
        # Flag document and create audit log - use new session to avoid transaction issues
        try:
            flag_document(document_id, "ocr_failed", e)
        except Exception as e2:
            logger.exception(f"Failed to flag document {document_id}: {e2}")
        
        # Update session with failed stage
        try:
            _update_session_atomic(db, document_id, "failed", 0, f"OCR failed: {str(e)[:200]}", DocumentStatus.flagged)
        except Exception as e2:
            logger.exception(f"Failed to update session for document {document_id}: {e2}")
        
        # Do NOT re-raise - let the document land in flagged state
        return {"status": "failed", "document_id": document_id, "error": str(e)}
    finally:
        db.close()