"""create_nl_query_log

Revision ID: 008
Revises: 007
Create Date: 2024-01-15 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "nl_query_log",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("question_text", sa.String(2000), nullable=False),
        sa.Column("resolved_intent", sa.String(100), nullable=True),
        sa.Column("tool_called", sa.String(100), nullable=True),
        sa.Column("tool_args", postgresql.JSONB(), nullable=True),
        sa.Column("response_text", sa.String(5000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_nl_query_log_user_id", "nl_query_log", ["user_id"])
    op.create_index("ix_nl_query_log_user_created", "nl_query_log", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_nl_query_log_user_created", table_name="nl_query_log")
    op.drop_index("ix_nl_query_log_user_id", table_name="nl_query_log")
    op.drop_table("nl_query_log")