from datetime import datetime, timezone, timedelta
from typing import Optional, List, Tuple
import logging
from decimal import Decimal

from celery import shared_task
from sqlalchemy import select, and_, or_
from sqlalchemy.orm import Session

from app.tier_config.tiers import feature_enabled
from app.services.rules_engine import RuleEvaluator
from app.models.rule import Rule, RuleViolation, RuleSeverity
from app.db.session import SyncSessionLocal
from app.models.document import Document, DocumentSession, DocumentStatus
from app.models.vendor import Vendor
from app.models.flag import DuplicateFlag, DuplicateMatchType
from app.models.audit_log import AuditLog
from app.models.extracted_field import ExtractedField
from rapidfuzz import fuzz

logger = logging.getLogger(__name__)


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


def get_field_value(session: Session, document_id: str, field_name: str) -> Tuple[Optional[str], float]:
    """Helper to get field value and confidence from extracted fields."""
    result = session.execute(
        select(ExtractedField)
        .where(and_(ExtractedField.document_id == document_id, ExtractedField.field_name == field_name))
    ).scalar_one_or_none()

    if result:
        return result.field_value, result.confidence_score
    return None, 0.0

@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    retry_backoff=True
)
def validate_critical_fields(self, document_id: str):
    """
    Quality Gate:
    - Checks critical fields for existence and confidence.
    - Normalizes vendor through fuzzy matching.
    """
    logger.info(f"Validating critical fields for document {document_id}")

    with SyncSessionLocal() as session:
        try:
            # Update session stage
            _update_session(session, document_id, "quality_gate", 55, "Validating critical fields and normalizing vendor")

            # 1. Quality Gate
            critical_fields = ["invoice_number", "vendor_name", "total_amount", "invoice_date"]
            failed_fields = []

            for field in critical_fields:
                val, conf = get_field_value(session, document_id, field)
                if val is None or conf < 0.5:
                    failed_fields.append(field)

            if failed_fields:
                doc = session.get(Document, document_id)
                doc.status = DocumentStatus.review

                log = AuditLog(
                    document_id=document_id,
                    action="quality_gate_failure",
                    after_state={"failed_fields": failed_fields, "message": "Critical fields missing or low confidence"}
                )
                session.add(log)
                session.commit()
                logger.warning(f"Document {document_id} failed quality gate: {failed_fields}")

            # 2. Vendor Normalization
            vendor_name, _ = get_field_value(session, document_id, "vendor_name")
            if vendor_name:
                # Search for existing vendors
                vendors = session.execute(select(Vendor)).scalars().all()
                best_match = None
                max_score = 0.0

                for v in vendors:
                    # Compare against canonical name
                    score = fuzz.token_set_ratio(vendor_name, v.canonical_name)
                    # Compare against aliases
                    for alias in v.aliases:
                        alias_score = fuzz.token_set_ratio(vendor_name, alias)
                        score = max(score, alias_score)

                    if score > max_score:
                        max_score = score
                        best_match = v

                if best_match and max_score >= 85.0:
                    logger.info(f"Matched vendor {vendor_name} to existing vendor {best_match.canonical_name} (score: {max_score})")

                    # Update the vendor aliases if it's a new variation
                    if vendor_name not in best_match.aliases and vendor_name != best_match.canonical_name:
                        best_match.aliases.append(vendor_name)
                        from sqlalchemy.orm.attributes import flag_modified
                        flag_modified(best_match, "aliases")
                else:
                    # Create new vendor
                    new_vendor = Vendor(
                        canonical_name=vendor_name,
                        aliases=[vendor_name],
                        is_new=True
                    )
                    session.add(new_vendor)
                    logger.info(f"Created new vendor {vendor_name}")

            session.commit()

        except Exception as e:
            session.rollback()
            logger.exception(f"Error validating critical fields for {document_id}: {e}")
            raise self.retry(exc=e)

@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    retry_backoff=True
)
def check_duplicates(self, document_id: str):
    """
    Checks for duplicate invoices:
    - Exact match: Same vendor and invoice number.
    - Fuzzy match: Same vendor, total_amount within 1%, invoice_date within 3 days.
    """
    logger.info(f"Checking duplicates for document {document_id}")

    with SyncSessionLocal() as session:
        try:
            _update_session(session, document_id, "duplicate_check", 60, "Checking for duplicate invoices")
            
            vendor_name, _ = get_field_value(session, document_id, "vendor_name")
            invoice_num, _ = get_field_value(session, document_id, "invoice_number")
            total_str, _ = get_field_value(session, document_id, "total_amount")
            date_str, _ = get_field_value(session, document_id, "invoice_date")

            if not vendor_name or not invoice_num:
                logger.info(f"Skipping duplicate check for {document_id}: missing vendor or invoice number")
                return

            try:
                total_amount = Decimal(total_str) if total_str else None
                invoice_date = datetime.fromisoformat(date_str) if date_str else None
            except Exception as e:
                logger.warning(f"Failed to parse amount/date for {document_id}: {e}")
                return

            # 1. Exact Key Match
            exact_match = session.execute(
                select(ExtractedField)
                .where(and_(
                    ExtractedField.field_name == "invoice_number",
                    ExtractedField.field_value == invoice_num
                ))
            ).scalars().all()

            for ef in exact_match:
                dup_doc_id = ef.document_id
                if dup_doc_id == document_id:
                    continue

                v_val, _ = get_field_value(session, dup_doc_id, "vendor_name")
                if v_val == vendor_name:
                    # Idempotency check: skip if flag already exists
                    existing_flag = session.execute(
                        select(DuplicateFlag)
                        .where(and_(
                            DuplicateFlag.document_id == document_id,
                            DuplicateFlag.duplicate_of_document_id == dup_doc_id
                        ))
                    ).scalars().first()

                    if existing_flag:
                        logger.info(f"Duplicate flag already exists for {document_id} vs {dup_doc_id}")
                        return

                    doc = session.get(Document, document_id)
                    doc.status = DocumentStatus.duplicate

                    flag = DuplicateFlag(
                        document_id=document_id,
                        duplicate_of_document_id=dup_doc_id,
                        match_type=DuplicateMatchType.exact_key,
                        confidence_score=1.0
                    )
                    session.add(flag)
                    session.commit()
                    logger.info(f"Document {document_id} is an exact duplicate of {dup_doc_id}")
                    return

            # 2. Fuzzy Match (Near-Duplicates)
            potential_dups = session.execute(
                select(ExtractedField)
                .where(and_(
                    ExtractedField.field_name == "vendor_name",
                    ExtractedField.field_value == vendor_name
                ))
            ).scalars().all()

            for ef in potential_dups:
                dup_doc_id = ef.document_id
                if dup_doc_id == document_id:
                    continue

                dup_total_str, _ = get_field_value(session, dup_doc_id, "total_amount")
                dup_date_str, _ = get_field_value(session, dup_doc_id, "invoice_date")

                if not dup_total_str or not dup_date_str:
                    continue

                try:
                    dup_total = Decimal(dup_total_str)
                    dup_date = datetime.fromisoformat(dup_date_str)
                except Exception:
                    continue

                amount_diff = abs(total_amount - dup_total) if total_amount else Decimal('0')
                amount_sim = 1.0 if (total_amount and dup_total and
                                   amount_diff <= (total_amount * Decimal('0.01'))) else 0.0

                date_diff = abs((invoice_date - dup_date).days) if (invoice_date and dup_date) else 999
                date_sim = 1.0 if date_diff <= 3 else 0.0

                if amount_sim == 1.0 and date_sim == 1.0:
                    # Idempotency check: skip if flag already exists
                    existing_flag = session.execute(
                        select(DuplicateFlag)
                        .where(and_(
                            DuplicateFlag.document_id == document_id,
                            DuplicateFlag.duplicate_of_document_id == dup_doc_id
                        ))
                    ).scalars().first()

                    if existing_flag:
                        logger.info(f"Duplicate flag already exists for {document_id} vs {dup_doc_id}")
                        return

                    doc = session.get(Document, document_id)
                    doc.status = DocumentStatus.duplicate

                    flag = DuplicateFlag(
                        document_id=document_id,
                        duplicate_of_document_id=dup_doc_id,
                        match_type=DuplicateMatchType.fuzzy_match,
                        confidence_score=0.9
                    )
                    session.add(flag)
                    session.commit()
                    logger.info(f"Document {document_id} is a fuzzy duplicate of {dup_doc_id}")
                    return

        except Exception as e:
            session.rollback()
            logger.exception(f"Error checking duplicates for {document_id}: {e}")
            raise self.retry(exc=e)

@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    retry_backoff=True
)
def evaluate_rules(self, document_id: str):
    """
    Deterministic Rules Engine Task:
    - Evaluates all active rules against the document and vendor.
    - Creates RuleViolation records for matches.
    - Overrides status to 'review' if any critical violation occurs.
    """
    logger.info(f"Evaluating rules for document {document_id}")

    if not feature_enabled("rules_engine"):
        logger.info(f"Rules engine disabled for document {document_id}, skipping.")
        return

    with SyncSessionLocal() as session:
        try:
            # 1. Setup Data
            doc = session.get(Document, document_id)
            if not doc:
                logger.error(f"Document {document_id} not found")
                return

            # Flatten extracted fields into a dict
            extracted_fields = session.execute(
                select(ExtractedField).where(ExtractedField.document_id == document_id)
            ).scalars().all()
            data_map = {ef.field_name: ef.field_value for ef in extracted_fields}

            # Find matched vendor
            vendor_name, _ = get_field_value(session, document_id, "vendor_name")
            vendor = None
            if vendor_name:
                vendor = session.execute(
                    select(Vendor).where(Vendor.canonical_name == vendor_name)
                ).scalars().first() # simplified lookup; normally we'd use the matched vendor from previous task

            # 2. Evaluate Rules
            active_rules = session.execute(select(Rule).where(Rule.active == True)).scalars().all()
            violations_created = 0
            has_critical = False

            for rule in active_rules:
                if RuleEvaluator.evaluate(rule.condition, data_map, vendor):
                    # Idempotency check: skip if a violation already exists for this
                    # document_id + rule_id pair (same pattern as check_duplicates).
                    existing_violation = session.execute(
                        select(RuleViolation)
                        .where(and_(
                            RuleViolation.document_id == document_id,
                            RuleViolation.rule_id == rule.id
                        ))
                    ).scalars().first()

                    if existing_violation:
                        logger.info(
                            f"Violation already exists for document {document_id} "
                            f"and rule {rule.id}; skipping re-insert."
                        )
                        continue

                    violations_created += 1

                    violation = RuleViolation(
                        document_id=document_id,
                        rule_id=rule.id,
                        details={"field_values": data_map, "rule_name": rule.name}
                    )
                    session.add(violation)

                    if rule.severity == RuleSeverity.critical:
                        has_critical = True

            # 3. Status and Session Update
            if has_critical:
                doc.status = DocumentStatus.review
                logger.warning(f"Critical rule violation found for {document_id}. Forced to review.")

            session_result = session.execute(
                select(DocumentSession)
                .where(DocumentSession.document_id == document_id)
                .order_by(DocumentSession.updated_at.desc())
            ).scalar_one_or_none()

            if session_result:
                session_result.current_stage = "rules_complete"
                session_result.progress_percent = 65

                history_entry = {
                    "stage": "rules_complete",
                    "progress": 65,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "message": f"Rules engine completed. {violations_created} violations found."
                }
                updated_history = list(session_result.stage_history)
                updated_history.append(history_entry)
                session_result.stage_history = updated_history

            session.commit()
            logger.info(f"Rules evaluation finished for {document_id}. Violations: {violations_created}")

        except Exception as e:
            session.rollback()
            logger.exception(f"Error evaluating rules for {document_id}: {e}")
            raise self.retry(exc=e)

@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    retry_backoff=True
)
def finalize_validation(self, document_id: str):
    """
    Updates the DocumentSession to mark validation as complete.
    """
    logger.info(f"Finalizing validation for document {document_id}")

    with SyncSessionLocal() as session:
        try:
            session_result = session.execute(
                select(DocumentSession)
                .where(DocumentSession.document_id == document_id)
                .order_by(DocumentSession.updated_at.desc())
            ).scalar_one_or_none()

            if session_result:
                session_result.current_stage = "validation_complete"
                session_result.progress_percent = 65

                history_entry = {
                    "stage": "validation_complete",
                    "progress": 65,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "message": "Validation and duplicate check completed"
                }
                updated_history = list(session_result.stage_history)
                updated_history.append(history_entry)
                session_result.stage_history = updated_history

                session.commit()
                logger.info(f"Document {document_id} validation finalized")
            else:
                logger.warning(f"Document {document_id} has no session to finalize")

        except Exception as e:
            session.rollback()
            logger.exception(f"Error finalizing validation for {document_id}: {e}")
            raise self.retry(exc=e)
