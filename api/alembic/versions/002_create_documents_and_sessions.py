"""create_documents_and_sessions

Revision ID: 002
Revises: 001
Create Date: 2024-01-15 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create document status enum
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE document_status_enum AS ENUM ('pending', 'ocr_processing', 'extracting', 'validating', 'review', 'verified', 'flagged', 'duplicate');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)

    # Create documents table
    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("original_filename", sa.String(500), nullable=False),
        sa.Column("storage_path", sa.String(1000), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("status", sa.Enum("pending", "ocr_processing", "extracting", "validating", "review", "verified", "flagged", "duplicate", name="document_status_enum", native_enum=False, create_type=False), nullable=False, server_default="pending"),
        sa.Column("uploaded_by", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_documents_status", "documents", ["status"])
    op.create_index("ix_documents_status_created_at", "documents", ["status", "created_at"])
    op.create_index("ix_documents_uploaded_by", "documents", ["uploaded_by"])
    op.create_index("ix_documents_uploaded_by_created_at", "documents", ["uploaded_by", "created_at"])

    # Create document_sessions table
    op.create_table(
        "document_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("current_stage", sa.String(100), nullable=False),
        sa.Column("progress_percent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("stage_history", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_document_sessions_document_id", "document_sessions", ["document_id"])
    op.create_index("ix_document_sessions_document_id_updated_at", "document_sessions", ["document_id", "updated_at"])


def downgrade() -> None:
    op.drop_index("ix_document_sessions_document_id_updated_at", table_name="document_sessions")
    op.drop_index("ix_document_sessions_document_id", table_name="document_sessions")
    op.drop_table("document_sessions")
    op.drop_index("ix_documents_uploaded_by_created_at", table_name="documents")
    op.drop_index("ix_documents_uploaded_by", table_name="documents")
    op.drop_index("ix_documents_status_created_at", table_name="documents")
    op.drop_index("ix_documents_status", table_name="documents")
    op.drop_table("documents")
    op.execute("DROP TYPE IF EXISTS document_status_enum")