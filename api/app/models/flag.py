import enum
from sqlalchemy import String, ForeignKey, Float, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class DuplicateMatchType(str, enum.Enum):
    exact_key = "exact_key"
    fuzzy_match = "fuzzy_match"


class DuplicateFlag(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "duplicate_flags"

    document_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    duplicate_of_document_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    match_type: Mapped[DuplicateMatchType] = mapped_column(
        String(20),
        nullable=False,
    )
    confidence_score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    document: Mapped["Document"] = relationship(
        foreign_keys=[document_id],
        back_populates="duplicate_flags",
    )
    duplicate_of: Mapped["Document"] = relationship(
        foreign_keys=[duplicate_of_document_id],
    )

    __table_args__ = (
        Index("ix_duplicate_flags_doc_duplicate", "document_id", "duplicate_of_document_id"),
    )

    def __repr__(self) -> str:
        return f"<DuplicateFlag(id={self.id}, doc={self.document_id}, dup_of={self.duplicate_of_document_id})>"


class FraudFlagType(str, enum.Enum):
    bank_change = "bank_change"
    new_vendor_high_amount = "new_vendor_high_amount"
    round_number_threshold = "round_number_threshold"


class FraudFlag(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "fraud_flags"

    document_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    flag_type: Mapped[FraudFlagType] = mapped_column(
        String(40),
        nullable=False,
        index=True,
    )
    severity: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )
    details: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
    )

    document: Mapped["Document"] = relationship(back_populates="fraud_flags")

    __table_args__ = (
        Index("ix_fraud_flags_document_type", "document_id", "flag_type"),
    )

    def __repr__(self) -> str:
        return f"<FraudFlag(id={self.id}, document_id={self.document_id}, type={self.flag_type})>"