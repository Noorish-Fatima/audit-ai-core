from datetime import datetime
from typing import Optional, List
from sqlalchemy import String, Boolean, ForeignKey, DateTime, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class Vendor(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "vendors"

    canonical_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )
    aliases: Mapped[List[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
    )
    tax_id: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        index=True,
    )
    is_approved: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    is_new: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )
    bank_account_last4: Mapped[Optional[str]] = mapped_column(
        String(4),
        nullable=True,
    )
    bank_account_hash: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
    )

    bank_history: Mapped[List["VendorBankHistory"]] = relationship(
        back_populates="vendor",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_vendors_canonical_name_trgm", "canonical_name", postgresql_using="gin"),
    )

    def __repr__(self) -> str:
        return f"<Vendor(id={self.id}, name={self.canonical_name}, approved={self.is_approved})>"


class VendorBankHistory(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "vendor_bank_history"

    vendor_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("vendors.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    old_bank_account_hash: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
    )
    new_bank_account_hash: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
    )
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    flagged: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    vendor: Mapped["Vendor"] = relationship(back_populates="bank_history")

    __table_args__ = (
        Index("ix_vendor_bank_history_vendor_changed", "vendor_id", "changed_at"),
    )

    def __repr__(self) -> str:
        return f"<VendorBankHistory(id={self.id}, vendor_id={self.vendor_id}, flagged={self.flagged})>"