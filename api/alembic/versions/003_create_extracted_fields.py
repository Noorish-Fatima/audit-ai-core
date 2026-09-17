"""create_extracted_fields

Revision ID: 003
Revises: 002
Create Date: 2024-01-15 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE extraction_method_enum AS ENUM ('text_model', 'vision_model', 'ocr_only');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)

    op.create_table(
        "extracted_fields",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("field_name", sa.String(100), nullable=False),
        sa.Column("field_value", sa.String(5000), nullable=False),
        sa.Column("confidence_score", sa.Float(), nullable=False),
        sa.Column("extraction_method", sa.Enum("text_model", "vision_model", "ocr_only", name="extraction_method_enum", native_enum=False, create_type=False), nullable=False),
        sa.Column("is_corrected", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("original_value", sa.String(5000), nullable=True),
        sa.Column("corrected_by", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("corrected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_extracted_fields_document_id", "extracted_fields", ["document_id"])
    op.create_index("ix_extracted_fields_document_field", "extracted_fields", ["document_id", "field_name"])
    op.create_index("ix_extracted_fields_corrected_by", "extracted_fields", ["corrected_by"])


def downgrade() -> None:
    op.drop_index("ix_extracted_fields_corrected_by", table_name="extracted_fields")
    op.drop_index("ix_extracted_fields_document_field", table_name="extracted_fields")
    op.drop_index("ix_extracted_fields_document_id", table_name="extracted_fields")
    op.drop_table("extracted_fields")
    op.execute("DROP TYPE IF EXISTS extraction_method_enum")