"""create_duplicate_and_fraud_flags

Revision ID: 006
Revises: 005
Create Date: 2024-01-15 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE duplicate_match_type_enum AS ENUM ('exact_key', 'fuzzy_match');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE fraud_flag_type_enum AS ENUM ('bank_change', 'new_vendor_high_amount', 'round_number_threshold');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)

    op.create_table(
        "duplicate_flags",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("duplicate_of_document_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("match_type", sa.Enum("exact_key", "fuzzy_match", name="duplicate_match_type_enum", native_enum=False, create_type=False), nullable=False),
        sa.Column("confidence_score", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_duplicate_flags_document_id", "duplicate_flags", ["document_id"])
    op.create_index("ix_duplicate_flags_duplicate_of_id", "duplicate_flags", ["duplicate_of_document_id"])
    op.create_index("ix_duplicate_flags_doc_duplicate", "duplicate_flags", ["document_id", "duplicate_of_document_id"])

    op.create_table(
        "fraud_flags",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("flag_type", sa.Enum("bank_change", "new_vendor_high_amount", "round_number_threshold", name="fraud_flag_type_enum", native_enum=False, create_type=False), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("details", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_fraud_flags_document_id", "fraud_flags", ["document_id"])
    op.create_index("ix_fraud_flags_flag_type", "fraud_flags", ["flag_type"])
    op.create_index("ix_fraud_flags_document_type", "fraud_flags", ["document_id", "flag_type"])


def downgrade() -> None:
    op.drop_index("ix_fraud_flags_document_type", table_name="fraud_flags")
    op.drop_index("ix_fraud_flags_flag_type", table_name="fraud_flags")
    op.drop_index("ix_fraud_flags_document_id", table_name="fraud_flags")
    op.drop_table("fraud_flags")
    op.drop_index("ix_duplicate_flags_doc_duplicate", table_name="duplicate_flags")
    op.drop_index("ix_duplicate_flags_duplicate_of_id", table_name="duplicate_flags")
    op.drop_index("ix_duplicate_flags_document_id", table_name="duplicate_flags")
    op.drop_table("duplicate_flags")
    op.execute("DROP TYPE IF EXISTS fraud_flag_type_enum")
    op.execute("DROP TYPE IF EXISTS duplicate_match_type_enum")