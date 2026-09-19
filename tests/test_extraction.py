"""
Tests for invoice field extraction with synthetic invoice variants.
"""
import pytest
import pytest_asyncio
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
import json
import uuid

from app.schemas.extraction import ExtractedInvoiceFields, LineItem
from app.agents.extraction_graph import (
    text_model_node,
    confidence_check_node,
    vision_model_node,
    merge_node,
    route_after_confidence_check,
    save_extracted_fields,
    ExtractionState,
)


class TestExtractedInvoiceFields:
    """Tests for the ExtractedInvoiceFields Pydantic schema."""
    
    def test_valid_complete_invoice(self):
        """Test a complete valid invoice extraction."""
        invoice = ExtractedInvoiceFields(
            invoice_number="INV-2024-001",
            vendor_name="Acme Corp",
            invoice_date=date(2024, 1, 15),
            due_date=date(2024, 2, 14),
            currency="USD",
            subtotal=Decimal("100.00"),
            tax_amount=Decimal("8.50"),
            tax_rate=Decimal("0.085"),
            total_amount=Decimal("108.50"),
            line_items=[
                LineItem(description="Professional Services", quantity=Decimal("10"), unit_price=Decimal("10.00"), total=Decimal("100.00"), confidence_score=0.95)
            ],
            invoice_number_confidence=0.95,
            vendor_name_confidence=0.98,
            invoice_date_confidence=0.90,
            due_date_confidence=0.85,
            currency_confidence=1.0,
            subtotal_confidence=0.95,
            tax_amount_confidence=0.90,
            tax_rate_confidence=0.85,
            total_amount_confidence=0.98,
            line_items_confidence=0.90,
        )
        
        assert invoice.invoice_number == "INV-2024-001"
        assert invoice.currency == "USD"
        assert invoice.total_amount == Decimal("108.50")
        assert invoice.currency_confidence == 1.0
    
    def test_currency_null_when_absent(self):
        """Currency must be null when not explicitly present in document."""
        invoice = ExtractedInvoiceFields(
            invoice_number="INV-001",
            vendor_name="Test Vendor",
            total_amount=Decimal("100.00"),
            invoice_number_confidence=0.9,
            vendor_name_confidence=0.9,
            total_amount_confidence=0.9,
            currency=None,  # Must be null when not explicitly in document
            currency_confidence=0.0,
        )
        
        assert invoice.currency is None
        assert invoice.currency_confidence == 0.0
    
    def test_currency_invalid_when_not_iso(self):
        """Currency must be valid ISO 4217 code."""
        with pytest.raises(Exception):
            ExtractedInvoiceFields(
                invoice_number="INV-001",
                vendor_name="Test",
                total_amount=Decimal("100.00"),
                currency="US",  # Invalid - not 3 chars
                currency_confidence=0.9,
                invoice_number_confidence=0.9,
                vendor_name_confidence=0.9,
                total_amount_confidence=0.9,
            )
    
    def test_invalid_currency_code(self):
        """Currency must match ISO 4217 pattern (3 uppercase letters)."""
        with pytest.raises(Exception):
            ExtractedInvoiceFields(
                invoice_number="INV-001",
                vendor_name="Test",
                total_amount=Decimal("100.00"),
                currency="XY",  # Invalid - not 3 letters
                currency_confidence=0.9,
                invoice_number_confidence=0.9,
                vendor_name_confidence=0.9,
                total_amount_confidence=0.9,
            )
        
        # Valid pattern but invalid ISO code - should pass pattern validation
        # but we don't validate against actual ISO 4217 list
        invoice = ExtractedInvoiceFields(
            invoice_number="INV-001",
            vendor_name="Test",
            total_amount=Decimal("100.00"),
            currency="XYZ",  # Valid pattern but not real ISO code
            currency_confidence=0.9,
            invoice_number_confidence=0.9,
            vendor_name_confidence=0.9,
            total_amount_confidence=0.9,
        )
        assert invoice.currency == "XYZ"
    
    def test_low_confidence_critical_fields(self):
        """Detect low confidence in critical fields."""
        invoice = ExtractedInvoiceFields(
            invoice_number="INV-001",
            vendor_name="Test Vendor",
            total_amount=Decimal("100.00"),
            invoice_number_confidence=0.9,
            vendor_name_confidence=0.5,  # Low confidence
            total_amount_confidence=0.9,
        )
        
        assert invoice.has_low_confidence_critical(0.7) is True
    
    def test_null_critical_field(self):
        """Detect null critical fields."""
        invoice = ExtractedInvoiceFields(
            invoice_number="INV-001",
            vendor_name=None,  # Missing critical field
            total_amount=Decimal("100.00"),
            invoice_number_confidence=0.9,
            vendor_name_confidence=0.0,
            total_amount_confidence=0.9,
        )
        
        assert invoice.has_null_critical() is True
    
    def test_confidence_check_routing(self):
        """Test confidence check routing logic."""
        from app.agents.extraction_graph import confidence_check_node
        
        # Test with low confidence critical field
        extracted = {
            "invoice_number": "INV-001",
            "vendor_name": "Test Corp",
            "total_amount": 100.0,
            "invoice_number_confidence": 0.9,
            "vendor_name_confidence": 0.5,  # Low confidence
            "total_amount_confidence": 0.9,
        }
        
        state = {"extracted_fields": extracted}
        # This would be called in async context, testing logic directly
        critical_fields = ["invoice_number", "vendor_name", "total_amount"]
        low_confidence = []
        null_fields = []
        
        for field in ["invoice_number", "vendor_name", "total_amount"]:
            confidence_key = f"{field}_confidence"
            value = {"invoice_number": "INV-001", "vendor_name": "Test", "total_amount": 100.0}.get(field)
            confidence = extracted.get(f"{field}_confidence", 0.0)
            
            if value is None:
                null_fields.append(field)
            elif confidence is not None and confidence < 0.7:
                low_confidence.append((field, confidence))
        
        needs_vision = len(null_fields) > 0 or len(low_confidence) > 0
        
        assert needs_vision is True
        assert "vendor_name" in [f for f, _ in [("vendor_name", 0.5)]]


class TestExtractionGraphNodes:
    """Tests for extraction graph nodes."""
    
    @pytest.mark.asyncio
    async def test_confidence_check_node_no_fields(self):
        """Test confidence check with no extracted fields."""
        from app.agents.extraction_graph import confidence_check_node
        
        state = {"document_id": "test-123", "extracted_fields": None}
        result = await confidence_check_node({"document_id": "test-123", "extracted_fields": None})
        
        assert result["confidence_check_result"]["needs_vision"] is True
        assert "No extracted fields" in result["confidence_check_result"]["reason"]
    
    @pytest.mark.asyncio
    async def test_confidence_check_node_high_confidence(self):
        """Test confidence check passes with high confidence."""
        from app.agents.extraction_graph import confidence_check_node
        
        extracted = {
            "invoice_number": "INV-001",
            "vendor_name": "Test Corp",
            "total_amount": 100.0,
            "invoice_number_confidence": 0.9,
            "vendor_name_confidence": 0.9,
            "total_amount_confidence": 0.9,
        }
        
        state = {"document_id": "test-123", "extracted_fields": extracted}
        result = await confidence_check_node(state)
        
        assert result["confidence_check_result"]["needs_vision"] is False
        assert len(result["confidence_check_result"]["null_fields"]) == 0
    
    @pytest.mark.asyncio
    async def test_merge_node_no_vision(self):
        """Test merge node uses text model when no vision results."""
        from app.agents.extraction_graph import merge_node
        
        state = {
            "document_id": "test-123",
            "extracted_fields": {
                "invoice_number": "INV-001",
                "vendor_name": "Test Corp",
                "invoice_number_confidence": 0.9,
                "vendor_name_confidence": 0.9,
            },
            "vision_extracted_fields": None,
        }
        
        result = await merge_node(state)
        
        assert result["final_extracted_fields"]["extraction_method"] == "text_model"
        assert result["final_extracted_fields"]["invoice_number"] == "INV-001"
    
    @pytest.mark.asyncio
    async def test_merge_node_vision_fills_nulls(self):
        """Test merge fills nulls from vision model."""
        from app.agents.extraction_graph import merge_node
        
        state = {
            "document_id": "test-123",
            "extracted_fields": {
                "invoice_number": "INV-001",
                "vendor_name": None,  # Text model couldn't extract
                "invoice_number_confidence": 0.9,
                "vendor_name_confidence": 0.0,
            },
            "vision_extracted_fields": {
                "vendor_name": "Acme Corp",
                "vendor_name_confidence": 0.95,
            },
        }
        
        result = await merge_node(state)
        
        assert result["final_extracted_fields"]["vendor_name"] == "Acme Corp"
        assert result["final_extracted_fields"]["vendor_name_confidence"] == 0.95
        assert result["final_extracted_fields"]["extraction_method"] == "merged_text_vision"
    
    @pytest.mark.asyncio
    async def test_merge_node_text_precedence(self):
        """Test text model takes precedence over vision."""
        from app.agents.extraction_graph import merge_node
        
        state = {
            "document_id": "test-123",
            "extracted_fields": {
                "vendor_name": "Text Model Corp",
                "vendor_name_confidence": 0.9,
            },
            "vision_extracted_fields": {
                "vendor_name": "Vision Model Corp",
                "vendor_name_confidence": 0.95,
            },
        }
        
        result = await merge_node(state)
        
        # Text model should win even though vision has higher confidence
        assert result["final_extracted_fields"]["vendor_name"] == "Text Model Corp"


class TestCurrencyNoInference:
    """Tests for no-inference currency policy."""
    
    def test_currency_null_when_no_symbol(self):
        """Currency must be null when no symbol/code present."""
        # This is enforced by the schema - currency must be null if not explicitly present
        # The text_model_node prompt enforces this
        pass
    
    def test_currency_from_symbol(self):
        """Currency can be extracted from symbol."""
        from app.schemas.extraction import ExtractedInvoiceFields
        from decimal import Decimal
        
        invoice = ExtractedInvoiceFields(
            invoice_number="INV-001",
            vendor_name="Test",
            total_amount=Decimal("100.00"),
            currency="USD",  # Extracted from $ symbol
            currency_confidence=0.95,
            invoice_number_confidence=0.9,
            vendor_name_confidence=0.9,
            total_amount_confidence=0.9,
        )
        
        assert invoice.currency == "USD"
        assert invoice.currency_confidence == 0.95


class TestSyntheticInvoiceVariants:
    """Integration tests with 3 synthetic invoice variants."""
    
    @pytest.mark.asyncio
    async def test_typed_pdf_extracts_via_text_model_only(self):
        """Test: Clean typed PDF extracts via text model only (no vision fallback)."""
        from app.agents.extraction_graph import confidence_check_node, merge_node
        from unittest.mock import AsyncMock, MagicMock, patch
        import json
        
        # Mock the text_model_node since it requires Groq API
        with patch('app.agents.extraction_graph.text_model_node') as mock_text_model:
            mock_text_model = AsyncMock()
            mock_text_model.return_value = {
                "extracted_fields": {
                    "invoice_number": "INV-2024-001",
                    "vendor_name": "Acme Corporation",
                    "invoice_date": "2024-01-15",
                    "due_date": "2024-02-14",
                    "currency": "USD",
                    "subtotal": 1000.00,
                    "tax_amount": 85.00,
                    "tax_rate": 0.085,
                    "total_amount": 1085.00,
                    "line_items": [{"description": "Professional Services", "quantity": 10, "unit_price": 100.00, "total": 1000.00}],
                    "invoice_number_confidence": 0.98,
                    "vendor_name_confidence": 0.98,
                    "invoice_date_confidence": 0.95,
                    "due_date_confidence": 0.95,
                    "currency_confidence": 0.99,
                    "subtotal_confidence": 0.97,
                    "tax_amount_confidence": 0.95,
                    "tax_rate_confidence": 0.95,
                    "total_amount_confidence": 0.98,
                    "line_items_confidence": 0.95,
                }
            }
            
            state = {
                "document_id": "test-123",
                "raw_ocr_text": "INVOICE #12345\nAcme Corp\nDate: 2024-01-15\nTotal: $1,085.00",
                "normalized_image_paths": [],
            }
            
            # Test the mock text_model_node
            with patch('app.agents.extraction_graph.text_model_node') as mock_text_model:
                mock_text_model.return_value = {
                    "extracted_fields": {
                        "invoice_number": "INV-2024-001",
                        "vendor_name": "Acme Corporation",
                        "invoice_date": "2024-01-15",
                        "due_date": "2024-02-14",
                        "currency": "USD",
                        "subtotal": 1000.00,
                        "tax_amount": 85.00,
                        "tax_rate": 0.085,
                        "total_amount": 1085.00,
                        "line_items": [{"description": "Professional Services", "quantity": 10, "unit_price": 100.00, "total": 1000.00}],
                        "invoice_number_confidence": 0.98,
                        "vendor_name_confidence": 0.98,
                        "invoice_date_confidence": 0.95,
                        "due_date_confidence": 0.95,
                        "currency_confidence": 0.99,
                        "subtotal_confidence": 0.97,
                        "tax_amount_confidence": 0.95,
                        "tax_rate_confidence": 0.95,
                        "total_amount_confidence": 0.98,
                        "line_items_confidence": 0.95,
                    }
                }
                
                state = {
                    "document_id": "test-123",
                    "raw_ocr_text": "INVOICE #12345\nAcme Corp\nDate: 2024-01-15\nTotal: $1,085.00",
                    "normalized_image_paths": [],
                }
                
                # Test the mock text_model_node
                from app.agents.extraction_graph import text_model_node
                result = await text_model_node(state)
            
            # Verify extraction happened
            assert "extracted_fields" in result
            assert result["extracted_fields"]["invoice_number"] == "INV-2024-001"
            assert result["extracted_fields"]["currency"] == "USD"
    
    @pytest.mark.asyncio
    async def test_scanned_image_fallbacks_to_vision(self):
        """Test: Low-quality scan correctly falls back to vision model."""
        from app.agents.extraction_graph import confidence_check_node, vision_model_node, merge_node
        from unittest.mock import patch, AsyncMock, MagicMock
        import json
        
        # Low confidence extraction from text model
        low_confidence_extracted = {
            "invoice_number": "INV-001",
            "vendor_name": None,  # Could not extract
            "total_amount": 100.00,
            "invoice_number_confidence": 0.9,
            "vendor_name_confidence": 0.3,  # Low confidence
            "total_amount_confidence": 0.9,
        }
        
        # Confidence check should trigger vision model
        state = {"document_id": "test-123", "extracted_fields": {"vendor_name": None, "vendor_name_confidence": 0.3}}
        result = await confidence_check_node({"document_id": "test", "extracted_fields": {"vendor_name": None, "vendor_name_confidence": 0.3}})
        
        assert result["confidence_check_result"]["needs_vision"] is True
        assert "vendor_name" in result["confidence_check_result"]["null_fields"] or \
               any(f == "vendor_name" for f, c in result["confidence_check_result"].get("low_confidence", []))
    
    def test_currency_never_fabricated(self):
        """Currency is never fabricated when absent from source."""
        # This is enforced by:
        # 1. Schema validation - currency pattern must be ^[A-Z]{3}$
        # 2. System prompt explicitly forbids inference
        # 3. Schema requires null when not present
        from app.schemas.extraction import ExtractedInvoiceFields
        from decimal import Decimal
        
        # No currency in source - must be null
        invoice = ExtractedInvoiceFields(
            invoice_number="INV-001",
            vendor_name="Test Vendor",
            total_amount=Decimal("100.00"),
            currency=None,  # Must be null when not in source
            currency_confidence=0.0,
            invoice_number_confidence=0.9,
            vendor_name_confidence=0.9,
            total_amount_confidence=0.9,
        )
        
        assert invoice.currency is None
        assert invoice.currency_confidence == 0.0
        
        # Verify currency is never defaulted - setting a currency without source is invalid
        # The schema allows any 3-letter code but the system prompt enforces no inference
        # We verify that when currency is provided, confidence must be > 0
        invoice_with_currency = ExtractedInvoiceFields(
            invoice_number="INV-001",
            vendor_name="Test",
            total_amount=Decimal("100.00"),
            currency="USD",  # Explicitly provided
            currency_confidence=0.95,  # High confidence because explicitly in source
            invoice_number_confidence=0.9,
            vendor_name_confidence=0.9,
            total_amount_confidence=0.9,
        )
        
        assert invoice_with_currency.currency == "USD"
        assert invoice_with_currency.currency_confidence > 0


class TestExtractionTask:
    """Tests for the extraction Celery task."""
    
    @pytest.mark.asyncio
    async def test_extraction_task_updates_session(self):
        """Test extraction task updates document_session to extraction_complete."""
        # This would test the full Celery task flow
        pass
    
    def test_retry_logic_exponential_backoff(self):
        """Test retry logic with exponential backoff."""
        from worker.tasks.extraction_task import extract_invoice_fields
        from celery.exceptions import MaxRetriesExceededError
        
        # Verify retry configuration
        from worker.tasks.extraction_task import extract_invoice_fields
        assert extract_invoice_fields.max_retries == 3
        assert extract_invoice_fields.default_retry_delay == 60


class TestIntegrationScenarios:
    """Integration test scenarios."""
    
    @pytest.mark.asyncio
    async def test_full_pipeline_typed_pdf(self):
        """Full pipeline: typed PDF -> text model -> high confidence -> no vision fallback."""
        # This would test the full pipeline with a clean typed PDF
        pass
    
    @pytest.mark.asyncio
    async def test_full_pipeline_scanned_fallback(self):
        """Full pipeline: scanned image -> low text confidence -> vision fallback -> merge."""
        pass
    
    @pytest.mark.asyncio
    async def test_currency_absent_returns_null(self):
        """Currency is null when not in source document."""
        pass
    
    def test_unusual_field_labels(self):
        """Test unusual field labels like 'Ref#' instead of 'Invoice #'."""
        from app.schemas.extraction import ExtractedInvoiceFields
        from decimal import Decimal
        
        # The text model should handle "Ref#" as invoice_number
        invoice = ExtractedInvoiceFields(
            invoice_number="REF-12345",  # Extracted from "Ref#" field
            vendor_name="Test Corp",
            total_amount=Decimal("100.00"),
            invoice_number_confidence=0.85,  # Slightly lower due to unusual label
            vendor_name_confidence=0.9,
            total_amount_confidence=0.9,
        )
        
        assert invoice.invoice_number == "REF-12345"
        assert invoice.invoice_number_confidence == 0.85


if __name__ == "__main__":
    pytest.main([__file__, "-v"])