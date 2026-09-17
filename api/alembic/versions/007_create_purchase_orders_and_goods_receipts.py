"""create_purchase_orders_and_goods_receipts

Revision ID: 007
Revises: 006
Create Date: 2024-01-15 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "purchase_orders",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("po_number", sa.String(100), nullable=False, unique=True),
        sa.Column("vendor_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("vendors.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("expected_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("line_items", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_purchase_orders_po_number", "purchase_orders", ["po_number"], unique=True)
    op.create_index("ix_purchase_orders_vendor_id", "purchase_orders", ["vendor_id"])

    op.create_table(
        "goods_receipts",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("po_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("purchase_orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("received_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_goods_receipts_po_id", "goods_receipts", ["po_id"])
    op.create_index("ix_goods_receipts_po_received", "goods_receipts", ["po_id", "received_at"])


def downgrade() -> None:
    op.drop_index("ix_goods_receipts_po_received", table_name="goods_receipts")
    op.drop_index("ix_goods_receipts_po_id", table_name="goods_receipts")
    op.drop_table("goods_receipts")
    op.drop_index("ix_purchase_orders_vendor_id", table_name="purchase_orders")
    op.drop_index("ix_purchase_orders_po_number", table_name="purchase_orders")
    op.drop_table("purchase_orders")