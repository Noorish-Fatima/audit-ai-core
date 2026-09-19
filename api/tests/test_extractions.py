import pytest
import json
from unittest.mock import MagicMock, patch
from api.app.agents.extraction_graph import build_extraction_graph

# Synthetic invoices for test cases
INVOICE_1_TYPED = {
    "invoice_number": "INV-001",
    "vendor_name": "ACME Corp",
    "total_amount": 100.0,
    "invoice_number_confidence": 0.95,
    "vendor_name_confidence": 0.98,
    "total_amount_confidence": 0.99
}

INVOICE_2_SCANNED = {
    "invoice_number": "INV-002",
    "vendor_name": "Globex Inc",
    "total_amount": 250.0,
    "invoice_number_confidence": 0.5, # Trigger fallback
    "vendor_name_confidence": 0.8,
    "total_amount_confidence": 0.8
}

@pytest.mark.asyncio
async def test_extraction_pipeline():
    # We test the graph nodes and logic, relying on the graph's structure
    
    state = {
        "document_id": "test-doc-1",
        "raw_ocr_text": "text",
        "normalized_image_paths": [],
        "extracted_fields": INVOICE_1_TYPED,
        "vision_extracted_fields": None,
        "final_extracted_fields": None,
        "confidence_check_result": None,
        "error": None,
        "retry_count": 0,
    }
    
    # Run confidence check directly as it's the gatekeeper
    from api.app.agents.extraction_graph import confidence_check_node
    result = confidence_check_node(state)
    assert result["confidence_check_result"]["needs_vision"] == False
    
    # Test Fallback
    state_2 = state.copy()
    state_2["extracted_fields"] = INVOICE_2_SCANNED
    result_2 = confidence_check_node(state_2)
    assert result_2["confidence_check_result"]["needs_vision"] == True
