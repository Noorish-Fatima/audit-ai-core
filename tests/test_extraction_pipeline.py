import pytest
import asyncio
import uuid
from unittest.mock import MagicMock, patch
from api.app.agents.extraction_graph import extraction_graph, ExtractionState
from api.app.schemas.extraction import ExtractedInvoiceFields

@pytest.mark.asyncio
async def test_extraction_variants():
    # Scenario 1: Typed PDF - Text model succeeds with high confidence
    doc_id_1 = str(uuid.uuid4())
    state_1 = {
        "document_id": doc_id_1,
        "raw_ocr_text": "Invoice #INV-1001\nVendor: Acme Corp\nTotal: 100.00\nCurrency: USD",
        "normalized_image_paths": ["/tmp/img1.png"],
        "extracted_fields": None,
        "vision_extracted_fields": None,
        "final_extracted_fields": None,
        "confidence_check_result": None,
        "error": None,
        "retry_count": 0,
    }
    
    # Mock Groq to return high confidence
    mock_groq_resp = MagicMock()
    mock_groq_resp.choices = [MagicMock()]
    mock_groq_resp.choices[0].message.content = '{"invoice_number": "INV-1001", "vendor_name": "Acme Corp", "total_amount": 100.0, "invoice_number_confidence": 0.9, "vendor_name_confidence": 0.9, "total_amount_confidence": 0.9, "currency": "USD", "currency_confidence": 0.9}'
    
    with patch('app.agents.extraction_graph.Groq') as mock_groq, \
         patch('app.agents.extraction_graph.save_extracted_fields', return_value={"final_extracted_fields": {}}):
        mock_groq.return_value.chat.completions.create.return_value = mock_groq_resp
        
        result = await extraction_graph.ainvoke(state_1)
        # Should NOT trigger vision model
        assert result["vision_extracted_fields"] is None
        assert result["final_extracted_fields"]["invoice_number"] == "INV-1001"

    # Scenario 2: Low-quality scan - Text model fails/low confidence, Vision model succeeds
    doc_id_2 = str(uuid.uuid4())
    state_2 = {
        "document_id": doc_id_2,
        "raw_ocr_text": "Inv# ???\nVen: ???\nTot: 200.0",
        "normalized_image_paths": ["/tmp/img2.png"],
        "extracted_fields": None,
        "vision_extracted_fields": None,
        "final_extracted_fields": None,
        "confidence_check_result": None,
        "error": None,
        "retry_count": 0,
    }
    
    # Mock Groq to return low confidence
    mock_groq_low = MagicMock()
    mock_groq_low.choices = [MagicMock()]
    mock_groq_low.choices[0].message.content = '{"invoice_number": null, "vendor_name": null, "total_amount": 200.0, "invoice_number_confidence": 0.1, "vendor_name_confidence": 0.1, "total_amount_confidence": 0.8}'
    
    # Mock Gemini to return high confidence
    mock_gemini_resp = MagicMock()
    mock_gemini_resp.text = '{"invoice_number": "INV-2002", "vendor_name": "Globex", "total_amount": 200.0, "invoice_number_confidence": 0.9, "vendor_name_confidence": 0.9, "total_amount_confidence": 0.9}'
    
    with patch('app.agents.extraction_graph.Groq') as mock_groq, \
         patch('google.generativeai.GenerativeModel') as mock_gemini, \
         patch('app.agents.extraction_graph.save_extracted_fields', return_value={"final_extracted_fields": {}}):
        mock_groq.return_value.chat.completions.create.return_value = mock_groq_low
        mock_gemini.return_value.generate_content.return_value = mock_gemini_resp
        
        result = await extraction_graph.ainvoke(state_2)
        # Should trigger vision model
        assert result["vision_extracted_fields"] is not None
        assert result["final_extracted_fields"]["invoice_number"] == "INV-2002"

    # Scenario 3: No currency - Confirm no inference
    doc_id_3 = str(uuid.uuid4())
    state_3 = {
        "document_id": doc_id_3,
        "raw_ocr_text": "Invoice #INV-3003\nVendor: Stark Ind\nTotal: 300.00", # NO CURRENCY
        "normalized_image_paths": ["/tmp/img3.png"],
        "extracted_fields": None,
        "vision_extracted_fields": None,
        "final_extracted_fields": None,
        "confidence_check_result": None,
        "error": None,
        "retry_count": 0,
    }
    
    # Mock Groq to hallucinate USD
    mock_groq_hallucinate = MagicMock()
    mock_groq_hallucinate.choices = [MagicMock()]
    mock_groq_hallucinate.choices[0].message.content = '{"invoice_number": "INV-3003", "vendor_name": "Stark Ind", "total_amount": 300.0, "invoice_number_confidence": 0.9, "vendor_name_confidence": 0.9, "total_amount_confidence": 0.9, "currency": "USD", "currency_confidence": 0.9}'
    
    with patch('app.agents.extraction_graph.Groq') as mock_groq, \
         patch('app.agents.extraction_graph.save_extracted_fields', return_value={"final_extracted_fields": {}}):
        mock_groq.return_value.chat.completions.create.return_value = mock_groq_hallucinate
        
        result = await extraction_graph.ainvoke(state_3)
        # Currency should be null because it wasn't in raw_ocr_text
        assert result["final_extracted_fields"]["currency"] is None
