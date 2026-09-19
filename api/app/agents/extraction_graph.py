"""
LangGraph extraction subgraph for invoice field extraction.
"""
from typing import Literal, Optional
from typing_extensions import TypedDict

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from app.schemas.extraction import ExtractedInvoiceFields, LineItem
from app.config import settings
from app.db.session import sync_engine
from app.models.document import Document, DocumentStatus, DocumentSession
from app.models.extracted_field import ExtractedField, ExtractionMethod
from app.db.session import get_session
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select
import uuid
import logging
import asyncio
import json
import re
from datetime import date, datetime
from decimal import Decimal

logger = logging.getLogger(__name__)


class ExtractionState(TypedDict):
    """State for the extraction subgraph."""
    document_id: str
    raw_ocr_text: str
    normalized_image_paths: list[str]
    extracted_fields: Optional[dict]
    vision_extracted_fields: Optional[dict]
    final_extracted_fields: Optional[dict]
    confidence_check_result: Optional[dict]
    error: Optional[str]
    retry_count: int


# Currency symbol to ISO code mapping
CURRENCY_SYMBOL_MAP = {
    "$": "USD",
    "€": "EUR",
    "£": "GBP",
    "¥": "JPY",
    "₹": "INR",
    "₩": "KRW",
    "₽": "RUB",
    "₺": "TRY",
    "₪": "ILS",
    "₫": "VND",
    "₦": "NGN",
    "₡": "CRC",
    "₱": "PHP",
    "₴": "UAH",
    "₵": "GHS",
    "₸": "KZT",
    "₼": "AZN",
    "₾": "GEL",
}


def map_currency_symbol_to_iso(text: str) -> Optional[str]:
    """Map currency symbols in text to ISO 4217 codes. Returns None if no symbol found."""
    for symbol, iso_code in CURRENCY_SYMBOL_MAP.items():
        if symbol in text:
            return iso_code
    # Also check for explicit ISO codes
    iso_pattern = re.compile(r'\b(USD|EUR|GBP|JPY|CNY|INR|CAD|AUD|CHF|SGD|HKD|KRW|MXN|BRL|RUB|ZAR|TRY|ILS|NZD|NOK|SEK|DKK|PLN|CZK|HUF|THB|MYR|IDR|PHP|VND|AED|SAR|QAR|KWD|BHD|OMR|JOD|LBP|EGP|MAD|TND|DZD|KES|UGX|TZS|NGN|GHS|XOF|XAF|ETB|KSH|MWK|MUR|SCR|SZL|LSL|NAD|BWP|ZMW|MZN|AOA|STN|CVE|KMF|DJF|ERN|SOS|SDG|SSP|YER|IQD|IRR|SYP|LBP|JOD|KWD|BHD|OMR|QAR|AED|SAR|ILS|TRY|RUB|UAH|BYN|MDL|RON|BGN|HRK|RSD|MKD|ALL|BAM|GEL|AMD|AZN|KZT|UZS|KGS|TJS|TMT|MNT|LAK|KHR|MMK|BTN|MVR|LKR|NPR|AFN|PKR|BDT)\b')
    match = iso_pattern.search(text.upper())
    if match:
        return match.group(1)
    return None


async def text_model_node(state: ExtractionState) -> ExtractionState:
    """
    Extract invoice fields using Groq.
    """
    from groq import Groq

    document_id = state["document_id"]
    raw_ocr_text = state["raw_ocr_text"]

    logger.info(f"Running text model extraction (Groq) for document {document_id}")

    if not raw_ocr_text or not raw_ocr_text.strip():
        logger.warning(f"No OCR text available for document {document_id}")
        return {"extracted_fields": None, "error": "No OCR text available"}

    detected_currency = map_currency_symbol_to_iso(raw_ocr_text)

    system_prompt = f"""You are an expert invoice data extraction system. Extract structured invoice fields from OCR text.

CRITICAL RULES:
1. NEVER infer or guess currency. Only extract currency if explicitly present as ISO 4217 code (USD, EUR, etc.) or currency symbol ($, €, £, etc.) that maps to a known ISO code.
2. If no explicit currency symbol/code is present, return null for currency and 0.0 confidence.
3. For dates, use YYYY-MM-DD format. If ambiguous, return null.
4. For monetary amounts, use decimal numbers.
5. Provide confidence scores (0.0-1.0) for each field based on clarity in the text.
6. If a field is not found or unclear, return null with 0.0 confidence.
7. CRITICAL FIELDS (must be present for valid invoice): invoice_number, vendor_name, total_amount

REQUIRED FIELD NAMES (Use these EXACTLY):
- invoice_number
- vendor_name, vendor_address, vendor_email, vendor_phone
- customer_name, customer_address, customer_phone, shipping_address
- invoice_date, due_date, currency
- subtotal, subtotal_amount, discount_amount, shipping_amount, tax_amount, tax_rate, total_amount
- payment_method
- line_items (Each item must have: description, quantity, unit_price, total, confidence_score)

DETECTED CURRENCY HINT: {detected_currency if detected_currency else 'None'}

Return JSON matching the ExtractedInvoiceFields schema exactly. Use a FLAT structure.
Example: {{"invoice_number": "INV-123", "invoice_number_confidence": 0.95}}
Do NOT use nested objects like {{"invoice_number": {{"value": "INV-123", "confidence": 0.95}}}}.
"""

    user_prompt = f"Extract invoice fields from this OCR text:\n\n{raw_ocr_text}"

    max_attempts = 3
    for attempt in range(max_attempts):
        try:
            client = Groq(api_key=settings.GROQ_API_KEY)

            # We use the Groq client which is synchronous, but we run it in a thread to avoid blocking the event loop
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: client.chat.completions.create(
                    model="openai/gpt-oss-120b",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.0,
                    response_format={"type": "json_object"}
                )
            )

            content = response.choices[0].message.content

            # Safety parsing for JSON
            if "```json" in content:
                match = re.search(r'```json\s*(.*?)\s*```', content, re.DOTALL)
                extracted_dict = json.loads(match.group(1)) if match else json.loads(content)
            elif "```" in content:
                match = re.search(r'```\s*(.*?)\s*```', content, re.DOTALL)
                extracted_dict = json.loads(match.group(1)) if match else json.loads(content)
            else:
                extracted_dict = json.loads(content)

            extracted_model = ExtractedInvoiceFields(**extracted_dict)

            if extracted_model.currency and not detected_currency:
                logger.warning(f"Currency {extracted_model.currency} extracted by LLM but not detected in raw text for document {document_id}")

            logger.info(f"Text model extraction completed for document {document_id}")
            return {"extracted_fields": extracted_model.model_dump()}

        except Exception as e:
            logger.warning(f"Text model extraction attempt {attempt + 1}/{max_attempts} failed for document {document_id}: {e}")
            if attempt < max_attempts - 1:
                await asyncio.sleep(2 ** attempt)
            else:
                logger.exception(f"Text model extraction failed after {max_attempts} attempts for document {document_id}")
                return {"extracted_fields": None, "error": str(e)}


async def confidence_check_node(state: ExtractionState) -> ExtractionState:
    """
    Check confidence of extracted fields.
    If critical fields have low confidence (< 0.7) or are null, route to vision model.
    """
    extracted = state.get("extracted_fields")

    if not extracted:
        logger.warning(f"No extracted fields from text model for document {state['document_id']}")
        return {"confidence_check_result": {"needs_vision": True, "reason": "No extracted fields"}}

    critical_fields = ["invoice_number", "vendor_name", "total_amount"]
    low_confidence = []
    null_fields = []

    for field in critical_fields:
        confidence_key = f"{field}_confidence"
        value = extracted.get(field)
        confidence = extracted.get(confidence_key, 0.0)

        if value is None:
            null_fields.append(field)
        elif confidence is not None and confidence < 0.7:
            low_confidence.append((field, confidence))

    needs_vision = len(null_fields) > 0 or len(low_confidence) > 0

    reason = ""
    if null_fields:
        reason += f"Null critical fields: {', '.join(null_fields)}. "
    if low_confidence:
        reason += f"Low confidence fields: {', '.join(f'{f} ({c:.2f})' for f, c in low_confidence)}. "

    result = {
        "needs_vision": needs_vision,
        "reason": reason.strip(),
        "null_fields": null_fields,
        "low_confidence": low_confidence
    }

    logger.info(f"Confidence check for document {state['document_id']}: needs_vision={needs_vision}, reason={reason}")

    return {"confidence_check_result": result}


async def vision_model_node(state: ExtractionState) -> ExtractionState:
    """
    Extract invoice fields using Google Gemini Vision model with the normalized image.
    Used as fallback when text model confidence is low.
    """
    import google.generativeai as genai

    document_id = state["document_id"]
    image_paths = state.get("normalized_image_paths", [])

    if not image_paths:
        logger.warning(f"No normalized images for document {document_id}")
        return {"vision_extracted_fields": None, "error": "No image available"}

    logger.info(f"Running vision model extraction for document {document_id}")

    max_attempts = 3
    for attempt in range(max_attempts):
        try:
            genai.configure(api_key=settings.GEMINI_API_KEY)
            model_id = settings.GEMINI_MODEL if settings.GEMINI_MODEL.startswith("models/") else f"models/{settings.GEMINI_MODEL}"
            model = genai.GenerativeModel(model_id)

            image_path = state["normalized_image_paths"][0]
            with open(image_path, "rb") as f:
                image_data = f.read()

            image_part = {
                "mime_type": "image/png",
                "data": image_data
            }

            prompt = """Extract invoice fields from this invoice image. Return JSON matching the schema.

CRITICAL RULES:
1. NEVER infer currency. Only extract if explicit ISO code (USD, EUR, etc.) or symbol ($, €, £) present.
2. If no explicit currency, return null for currency.
3. Dates in YYYY-MM-DD format.
4. Provide confidence scores (0.0-1.0) for each field.
5. Return null with 0.0 confidence for unclear/missing fields.
6. CRITICAL FIELDS: invoice_number, vendor_name, total_amount

FORMATTING RULES:
- Return a FLAT JSON object.
- Do NOT nest values and confidence.
- Correct: {"customer_name": "John Doe", "customer_name_confidence": 0.9}
- Incorrect: {"customer_name": {"value": "John Doe", "confidence": 0.9}}

REQUIRED FIELD NAMES (Use these EXACTLY):
- invoice_number
- vendor_name, vendor_address, vendor_email, vendor_phone
- customer_name, customer_address, customer_phone, shipping_address
- invoice_date, due_date, currency
- subtotal, subtotal_amount, discount_amount, shipping_amount, tax_amount, tax_rate, total_amount
- payment_method
- line_items (Each item must have: description, quantity, unit_price, total, confidence_score)

Return JSON matching the schema exactly."""

            response = model.generate_content([prompt, image_part], generation_config={
                "temperature": 0.0,
                "max_output_tokens": 4096,
                "response_mime_type": "application/json"
            })

            try:
                extracted_dict = json.loads(response.text)
            except json.JSONDecodeError:
                match = re.search(r'```json\s*(.*?)\s*```', response.text, re.DOTALL)
                if match:
                    extracted_dict = json.loads(match.group(1))
                else:
                    raise ValueError("Could not parse vision model response as JSON")

            # Validate using Pydantic schema
            extracted_model = ExtractedInvoiceFields(**extracted_dict)

            logger.info(f"Vision model extraction completed for document {document_id}")
            return {"vision_extracted_fields": extracted_model.model_dump()}

        except Exception as e:
            # Handle Quota/Rate Limit errors with longer delay
            delay = 2 ** attempt
            if "429" in str(e) or "quota" in str(e).lower():
                delay = 30 * (attempt + 1)
                logger.warning(f"Gemini quota exceeded. Increasing delay to {delay}s for document {document_id}")

            logger.warning(f"Vision model extraction attempt {attempt + 1}/{max_attempts} failed for document {document_id}: {e}")
            if attempt < max_attempts - 1:
                await asyncio.sleep(delay)
            else:
                logger.exception(f"Vision model extraction failed after {max_attempts} attempts for document {document_id}")
                return {"vision_extracted_fields": None, "error": str(e)}


async def merge_node(state: ExtractionState) -> ExtractionState:
    """
    Merge text and vision model results.
    Text model takes precedence unless vision model resolved a null field.
    """
    text_fields = state.get("extracted_fields") or {}
    vision_fields = state.get("vision_extracted_fields") or {}

    if not vision_fields:
        final = text_fields.copy()
        final["extraction_method"] = "text_model"
        logger.info(f"Using text model only for document {state['document_id']}")
        return {"final_extracted_fields": final}

    merged = text_fields.copy()
    for key in vision_fields:
        if key.endswith("_confidence"):
            continue
        text_value = merged.get(key)
        vision_value = vision_fields.get(key)
        if text_value is None and vision_value is not None:
            merged[key] = vision_value
            conf_key = f"{key}_confidence"
            if conf_key in vision_fields:
                merged[conf_key] = vision_fields[conf_key]

    merged["extraction_method"] = "merged_text_vision"
    logger.info(f"Merged text and vision results for document {state['document_id']}")

    return {"final_extracted_fields": merged}


def decimal_default(obj):
    """Custom JSON encoder for Decimal types."""
    if isinstance(obj, Decimal):
        return str(obj)
    raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable")


async def save_extracted_fields(state: ExtractionState) -> ExtractionState:
    """Save extracted fields to database and update document status/session."""
    document_id = state["document_id"]
    final_fields = state.get("final_extracted_fields", {})
    extraction_method = final_fields.pop("extraction_method", "text_model")

    SyncSessionLocal = sessionmaker(sync_engine, expire_on_commit=False)
    db = SyncSessionLocal()

    try:
        document = db.execute(select(Document).where(Document.id == uuid.UUID(state["document_id"]))).scalar_one_or_none()
        if not document:
            return {"error": "Document not found"}

        # 1. Update Document status to validating
        document.status = DocumentStatus.validating
        db.add(document)

        # 2. Update DocumentSession progress and stage_history
        result = db.execute(
            select(DocumentSession)
            .where(DocumentSession.document_id == uuid.UUID(state["document_id"]))
            .order_by(DocumentSession.updated_at.desc())
            .limit(1)
        )
        session = result.scalar_one_or_none()
        if session:
            session.current_stage = "extraction_complete"
            session.progress_percent = 50
            new_entry = {
                "stage": "extraction_complete",
                "progress": 50,
                "timestamp": datetime.utcnow().isoformat(),
                "message": "Field extraction completed and saved"
            }
            if session.stage_history is None:
                session.stage_history = []
            session.stage_history.append(new_entry)
            db.add(session)

        # 3. Clear and Save extracted fields
        from sqlalchemy import delete
        db.execute(delete(ExtractedField).where(ExtractedField.document_id == uuid.UUID(state["document_id"])))

        # Canonical field name is 'subtotal'. We prioritize it and drop 'subtotal_amount' to avoid duplicates.
        field_mapping = {
            "invoice_number": ("invoice_number", final_fields.get("invoice_number_confidence", 0.0), final_fields.get("invoice_number")),
            "vendor_name": ("vendor_name", final_fields.get("vendor_name_confidence", 0.0), final_fields.get("vendor_name")),
            "vendor_address": ("vendor_address", final_fields.get("vendor_address_confidence", 0.0), final_fields.get("vendor_address")),
            "vendor_email": ("vendor_email", final_fields.get("vendor_email_confidence", 0.0), final_fields.get("vendor_email")),
            "vendor_phone": ("vendor_phone", final_fields.get("vendor_phone_confidence", 0.0), final_fields.get("vendor_phone")),
            "customer_name": ("customer_name", final_fields.get("customer_name_confidence", 0.0), final_fields.get("customer_name")),
            "customer_address": ("customer_address", final_fields.get("customer_address_confidence", 0.0), final_fields.get("customer_address")),
            "customer_phone": ("customer_phone", final_fields.get("customer_phone_confidence", 0.0), final_fields.get("customer_phone")),
            "shipping_address": ("shipping_address", final_fields.get("shipping_address_confidence", 0.0), final_fields.get("shipping_address")),
            "payment_method": ("payment_method", final_fields.get("payment_method_confidence", 0.0), final_fields.get("payment_method")),
            "invoice_date": ("invoice_date", final_fields.get("invoice_date_confidence", 0.0), final_fields.get("invoice_date")),
            "due_date": ("due_date", final_fields.get("due_date_confidence", 0.0), final_fields.get("due_date")),
            "currency": ("currency", final_fields.get("currency_confidence", 0.0), final_fields.get("currency")),
            "subtotal": ("subtotal", final_fields.get("subtotal_confidence", 0.0), final_fields.get("subtotal") or final_fields.get("subtotal_amount")),
            "discount_amount": ("discount_amount", final_fields.get("discount_amount_confidence", 0.0), final_fields.get("discount_amount")),
            "shipping_amount": ("shipping_amount", final_fields.get("shipping_amount_confidence", 0.0), final_fields.get("shipping_amount")),
            "tax_amount": ("tax_amount", final_fields.get("tax_amount_confidence", 0.0), final_fields.get("tax_amount")),
            "tax_rate": ("tax_rate", final_fields.get("tax_rate_confidence", 0.0), final_fields.get("tax_rate")),
            "total_amount": ("total_amount", final_fields.get("total_amount_confidence", 0.0), final_fields.get("total_amount")),
        }

        for field_name, (db_field, confidence, value) in field_mapping.items():
            if value is not None:
                val_str = str(value) if not isinstance(value, (int, float, Decimal)) else f"{value:.4f}" if isinstance(value, (float, Decimal)) else str(value)

                db.add(ExtractedField(
                    document_id=uuid.UUID(state["document_id"]),
                    field_name=db_field,
                    field_value=val_str,
                    confidence_score=confidence,
                    extraction_method=extraction_method,
                ))

        line_items = final_fields.get("line_items", [])
        if line_items:
            line_items_confidence = final_fields.get("line_items_confidence", 0.0)
            for item in line_items:
                if isinstance(item, dict):
                    db.add(ExtractedField(
                        document_id= uuid.UUID(state["document_id"]),
                        field_name="line_items",
                        field_value=json.dumps(item, default=decimal_default),
                        confidence_score=line_items_confidence,
                        extraction_method=extraction_method,
                    ))

        db.commit()
        logger.info(f"Saved extracted fields and updated status for document {state['document_id']}")
    except Exception as e:
        logger.exception(f"Failed to save extracted fields for document {state['document_id']}: {e}")
        db.rollback()
    finally:
        db.close()

    return {"final_extracted_fields": state.get("final_extracted_fields", {})}


def route_after_confidence_check(state: ExtractionState) -> Literal["vision_model_node", "merge_node"]:
    result = state.get("confidence_check_result", {})
    return "vision_model_node" if result.get("needs_vision", False) else "merge_node"


def build_extraction_graph():
    graph = StateGraph(ExtractionState)
    graph.add_node("text_model_node", text_model_node)
    graph.add_node("confidence_check_node", confidence_check_node)
    graph.add_node("vision_model_node", vision_model_node)
    graph.add_node("merge_node", merge_node)
    graph.add_node("save_extracted_fields", save_extracted_fields)

    graph.add_edge(START, "text_model_node")
    graph.add_edge("text_model_node", "confidence_check_node")
    graph.add_conditional_edges(
        "confidence_check_node",
        route_after_confidence_check,
        {"vision_model_node": "vision_model_node", "merge_node": "merge_node"}
    )
    graph.add_edge("vision_model_node", "merge_node")
    graph.add_edge("merge_node", "save_extracted_fields")
    graph.add_edge("save_extracted_fields", END)

    return graph.compile(checkpointer=MemorySaver())

extraction_graph = build_extraction_graph()
