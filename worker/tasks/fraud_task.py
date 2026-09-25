from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Optional, List
import logging

from celery import shared_task
from sqlalchemy import select, and_, func
from sqlalchemy.orm import Session

from app.tier_config.tiers import feature_enabled
from app.db.session import SyncSessionLocal
from app.models.document import Document, DocumentSession, DocumentStatus
from app.models.vendor import Vendor, VendorBankHistory
from app.models.flag import FraudFlag, FraudFlagType
from app.models.extracted_field import ExtractedField
from app.models.audit_log import AuditLog

logger = logging.getLogger(__name__)


def get_field_value(session: Session, document_id: str, field_name: str) -> Optional[str]:
    """Helper to get field value from extracted fields."""
    result = session.execute(
        select(ExtractedField)
        .where(and_(ExtractedField.document_id == document_id, ExtractedField.field_name == field_name))
    ).scalar_one_or_none()
    return result.field_value if result else None


def get_fraud_threshold(session: Session, rule_name: str, default_value: Decimal) -> Decimal:
    """Get fraud threshold from rules table, fallback to default."""
    from app.models.rule import Rule
    rule = session.execute(
        select(Rule).where(and_(Rule.name == rule_name, Rule.active == True))
    ).scalar_one_or_none()
    if rule and rule.condition.get("threshold"):
        try:
            return Decimal(str(rule.condition["threshold"]))
        except Exception:
            pass
    return default_value


def get_approval_thresholds(session: Session) -> List[Decimal]:
    """Get approval thresholds from rules table, fallback to defaults."""
    from app.models.rule import Rule
    rule = session.execute(
        select(Rule).where(and_(Rule.name == "approval_thresholds", Rule.active == True))
    ).scalar_one_or_none()
    if rule and isinstance(rule.condition.get("thresholds"), list):
        return [Decimal(str(t)) for t in rule.condition["thresholds"]]
    return [Decimal("10000")]


def _create_fraud_flag(
    session: Session,
    document_id: str,
    flag_type: FraudFlagType,
    severity: str,
    details: dict
) -> FraudFlag:
    """Create a fraud flag with idempotency check."""
    existing = session.execute(
        select(FraudFlag).where(and_(
            FraudFlag.document_id == document_id,
            FraudFlag.flag_type == flag_type
        ))
    ).scalar_one_or_none()
    if existing:
        logger.info(f"Fraud flag {flag_type} already exists for document {document_id}")
        return existing

    flag = FraudFlag(
        document_id=document_id,
        flag_type=flag_type,
        severity=severity,
        details=details
    )
    session.add(flag)
    return flag


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    retry_backoff=True
)
def check_fraud_patterns(self, document_id: str):
    """
    Fraud Pattern Detection Task:
    - Bank detail change detection (critical)
    - New vendor + high first invoice (high)
    - Round-number / threshold-avoidance pattern (high)
    - Updates document_session to fraud_check_complete, progress=85
    - Forces status to 'review' if any critical fraud flag
    """
    logger.info(f"Checking fraud patterns for document {document_id}")

    if not feature_enabled("fraud_detection"):
        logger.info(f"Fraud detection disabled for document {document_id}, skipping.")
        return {"status": "skipped", "reason": "feature_disabled"}

    with SyncSessionLocal() as session:
        try:
            doc = session.get(Document, document_id)
            if not doc:
                logger.error(f"Document {document_id} not found")
                return {"status": "error", "reason": "document_not_found"}

            vendor_name = get_field_value(session, document_id, "vendor_name")
            total_str = get_field_value(session, document_id, "total_amount")
            date_str = get_field_value(session, document_id, "invoice_date")

            if not vendor_name:
                logger.warning(f"Skipping fraud check for {document_id}: no vendor_name extracted")
                return {"status": "skipped", "reason": "no_vendor"}

            vendor = session.execute(
                select(Vendor).where(Vendor.canonical_name == vendor_name)
            ).scalars().first()

            if not vendor:
                logger.warning(f"Vendor {vendor_name} not found for document {document_id}")
                return {"status": "skipped", "reason": "vendor_not_found"}

            try:
                total_amount = Decimal(total_str) if total_str else Decimal("0")
                invoice_date = datetime.fromisoformat(date_str) if date_str else None
                if invoice_date and invoice_date.tzinfo is None:
                    invoice_date = invoice_date.replace(tzinfo=timezone.utc)
            except Exception as e:
                logger.warning(f"Failed to parse amount/date for {document_id}: {e}")
                return {"status": "error", "reason": "parse_failed"}

            logger.info(f"[DEBUG] invoice_date={invoice_date}, vendor.id={vendor.id}, vendor.bank_account_hash={vendor.bank_account_hash}, vendor_name={vendor_name}")

            has_critical = False

            # Detector 1: Bank detail change detection
            if vendor.bank_account_hash:
                recent_change = session.execute(
                    select(VendorBankHistory)
                    .where(and_(
                        VendorBankHistory.vendor_id == vendor.id,
                        VendorBankHistory.new_bank_account_hash == vendor.bank_account_hash,
                        VendorBankHistory.changed_at >= (invoice_date - timedelta(days=14)) if invoice_date else False,
                        VendorBankHistory.changed_at <= invoice_date if invoice_date else True,
                    ))
                    .order_by(VendorBankHistory.changed_at.desc())
                ).scalar_one_or_none()

                logger.info(f"[DEBUG] bank_change_query: vendor_id={vendor.id}, target_hash={vendor.bank_account_hash}, invoice_date={invoice_date}, found={recent_change is not None}")
                if recent_change:
                    logger.info(f"[DEBUG] recent_change: id={recent_change.id}, changed_at={recent_change.changed_at}, old_hash={recent_change.old_bank_account_hash}, new_hash={recent_change.new_bank_account_hash}, flagged={recent_change.flagged}")
                    _create_fraud_flag(
                        session,
                        document_id,
                        FraudFlagType.bank_change,
                        "critical",
                        {
                            "bank_history_id": str(recent_change.id),
                            "changed_at": recent_change.changed_at.isoformat(),
                            "old_hash": recent_change.old_bank_account_hash,
                            "new_hash": recent_change.new_bank_account_hash,
                            "days_before_invoice": (invoice_date - recent_change.changed_at).days if invoice_date else None,
                            "description": "Bank account details changed within 14 days before invoice date - potential BEC"
                        }
                    )
                    has_critical = True
                    logger.warning(f"CRITICAL: Bank change fraud detected for document {document_id}")

            # Detector 2: New vendor + high first invoice
            if vendor.is_new:
                prior_invoices = session.execute(
                    select(ExtractedField.document_id)
                    .join(Document, Document.id == ExtractedField.document_id)
                    .where(and_(
                        ExtractedField.field_name == "vendor_name",
                        ExtractedField.field_value == vendor_name,
                        Document.id != document_id
                    ))
                ).scalars().all()

                if not prior_invoices:
                    threshold = get_fraud_threshold(
                        session,
                        "new_vendor_high_amount_threshold",
                        Decimal("5000")
                    )
                    if total_amount > threshold:
                        _create_fraud_flag(
                            session,
                            document_id,
                            FraudFlagType.new_vendor_high_amount,
                            "high",
                            {
                                "vendor_id": str(vendor.id),
                                "total_amount": str(total_amount),
                                "threshold": str(threshold),
                                "description": f"New vendor's first invoice (${total_amount}) exceeds threshold (${threshold})"
                            }
                        )
                        logger.warning(f"HIGH: New vendor high amount fraud detected for document {document_id}")

            # Detector 3: Round-number / threshold-avoidance pattern
            thresholds = get_approval_thresholds(session)
            ninety_days_ago = (invoice_date - timedelta(days=90)) if invoice_date else datetime.now(timezone.utc) - timedelta(days=90)

            vendor_invoices = session.execute(
                select(ExtractedField.document_id, ExtractedField.field_value)
                .join(Document, Document.id == ExtractedField.document_id)
                .where(and_(
                    ExtractedField.field_name == "total_amount",
                    Document.id != document_id,
                    Document.created_at >= ninety_days_ago
                ))
            ).all()

            for threshold in thresholds:
                lower_bound = threshold * Decimal("0.95")
                cluster_invoices = []

                for inv_doc_id, amount_str in vendor_invoices:
                    try:
                        amount = Decimal(amount_str)
                        if lower_bound <= amount < threshold:
                            cluster_invoices.append((inv_doc_id, amount))
                    except Exception:
                        continue

                if len(cluster_invoices) >= 3:
                    cluster_invoice_ids = [str(inv_id) for inv_id, _ in cluster_invoices]
                    _create_fraud_flag(
                        session,
                        document_id,
                        FraudFlagType.round_number_threshold,
                        "high",
                        {
                            "threshold": str(threshold),
                            "lower_bound": str(lower_bound),
                            "cluster_invoice_ids": cluster_invoice_ids,
                            "cluster_amounts": [str(amt) for _, amt in cluster_invoices],
                            "current_invoice_amount": str(total_amount),
                            "description": f"Found {len(cluster_invoices)} invoices within 5% below ${threshold} approval threshold"
                        }
                    )
                    logger.warning(f"HIGH: Round number threshold avoidance detected for document {document_id}")
                    break

            # Update document status if critical flag found
            if has_critical:
                doc.status = DocumentStatus.review
                logger.warning(f"Document {document_id} forced to review due to critical fraud flag")

            # Update document session
            session_result = session.execute(
                select(DocumentSession)
                .where(DocumentSession.document_id == document_id)
                .order_by(DocumentSession.updated_at.desc())
            ).scalar_one_or_none()

            if session_result:
                session_result.current_stage = "fraud_check_complete"
                session_result.progress_percent = 75
                history_entry = {
                    "stage": "fraud_check_complete",
                    "progress": 75,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "message": "Fraud pattern detection completed"
                }
                updated_history = list(session_result.stage_history) if session_result.stage_history else []
                updated_history.append(history_entry)
                session_result.stage_history = updated_history

            # Audit log
            audit = AuditLog(
                document_id=document_id,
                action="fraud_check_completed",
                after_state={
                    "has_critical": has_critical,
                    "document_status": doc.status.value
                }
            )
            session.add(audit)

            session.commit()
            logger.info(f"Fraud check completed for document {document_id}. Critical: {has_critical}")

            return {
                "status": "completed",
                "document_id": document_id,
                "has_critical": has_critical,
                "document_status": doc.status.value
            }

        except Exception as e:
            session.rollback()
            logger.exception(f"Error checking fraud patterns for {document_id}: {e}")
            raise self.retry(exc=e)