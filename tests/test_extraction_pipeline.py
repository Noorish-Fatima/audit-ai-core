"""Extraction pipeline variants — all LLM provider calls are mocked.

No test in this file may make a live Groq/Gemini call. The Groq client is
constructed inside text_model_node (``from groq import Groq``), so the correct
patch target is ``groq.Groq``. The Gemini model is constructed inside
vision_model_node (``import google.generativeai as genai``), so the correct
target is ``google.generativeai.GenerativeModel``.

We exercise the graph nodes directly (text -> confidence -> vision -> merge)
instead of invoking the compiled graph end-to-end, because the terminal
``save_extracted_fields`` node requires a live Postgres database.
"""
import uuid
from unittest.mock import MagicMock, mock_open, patch

import pytest

from app.agents.extraction_graph import (
    confidence_check_node,
    merge_node,
    text_model_node,
    vision_model_node,
)


def _groq_response(payload_json: str):
    resp = MagicMock()
    choice = MagicMock()
    choice.message.content = payload_json
    resp.choices = [choice]
    return resp


@pytest.mark.asyncio
async def test_extraction_variants():
    # Scenario 1: Typed PDF - text model succeeds with high confidence,
    # no vision fallback needed.
    state_1 = {
        "document_id": str(uuid.uuid4()),
        "raw_ocr_text": "Invoice #INV-1001\nVendor: Acme Corp\nTotal: $100.00\nCurrency: USD",
        "normalized_image_paths": [],
    }
    groq_high = _groq_response(
        '{"invoice_number": "INV-1001", "vendor_name": "Acme Corp", '
        '"total_amount": 100.0, "invoice_number_confidence": 0.9, '
        '"vendor_name_confidence": 0.9, "total_amount_confidence": 0.9, '
        '"currency": "USD", "currency_confidence": 0.9}'
    )
    with patch("groq.Groq") as mock_groq:
        mock_groq.return_value.chat.completions.create.return_value = groq_high
        text_out = await text_model_node(state_1)
    assert text_out["extracted_fields"]["invoice_number"] == "INV-1001"

    conf_1 = await confidence_check_node(
        {"document_id": state_1["document_id"], "extracted_fields": text_out["extracted_fields"]}
    )
    assert conf_1["confidence_check_result"]["needs_vision"] is False

    merged_1 = await merge_node(
        {
            "document_id": state_1["document_id"],
            "extracted_fields": text_out["extracted_fields"],
            "vision_extracted_fields": None,
        }
    )
    assert merged_1["final_extracted_fields"]["invoice_number"] == "INV-1001"
    assert merged_1["final_extracted_fields"]["extraction_method"] == "text_model"

    # Scenario 2: low-quality scan - low text confidence triggers vision,
    # vision fills the nulls and merge takes the vision values.
    state_2 = {
        "document_id": str(uuid.uuid4()),
        "raw_ocr_text": "Inv# ???\nVen: ???\nTot: 200.0",
        "normalized_image_paths": ["/tmp/img2.png"],
    }
    groq_low = _groq_response(
        '{"invoice_number": null, "vendor_name": null, "total_amount": 200.0, '
        '"invoice_number_confidence": 0.1, "vendor_name_confidence": 0.1, '
        '"total_amount_confidence": 0.8}'
    )
    with patch("groq.Groq") as mock_groq:
        mock_groq.return_value.chat.completions.create.return_value = groq_low
        text_out_2 = await text_model_node(state_2)

    conf_2 = await confidence_check_node(
        {"document_id": state_2["document_id"], "extracted_fields": text_out_2["extracted_fields"]}
    )
    assert conf_2["confidence_check_result"]["needs_vision"] is True

    gemini_resp = MagicMock()
    gemini_resp.text = (
        '{"invoice_number": "INV-2002", "vendor_name": "Globex", '
        '"total_amount": 200.0, "invoice_number_confidence": 0.9, '
        '"vendor_name_confidence": 0.9, "total_amount_confidence": 0.9}'
    )
    with (
        patch("google.generativeai.GenerativeModel") as mock_gemini,
        patch("builtins.open", mock_open(read_data=b"fake-png-bytes")),
    ):
        mock_gemini.return_value.generate_content.return_value = gemini_resp
        vision_out = await vision_model_node(
            {
                "document_id": state_2["document_id"],
                "normalized_image_paths": state_2["normalized_image_paths"],
            }
        )
    assert vision_out["vision_extracted_fields"] is not None
    assert vision_out["vision_extracted_fields"]["invoice_number"] == "INV-2002"

    merged_2 = await merge_node(
        {
            "document_id": state_2["document_id"],
            "extracted_fields": text_out_2["extracted_fields"],
            "vision_extracted_fields": vision_out["vision_extracted_fields"],
        }
    )
    assert merged_2["final_extracted_fields"]["invoice_number"] == "INV-2002"

    # Scenario 3: no currency in source - hallucinated currency is nulled
    # by the no-inference policy even though the (mocked) LLM returns USD.
    state_3 = {
        "document_id": str(uuid.uuid4()),
        "raw_ocr_text": "Invoice #INV-3003\nVendor: Stark Ind\nTotal: 300.00",
        "normalized_image_paths": [],
    }
    groq_hallucinate = _groq_response(
        '{"invoice_number": "INV-3003", "vendor_name": "Stark Ind", '
        '"total_amount": 300.0, "invoice_number_confidence": 0.9, '
        '"vendor_name_confidence": 0.9, "total_amount_confidence": 0.9, '
        '"currency": "USD", "currency_confidence": 0.9}'
    )
    with patch("groq.Groq") as mock_groq:
        mock_groq.return_value.chat.completions.create.return_value = groq_hallucinate
        text_out_3 = await text_model_node(state_3)
    assert text_out_3["extracted_fields"]["currency"] is None
