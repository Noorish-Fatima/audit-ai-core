from typing import Optional, List, Literal
from pydantic import BaseModel, Field, ConfigDict
from datetime import date
from decimal import Decimal


class LineItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    description: str = Field(..., description="Line item description")
    quantity: Optional[Decimal] = Field(None, description="Quantity")
    unit_price: Optional[Decimal] = Field(None, description="Unit price")
    total: Optional[Decimal] = Field(None, description="Line total")
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="Confidence score 0.0-1.0")


class ExtractedInvoiceFields(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    invoice_number: Optional[str] = Field(None, description="Invoice number/identifier")
    invoice_number_confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    vendor_name: Optional[str] = Field(None, description="Vendor/supplier name")
    vendor_name_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    vendor_address: Optional[str] = Field(None, description="Vendor address")
    vendor_address_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    vendor_email: Optional[str] = Field(None, description="Vendor email")
    vendor_email_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    vendor_phone: Optional[str] = Field(None, description="Vendor phone number")
    vendor_phone_confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    customer_name: Optional[str] = Field(None, description="Customer/client name")
    customer_name_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    customer_address: Optional[str] = Field(None, description="Customer address")
    customer_address_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    customer_phone: Optional[str] = Field(None, description="Customer phone number")
    customer_phone_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    shipping_address: Optional[str] = Field(None, description="Shipping address")
    shipping_address_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    payment_method: Optional[str] = Field(None, description="Payment method used")
    payment_method_confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    invoice_date: Optional[date] = Field(None, description="Invoice date")
    invoice_date_confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    due_date: Optional[date] = Field(None, description="Payment due date")
    due_date_confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    currency: Optional[str] = Field(
        None,
        description="Currency ISO 4217 code (e.g., USD, EUR). Must be explicitly present in document - never inferred. If absent, return null.",
        pattern=r"^[A-Z]{3}$"
    )
    currency_confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    subtotal: Optional[Decimal] = Field(None, description="Subtotal before tax")
    subtotal_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    subtotal_amount: Optional[Decimal] = Field(None, description="Subtotal amount (alternative field)")
    subtotal_amount_confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    discount_amount: Optional[Decimal] = Field(None, description="Discount amount")
    discount_amount_confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    shipping_amount: Optional[Decimal] = Field(None, description="Shipping and handling amount")
    shipping_amount_confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    tax_amount: Optional[Decimal] = Field(None, description="Tax amount")
    tax_amount_confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    tax_rate: Optional[Decimal] = Field(None, description="Tax rate as decimal (e.g., 0.085 for 8.5%)")
    tax_rate_confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    total_amount: Optional[Decimal] = Field(None, description="Total amount due")
    total_amount_confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    line_items: List[LineItem] = Field(default_factory=list, description="Line items")
    line_items_confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    def get_critical_fields_confidence(self) -> dict:
        """Return confidence scores for critical fields only."""
        return {
            "invoice_number": self.invoice_number_confidence,
            "vendor_name": self.vendor_name_confidence,
            "total_amount": self.total_amount_confidence,
        }

    def has_low_confidence_critical(self, threshold: float = 0.7) -> bool:
        """Check if any critical field has confidence below threshold."""
        critical = self.get_critical_fields_confidence()
        return any(v < threshold for v in critical.values() if v is not None)

    def has_null_critical(self) -> bool:
        """Check if any critical field is null/missing."""
        return any(
            getattr(self, field) is None
            for field in ["invoice_number", "vendor_name", "total_amount"]
        )

    def to_extracted_fields_list(self, document_id: str, extraction_method: str) -> list:
        """Convert to list of ExtractedField model dicts for database insertion."""
        fields = []

        field_mapping = {
            "invoice_number": ("invoice_number", self.invoice_number_confidence, self.invoice_number),
            "vendor_name": ("vendor_name", self.vendor_name_confidence, self.vendor_name),
            "vendor_address": ("vendor_address", self.vendor_address_confidence, self.vendor_address),
            "vendor_email": ("vendor_email", self.vendor_email_confidence, self.vendor_email),
            "vendor_phone": ("vendor_phone", self.vendor_phone_confidence, self.vendor_phone),
            "customer_name": ("customer_name", self.customer_name_confidence, self.customer_name),
            "customer_address": ("customer_address", self.customer_address_confidence, self.customer_address),
            "customer_phone": ("customer_phone", self.customer_phone_confidence, self.customer_phone),
            "shipping_address": ("shipping_address", self.shipping_address_confidence, self.shipping_address),
            "payment_method": ("payment_method", self.payment_method_confidence, self.payment_method),
            "invoice_date": ("invoice_date", self.invoice_date_confidence, self.invoice_date.isoformat() if self.invoice_date else None),
            "due_date": ("due_date", self.due_date_confidence, self.due_date.isoformat() if self.due_date else None),
            "currency": ("currency", self.currency_confidence, self.currency),
            "subtotal": ("subtotal", self.subtotal_confidence, str(self.subtotal) if self.subtotal else None),
            "subtotal_amount": ("subtotal_amount", self.subtotal_amount_confidence, str(self.subtotal_amount) if self.subtotal_amount else None),
            "discount_amount": ("discount_amount", self.discount_amount_confidence, str(self.discount_amount) if self.discount_amount else None),
            "shipping_amount": ("shipping_amount", self.shipping_amount_confidence, str(self.shipping_amount) if self.shipping_amount else None),
            "tax_amount": ("tax_amount", self.tax_amount_confidence, str(self.tax_amount) if self.tax_amount else None),
            "tax_rate": ("tax_rate", self.tax_rate_confidence, str(self.tax_rate) if self.tax_rate else None),
            "total_amount": ("total_amount", self.total_amount_confidence, str(self.total_amount) if self.total_amount else None),
            "line_items": ("line_items", self.line_items_confidence, self.line_items if self.line_items else None),
        }

        for field_name, (db_field, confidence, value) in field_mapping.items():
            if value is not None:
                fields.append({
                    "document_id": None,  # Will be set by caller
                    "field_name": db_field,
                    "field_value": str(value) if not isinstance(value, list) else str(value),
                    "confidence_score": confidence,
                    "extraction_method": "text_model",  # Will be overridden by caller
                })

        return fields
