from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, List
import logging

from celery import shared_task, chain, group
from sqlalchemy import select, func, and_, or_
from sqlalchemy.orm import Session

from app.tier_config.tiers import feature_enabled
from app.db.session import SyncSessionLocal
from app.models.document import Document, DocumentSession, DocumentStatus
from app.models.extracted_field import ExtractedField
from app.models.flag import FraudFlag, DuplicateFlag, DuplicateMatchType
from app.models.rule import RuleViolation
from app.models.audit_log import AuditLog
from app.models.vendor import Vendor
from app.models.user import User, UserRole

logger = logging.getLogger(__name__)


def get_field_value(session: Session, document_id: str, field_name: str) -> Optional[str]:
    result = session.execute(
        select(ExtractedField)
        .where(ExtractedField.document_id == document_id, ExtractedField.field_name == field_name)
    ).scalar_one_or_none()
    return result.field_value if result else None


def get_confidence(session: Session, document_id: str, field_name: str) -> float:
    result = session.execute(
        select(ExtractedField)
        .where(ExtractedField.document_id == document_id, ExtractedField.field_name == field_name)
    ).scalar_one_or_none()
    return result.confidence_score if result else 0.0


def _update_session(session: Session, document_id: str, stage: str, progress: int, message: str):
    session_result = session.execute(
        select(DocumentSession)
        .where(DocumentSession.document_id == document_id)
        .order_by(DocumentSession.updated_at.desc())
    ).scalar_one_or_none()

    if session_result:
        session_result.current_stage = stage
        session_result.progress_percent = progress
        history_entry = {
            "stage": stage,
            "progress": progress,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "message": message
        }
        updated_history = list(session_result.stage_history) if session_result.stage_history else []
        updated_history.append(history_entry)
        session_result.stage_history = updated_history


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    retry_backoff=True
)
def route_decision(self, document_id: str):
    """
    Final routing decision task:
    - If status already in (review, flagged, duplicate): leave it
    - Else if all confidence high + no violations/flags/mismatches → verified
    - Else → review
    - This is the ONLY place terminal status is set
    """
    logger.info(f"Running route_decision for document {document_id}")

    with SyncSessionLocal() as session:
        try:
            doc = session.get(Document, document_id)
            if not doc:
                logger.error(f"Document {document_id} not found")
                return {"status": "error", "reason": "document_not_found"}

            # Rule 1: If already in a review-required state, do not override
            if doc.status in (DocumentStatus.review, DocumentStatus.flagged, DocumentStatus.duplicate):
                logger.info(f"Document {document_id} already in {doc.status.value}, leaving unchanged")
                _update_session(session, document_id, "route_decision_complete", 90, f"Status already {doc.status.value}, no change")
                session.commit()
                return {"status": "completed", "final_status": doc.status.value, "changed": False}

            # Check all confidence scores
            critical_fields = ["invoice_number", "vendor_name", "total_amount", "invoice_date"]
            low_confidence = []
            for field in critical_fields:
                conf = get_confidence(session, document_id, field)
                if conf < 0.7:
                    low_confidence.append(field)

            # Check for any rule violations
            violations = session.execute(
                select(RuleViolation).where(RuleViolation.document_id == document_id)
            ).scalars().all()

            # Check for fraud flags
            fraud_flags = session.execute(
                select(FraudFlag).where(FraudFlag.document_id == document_id)
            ).scalars().all()

            # Check for duplicate flags
            duplicate_flags = session.execute(
                select(DuplicateFlag).where(DuplicateFlag.document_id == document_id)
            ).scalars().all()

            # Check for three-way match mismatches (rule violations from three_way_match)
            match_violations = [v for v in violations if v.rule_id is not None and 
                               v.details.get("po_number") is not None]

            # Decision logic
            has_issues = (
                len(low_confidence) > 0 or
                len(violations) > 0 or
                len(fraud_flags) > 0 or
                len(duplicate_flags) > 0 or
                len(match_violations) > 0
            )

            if not has_issues:
                # All clear → auto-verify
                doc.status = DocumentStatus.verified
                final_status = DocumentStatus.verified.value
                message = "All checks passed, auto-verified"
            else:
                # Any issue → review
                doc.status = DocumentStatus.review
                final_status = DocumentStatus.review.value
                issues = []
                if low_confidence:
                    issues.append(f"low_confidence: {low_confidence}")
                if violations:
                    issues.append(f"rule_violations: {len(violations)}")
                if fraud_flags:
                    issues.append(f"fraud_flags: {len(fraud_flags)}")
                if duplicate_flags:
                    issues.append(f"duplicate_flags: {len(duplicate_flags)}")
                if match_violations:
                    issues.append(f"match_mismatches: {len(match_violations)}")
                message = f"Requires review: {', '.join(issues)}"

            _update_session(session, document_id, "route_decision_complete", 90, message)

            # Audit log for the decision
            audit = AuditLog(
                document_id=document_id,
                action="route_decision",
                after_state={
                    "final_status": final_status,
                    "low_confidence_fields": low_confidence,
                    "violation_count": len(violations),
                    "fraud_flag_count": len(fraud_flags),
                    "duplicate_flag_count": len(duplicate_flags),
                    "match_mismatch_count": len(match_violations)
                }
            )
            session.add(audit)

            session.commit()
            logger.info(f"Route decision for {document_id}: {final_status}")

            return {
                "status": "completed",
                "document_id": document_id,
                "final_status": final_status,
                "changed": True,
                "issues": {
                    "low_confidence": low_confidence,
                    "violations": len(violations),
                    "fraud_flags": len(fraud_flags),
                    "duplicate_flags": len(duplicate_flags),
                    "match_mismatches": len(match_violations)
                }
            }

        except Exception as e:
            session.rollback()
            logger.exception(f"Error in route_decision for {document_id}: {e}")
            raise self.retry(exc=e)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    retry_backoff=True
)
def audit_log_commit(self, document_id: str):
    """
    Final audit log commit:
    - Writes summary audit_log entry for full pipeline run
    - Updates document_session to complete, progress=100
    """
    logger.info(f"Running audit_log_commit for document {document_id}")

    with SyncSessionLocal() as session:
        try:
            doc = session.get(Document, document_id)
            if not doc:
                logger.error(f"Document {document_id} not found")
                return {"status": "error", "reason": "document_not_found"}

            # Gather all pipeline data
            extracted_fields = session.execute(
                select(ExtractedField).where(ExtractedField.document_id == document_id)
            ).scalars().all()

            fraud_flags = session.execute(
                select(FraudFlag).where(FraudFlag.document_id == document_id)
            ).scalars().all()

            duplicate_flags = session.execute(
                select(DuplicateFlag).where(DuplicateFlag.document_id == document_id)
            ).scalars().all()

            rule_violations = session.execute(
                select(RuleViolation).where(RuleViolation.document_id == document_id)
            ).scalars().all()

            sessions = session.execute(
                select(DocumentSession)
                .where(DocumentSession.document_id == document_id)
                .order_by(DocumentSession.created_at)
            ).scalars().all()

            # Build summary
            summary = {
                "document_id": document_id,
                "final_status": doc.status.value,
                "extracted_fields_count": len(extracted_fields),
                "critical_field_confidences": {
                    f.field_name: f.confidence_score
                    for f in extracted_fields
                    if f.field_name in ["invoice_number", "vendor_name", "total_amount", "invoice_date"]
                },
                "fraud_flags": [
                    {"type": f.flag_type.value if hasattr(f.flag_type, 'value') else f.flag_type, "severity": f.severity, "details": f.details}
                    for f in fraud_flags
                ],
                "duplicate_flags": [
                    {"match_type": d.match_type.value if hasattr(d.match_type, 'value') else d.match_type, "confidence": d.confidence_score, "duplicate_of": str(d.duplicate_of_document_id)}
                    for d in duplicate_flags
                ],
                "rule_violations": [
                    {"rule_id": str(v.rule_id) if v.rule_id else "three_way_match", "details": v.details}
                    for v in rule_violations
                ],
                "pipeline_stages": [
                    {"stage": s.current_stage, "progress": s.progress_percent, "message": s.stage_history[-1].get("message") if s.stage_history else None}
                    for s in sessions
                ],
                "completed_at": datetime.now(timezone.utc).isoformat()
            }

            # Final audit log entry
            audit = AuditLog(
                document_id=document_id,
                action="pipeline_complete",
                after_state=summary
            )
            session.add(audit)

            # Update session to complete
            _update_session(session, document_id, "complete", 100, "Pipeline completed successfully")

            session.commit()
            logger.info(f"Audit log committed for {document_id}")

            return {"status": "completed", "document_id": document_id, "final_status": doc.status.value}

        except Exception as e:
            session.rollback()
            logger.exception(f"Error in audit_log_commit for {document_id}: {e}")
            raise self.retry(exc=e)


def build_document_pipeline(document_id: str):
    """
    Build the full document processing chain with proper stage progression:
    ocr_normalize(20) → extract_invoice_fields(50) → validate_critical_fields(55) → 
    check_duplicates(60) → evaluate_rules(65) → finalize_validation(70) → 
    check_fraud_patterns(75) → three_way_match(80) → route_decision(90) → audit_log_commit(100)
    """
    from celery import chain

    # Import task signatures
    from worker.tasks.ocr_task import ocr_normalize
    from worker.tasks.extraction_task import extract_invoice_fields
    from worker.tasks.validation_task import validate_critical_fields, check_duplicates, evaluate_rules, finalize_validation
    from worker.tasks.fraud_task import check_fraud_patterns
    from worker.tasks.three_way_match_task import three_way_match
    from worker.tasks.pipeline_tasks import route_decision, audit_log_commit

    return chain(
        ocr_normalize.si(document_id) |
        extract_invoice_fields.si(document_id) |
        validate_critical_fields.si(document_id) |
        check_duplicates.si(document_id) |
        evaluate_rules.si(document_id) |
        finalize_validation.si(document_id) |
        check_fraud_patterns.si(document_id) |
        three_way_match.si(document_id) |
        route_decision.si(document_id) |
        audit_log_commit.si(document_id)
    )


def start_document_pipeline(document_id: str):
    """Start the full document processing pipeline."""
    pipeline = build_document_pipeline(document_id)
    result = pipeline.apply_async()
    return result