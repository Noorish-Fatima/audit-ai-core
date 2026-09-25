from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
import logging

from celery import shared_task
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.tier_config.tiers import feature_enabled
from app.db.session import SyncSessionLocal
from app.models.document import Document, DocumentSession, DocumentStatus
from app.models.purchase_order import PurchaseOrder, GoodsReceipt
from app.models.extracted_field import ExtractedField
from app.models.rule import RuleViolation
from app.models.audit_log import AuditLog

logger = logging.getLogger(__name__)


def get_field_value(session: Session, document_id: str, field_name: str) -> Optional[str]:
    """Helper to get field value from extracted fields."""
    result = session.execute(
        select(ExtractedField)
        .where(ExtractedField.document_id == document_id, ExtractedField.field_name == field_name)
    ).scalar_one_or_none()
    return result.field_value if result else None


def get_tolerance_threshold(session: Session) -> Decimal:
    """Get 3-way match tolerance threshold from rules table, fallback to default 2%."""
    from app.models.rule import Rule
    rule = session.execute(
        select(Rule).where(Rule.name == "three_way_match_tolerance", Rule.active == True)
    ).scalar_one_or_none()
    if rule and rule.condition.get("tolerance_percent"):
        try:
            return Decimal(str(rule.condition["tolerance_percent"])) / Decimal("100")
        except Exception:
            pass
    return Decimal("0.02")  # Default 2%


def get_three_way_match_rule_id(session: Session) -> Optional[str]:
    """Get the rule ID for three-way match tolerance exceeded violations."""
    from app.models.rule import Rule
    rule = session.execute(
        select(Rule).where(Rule.name == "three_way_match_tolerance_exceeded", Rule.active == True)
    ).scalar_one_or_none()
    return str(rule.id) if rule else None


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    retry_backoff=True
)
def three_way_match(self, document_id: str):
    """
    Three-Way Match Task:
    - Matches invoice to PO via extracted PO reference field
    - Compares invoice.total_amount against po.expected_amount AND goods_receipt.received_amount
    - Tolerance threshold configurable (default 2%)
    - Mismatch beyond tolerance → rule_violations row with severity="high"
    - Updates document_session to three_way_match_complete, progress=80
    """
    logger.info(f"Running three-way match for document {document_id}")

    if not feature_enabled("three_way_match"):
        logger.info(f"Three-way match disabled for document {document_id}, skipping.")
        return {"status": "skipped", "reason": "feature_disabled"}

    with SyncSessionLocal() as session:
        try:
            doc = session.get(Document, document_id)
            if not doc:
                logger.error(f"Document {document_id} not found")
                return {"status": "error", "reason": "document_not_found"}

            # Get extracted fields
            po_reference = get_field_value(session, document_id, "po_reference")
            total_str = get_field_value(session, document_id, "total_amount")

            if not po_reference:
                logger.info(f"Document {document_id} has no PO reference, skipping three-way match")
                _update_session(session, document_id, "three_way_match_complete", 80, "No PO reference found, skipped")
                session.commit()
                return {"status": "completed", "skipped": True, "reason": "no_po_reference"}

            if not total_str:
                logger.warning(f"Document {document_id} has no total_amount extracted")
                _update_session(session, document_id, "three_way_match_complete", 80, "No total amount extracted, skipped")
                session.commit()
                return {"status": "completed", "skipped": True, "reason": "no_total_amount"}

            try:
                invoice_total = Decimal(total_str)
            except Exception as e:
                logger.warning(f"Failed to parse amount/date for {document_id}: {e}")
                _update_session(session, document_id, "three_way_match_complete", 80, "Failed to parse total amount")
                session.commit()
                return {"status": "error", "reason": "parse_failed"}

            # Find matching PO
            po = session.execute(
                select(PurchaseOrder).where(PurchaseOrder.po_number == po_reference)
            ).scalar_one_or_none()

            if not po:
                logger.info(f"No PO found with number {po_reference} for document {document_id}")
                _update_session(session, document_id, "three_way_match_complete", 80, f"PO {po_reference} not found, skipped")
                session.commit()
                return {"status": "completed", "skipped": True, "reason": "po_not_found"}

            # Get the most recent goods receipt for this PO
            receipt = session.execute(
                select(GoodsReceipt)
                .where(GoodsReceipt.po_id == po.id)
                .order_by(GoodsReceipt.received_at.desc())
            ).scalar_one_or_none()

            tolerance = get_tolerance_threshold(session)
            violations_created = 0

            # Compare invoice total vs PO expected amount
            po_amount = po.expected_amount
            amount_diff = abs(invoice_total - po_amount)
            allowed_diff = po_amount * tolerance
            po_mismatch = amount_diff > allowed_diff

            # Compare invoice total vs received amount (if receipt exists)
            receipt_mismatch = False
            receipt_amount = None
            if receipt:
                receipt_amount = receipt.received_amount
                receipt_diff = abs(invoice_total - receipt_amount)
                allowed_receipt_diff = receipt_amount * tolerance
                receipt_mismatch = receipt_diff > allowed_receipt_diff

            # Create violation if any mismatch beyond tolerance
            if po_mismatch or receipt_mismatch:
                # Get the rule ID for three-way match tolerance exceeded
                rule_id = get_three_way_match_rule_id(session)
                if not rule_id:
                    logger.error("three_way_match_tolerance_exceeded rule not found, cannot create violation")
                else:
                    # Check if violation already exists for this document + rule
                    existing = session.execute(
                        select(RuleViolation).where(
                            RuleViolation.document_id == document_id,
                            RuleViolation.rule_id == rule_id
                        )
                    ).scalar_one_or_none()

                    if not existing:
                        details = {
                            "invoice_total": str(invoice_total),
                            "po_expected_amount": str(po_amount),
                            "po_number": po.po_number,
                            "tolerance_percent": str(tolerance * 100),
                            "mismatches": []
                        }

                        if po_mismatch:
                            details["mismatches"].append({
                                "type": "invoice_vs_po",
                                "invoice_amount": str(invoice_total),
                                "po_amount": str(po_amount),
                                "difference": str(amount_diff),
                                "allowed_difference": str(allowed_diff),
                                "exceeds_tolerance": True
                            })

                        if receipt_mismatch and receipt_amount:
                            receipt_diff = abs(invoice_total - receipt_amount)
                            allowed_receipt_diff = receipt_amount * tolerance
                            details["mismatches"].append({
                                "type": "invoice_vs_receipt",
                                "invoice_amount": str(invoice_total),
                                "receipt_amount": str(receipt_amount),
                                "difference": str(receipt_diff),
                                "allowed_difference": str(allowed_receipt_diff),
                                "exceeds_tolerance": True
                            })

                        violation = RuleViolation(
                            document_id=document_id,
                            rule_id=rule_id,
                            details=details
                        )
                        session.add(violation)
                        violations_created = 1
                        logger.warning(f"Three-way match mismatch for document {document_id}: {details}")

            # Update document session
            _update_session(
                session,
                document_id,
                "three_way_match_complete",
                80,
                f"Three-way match completed. Violations: {violations_created}"
            )

            # Audit log
            audit = AuditLog(
                document_id=document_id,
                action="three_way_match_completed",
                after_state={
                    "po_reference": po_reference,
                    "po_found": po is not None,
                    "receipt_found": receipt is not None,
                    "violations_created": violations_created,
                    "po_mismatch": po_mismatch,
                    "receipt_mismatch": receipt_mismatch
                }
            )
            session.add(audit)

            session.commit()
            logger.info(f"Three-way match completed for document {document_id}. Violations: {violations_created}")

            return {
                "status": "completed",
                "document_id": document_id,
                "po_reference": po_reference,
                "po_found": po is not None,
                "receipt_found": receipt is not None,
                "violations_created": violations_created,
                "po_mismatch": po_mismatch,
                "receipt_mismatch": receipt_mismatch
            }

        except Exception as e:
            session.rollback()
            logger.exception(f"Error in three-way match for {document_id}: {e}")
            raise self.retry(exc=e)


def _update_session(session: Session, document_id: str, stage: str, progress: int, message: str):
    """Update document session with new stage and progress."""
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