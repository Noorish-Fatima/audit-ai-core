"""create_vendors_and_bank_history

Revision ID: 004
Revises: 003
Create Date: 2024-01-15 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "vendors",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("canonical_name", sa.String(255), nullable=False),
        sa.Column("aliases", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("tax_id", sa.String(50), nullable=True),
        sa.Column("is_approved", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_new", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("bank_account_last4", sa.String(4), nullable=True),
        sa.Column("bank_account_hash", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_vendors_canonical_name", "vendors", ["canonical_name"])
    op.create_index("ix_vendors_tax_id", "vendors", ["tax_id"])

    op.create_table(
        "vendor_bank_history",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("vendor_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("vendors.id", ondelete="CASCADE"), nullable=False),
        sa.Column("old_bank_account_hash", sa.String(64), nullable=True),
        sa.Column("new_bank_account_hash", sa.String(64), nullable=True),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("flagged", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_vendor_bank_history_vendor_id", "vendor_bank_history", ["vendor_id"])
    op.create_index("ix_vendor_bank_history_vendor_changed", "vendor_bank_history", ["vendor_id", "changed_at"])


def downgrade() -> None:
    op.drop_index("ix_vendor_bank_history_vendor_changed", table_name="vendor_bank_history")
    op.drop_index("ix_vendor_bank_history_vendor_id", table_name="vendor_bank_history")
    op.drop_table("vendor_bank_history")
    op.drop_index("ix_vendors_tax_id", table_name="vendors")
    op.drop_index("ix_vendors_canonical_name", table_name="vendors")
    op.drop_table("vendors")