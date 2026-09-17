from datetime import datetime
from decimal import Decimal
from typing import List
from sqlalchemy import String, ForeignKey, Numeric, DateTime, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class PurchaseOrder(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "purchase_orders"

    po_number: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True,
        index=True,
    )
    vendor_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("vendors.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    expected_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )
    line_items: Mapped[List[dict]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
    )

    goods_receipts: Mapped[List["GoodsReceipt"]] = relationship(
        back_populates="purchase_order",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<PurchaseOrder(id={self.id}, po_number={self.po_number}, amount={self.expected_amount})>"


class GoodsReceipt(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "goods_receipts"

    po_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("purchase_orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    received_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    purchase_order: Mapped["PurchaseOrder"] = relationship(back_populates="goods_receipts")

    __table_args__ = (
        Index("ix_goods_receipts_po_received", "po_id", "received_at"),
    )

    def __repr__(self) -> str:
        return f"<GoodsReceipt(id={self.id}, po_id={self.po_id}, amount={self.received_amount})>"