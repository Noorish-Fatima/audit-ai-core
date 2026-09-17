import enum
from datetime import datetime
from typing import Optional
from sqlalchemy import String, ForeignKey, Float, Boolean, DateTime, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class ExtractionMethod(str, enum.Enum):
    text_model = "text_model"
    vision_model = "vision_model"
    ocr_only = "ocr_only"


class ExtractedField(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "extracted_fields"

    document_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    field_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    field_value: Mapped[str] = mapped_column(
        String(5000),
        nullable=False,
    )
    confidence_score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    extraction_method: Mapped[ExtractionMethod] = mapped_column(
        String(20),
        nullable=False,
    )
    is_corrected: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    original_value: Mapped[Optional[str]] = mapped_column(
        String(5000),
        nullable=True,
    )
    corrected_by: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    corrected_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    document: Mapped["Document"] = relationship(back_populates="extracted_fields")

    __table_args__ = (
        Index("ix_extracted_fields_document_field", "document_id", "field_name"),
    )

    def __repr__(self) -> str:
        return f"<ExtractedField(id={self.id}, document_id={self.document_id}, field={self.field_name})>"