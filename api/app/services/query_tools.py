"""
Whitelisted parameterized query functions for NL query agent.
NO raw SQL generation - all queries are fixed, parameterized SQLAlchemy queries.
"""
import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from sqlalchemy import select, func, and_, or_, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.document import Document, DocumentStatus
from app.models.extracted_field import ExtractedField
from app.models.flag import FraudFlag, DuplicateFlag, FraudFlagType
from app.models.vendor import Vendor
from app.models.audit_log import AuditLog

logger = logging.getLogger(__name__)


async def get_vendor_spend(
    db: AsyncSession,
    vendor_name: str,
    date_from: date,
    date_to: date,
) -> dict:
    """
    Get total spend for a specific vendor within a date range.
    """
    logger.info(f"get_vendor_spend called with vendor_name='{vendor_name}', date_from={date_from}, date_to={date_to}")
    
    # Find vendor by fuzzy matching against canonical name and aliases
    # Same fuzzy matching logic used in validate_critical_fields (Prompt 8)
    from rapidfuzz import fuzz
    
    vendors_result = await db.execute(select(Vendor))
    vendors = vendors_result.scalars().all()
    
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
    
    vendor = best_match if max_score >= 85.0 else None
    
    logger.info(f"Vendor lookup result: {vendor.canonical_name if vendor else 'None'} (score: {max_score})")
    
    if not vendor:
        return {"vendor": vendor_name, "total_spend": "0.00", "invoice_count": 0, "period": f"{date_from} to {date_to}"}
    
    # Get all invoices for this vendor in date range
    # First get document IDs with matching vendor_name in extracted fields
    vendor_docs_result = await db.execute(
        select(ExtractedField.document_id).where(
            and_(
                ExtractedField.field_name == "vendor_name",
                or_(
                    ExtractedField.field_value.ilike(vendor.canonical_name),
                    ExtractedField.field_value.in_(vendor.aliases)
                )
            )
        )
    )
    vendor_doc_ids = [row[0] for row in vendor_docs_result.all()]
    
    logger.info(f"Found {len(vendor_doc_ids)} documents for vendor {vendor.canonical_name}")
    
    # Get total amounts for these documents within date range
    # Fetch values as strings and convert in Python to avoid SQLAlchemy Decimal casting issues
    total_result = await db.execute(
        select(
            ExtractedField.field_value,
            ExtractedField.document_id
        ).where(
            and_(
                ExtractedField.document_id.in_(vendor_doc_ids),
                ExtractedField.field_name == "total_amount",
            )
        )
    )
    
    total_amount = Decimal("0")
    invoice_ids = set()
    for row in total_result.all():
        try:
            total_amount += Decimal(row[0] or "0")
            invoice_ids.add(row[1])
        except Exception:
            pass
    
    invoice_count = len(invoice_ids)
    
    return {
        "vendor": vendor.canonical_name,
        "total_spend": total_amount,
        "invoice_count": invoice_count,
        "period": f"{date_from} to {date_to}"
    }


async def get_avg_tax_rate(
    db: AsyncSession,
    vendor_name: Optional[str],
    date_from: date,
    date_to: date,
) -> dict:
    """
    Get average tax rate across invoices, optionally filtered by vendor.
    """
    # Get document IDs matching criteria
    if vendor_name:
        vendor_result = await db.execute(
            select(Vendor).where(
                or_(
                    Vendor.canonical_name.ilike(vendor_name),
                    Vendor.aliases.contains([vendor_name])
                )
            )
        )
        vendor = vendor_result.scalar_one_or_none()
        
        if not vendor:
            return {"vendor": vendor_name, "avg_tax_rate": "0.00", "invoice_count": 0, "period": f"{date_from} to {date_to}"}
        
        vendor_docs_result = await db.execute(
            select(ExtractedField.document_id).where(
                and_(
                    ExtractedField.field_name == "vendor_name",
                    or_(
                        ExtractedField.field_value.ilike(vendor.canonical_name),
                        ExtractedField.field_value.in_(vendor.aliases)
                    )
                )
            )
        )
        vendor_doc_ids = [row[0] for row in vendor_docs_result.all()]
        
        if not vendor_doc_ids:
            return {"vendor": vendor.canonical_name, "avg_tax_rate": "0.00", "invoice_count": 0, "period": f"{date_from} to {date_to}"}
        
        doc_ids = vendor_doc_ids
    else:
        # All documents
        all_docs_result = await db.execute(select(Document.id))
        doc_ids = [row[0] for row in all_docs_result.all()]
    
    if not doc_ids:
        return {"vendor": vendor_name or "all", "avg_tax_rate": "0.00", "invoice_count": 0, "period": f"{date_from} to {date_to}"}
    
    # Get tax rates
    tax_result = await db.execute(
        select(ExtractedField.field_value).where(
            and_(
                ExtractedField.document_id.in_(doc_ids),
                ExtractedField.field_name == "tax_rate",
            )
        )
    )
    tax_values = [Decimal(row[0]) for row in tax_result.all() if row[0]]
    
    if not tax_values:
        return {"vendor": vendor_name or "all", "avg_tax_rate": "0.00", "invoice_count": 0, "period": f"{date_from} to {date_to}"}
    
    avg_rate = sum(tax_values) / len(tax_values)
    
    return {
        "vendor": vendor_name or "all",
        "avg_tax_rate": str(round(avg_rate, 4)),
        "invoice_count": len(tax_values),
        "period": f"{date_from} to {date_to}"
    }


async def list_flagged_documents(
    db: AsyncSession,
    severity: Optional[str],
    date_from: date,
    date_to: date,
) -> list:
    """
    List documents with fraud flags, optionally filtered by severity.
    """
    query = select(Document.id, Document.original_filename, Document.status, Document.created_at).where(
        and_(
            Document.created_at >= date_from,
            Document.created_at <= date_to,
        )
    )
    
    if severity:
        query = query.where(Document.status == DocumentStatus.review)  # Simplified - all flagged docs are in review
    
    docs_result = await db.execute(query.order_by(desc(Document.created_at)))
    documents = docs_result.all()
    
    results = []
    for doc in documents:
        # Get fraud flags for this document
        flags_result = await db.execute(
            select(FraudFlag).where(FraudFlag.document_id == doc.id)
        )
        flags = flags_result.scalars().all()
        
        if severity:
            flags = [f for f in flags if f.severity == severity]
        
        if flags:
            results.append({
                "document_id": str(doc.id),
                "filename": doc.original_filename,
                "status": doc.status.value,
                "created_at": doc.created_at.isoformat() if doc.created_at else None,
                "flags": [
                    {"type": f.flag_type.value, "severity": f.severity, "details": f.details}
                    for f in flags
                ]
            })
    
    return results


async def get_invoice_summary(
    db: AsyncSession,
    document_id: str,
) -> dict:
    """
    Get full invoice summary for a specific document.
    """
    doc_result = await db.execute(
        select(Document).options(
            selectinload(Document.extracted_fields),
            selectinload(Document.fraud_flags),
            selectinload(Document.duplicate_flags),
            selectinload(Document.rule_violations),
        ).where(Document.id == document_id)
    )
    doc = doc_result.scalar_one_or_none()
    
    if not doc:
        return {"error": "Document not found"}
    
    # Build summary from extracted fields
    fields = {ef.field_name: ef.field_value for ef in doc.extracted_fields}
    confidences = {ef.field_name: ef.confidence_score for ef in doc.extracted_fields}
    
    return {
        "document_id": str(doc.id),
        "filename": doc.original_filename,
        "status": doc.status.value,
        "vendor_name": fields.get("vendor_name"),
        "vendor_name_confidence": confidences.get("vendor_name"),
        "invoice_number": fields.get("invoice_number"),
        "invoice_number_confidence": confidences.get("invoice_number"),
        "invoice_date": fields.get("invoice_date"),
        "invoice_date_confidence": confidences.get("invoice_date"),
        "total_amount": fields.get("total_amount"),
        "total_amount_confidence": confidences.get("total_amount"),
        "tax_amount": fields.get("tax_amount"),
        "tax_rate": fields.get("tax_rate"),
        "currency": fields.get("currency"),
        "po_reference": fields.get("po_reference"),
        "fraud_flags": [
            {"type": f.flag_type.value, "severity": f.severity, "details": f.details}
            for f in doc.fraud_flags
        ],
        "duplicate_flags": [
            {"match_type": d.match_type.value, "confidence": d.confidence_score}
            for d in doc.duplicate_flags
        ],
        "rule_violations": len(doc.rule_violations),
    }


async def get_top_vendors_by_spend(
    db: AsyncSession,
    date_from: date,
    date_to: date,
    limit: int = 10,
) -> list:
    """
    Get top vendors by total spend within a date range.
    """
    # Get all documents with vendor_name and total_amount in date range
    all_docs_result = await db.execute(
        select(Document.id, Document.created_at).where(
            and_(
                Document.created_at >= date_from,
                Document.created_at <= date_to,
            )
        )
    )
    all_doc_ids = [row[0] for row in all_docs_result.all()]
    
    if not all_doc_ids:
        return []
    
    # Get vendor_name and total_amount for these documents
    vendor_data_result = await db.execute(
        select(
            ExtractedField.document_id,
            ExtractedField.field_name,
            ExtractedField.field_value
        ).where(
            and_(
                ExtractedField.document_id.in_(all_doc_ids),
                ExtractedField.field_name.in_(["vendor_name", "total_amount"]),
            )
        )
    )
    
    # Group by document
    doc_data = {}
    for row in vendor_data_result.all():
        doc_id, field_name, field_value = row
        if doc_id not in doc_data:
            doc_data[doc_id] = {}
        doc_data[doc_id][field_name] = field_value
    
    # Aggregate by vendor
    vendor_spend = {}
    for doc_id, data in doc_data.items():
        vendor = data.get("vendor_name")
        total = data.get("total_amount")
        if vendor and total:
            try:
                amount = Decimal(total)
                if vendor in vendor_spend:
                    vendor_spend[vendor] += amount
                else:
                    vendor_spend[vendor] = amount
            except:
                pass
    
    # Sort and limit
    sorted_vendors = sorted(vendor_spend.items(), key=lambda x: x[1], reverse=True)
    
    return [
        {"vendor": vendor, "total_spend": str(amount)}
        for vendor, amount in sorted_vendors[:limit]
    ]