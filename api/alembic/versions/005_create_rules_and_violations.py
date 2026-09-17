"""create_rules_and_violations

Revision ID: 005
Revises: 004
Create Date: 2024-01-15 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE rule_severity_enum AS ENUM ('low', 'medium', 'high', 'critical');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)

    op.create_table(
        "rules",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False, unique=True),
        sa.Column("description", sa.String(1000), nullable=True),
        sa.Column("condition", postgresql.JSONB(), nullable=False),
        sa.Column("severity", sa.Enum("low", "medium", "high", "critical", name="rule_severity_enum", native_enum=False, create_type=False), nullable=False, server_default="medium"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_by", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_rules_name", "rules", ["name"], unique=True)
    op.create_index("ix_rules_created_by", "rules", ["created_by"])

    op.create_table(
        "rule_violations",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rule_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("rules.id", ondelete="CASCADE"), nullable=False),
        sa.Column("details", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_rule_violations_document_id", "rule_violations", ["document_id"])
    op.create_index("ix_rule_violations_rule_id", "rule_violations", ["rule_id"])
    op.create_index("ix_rule_violations_document_rule", "rule_violations", ["document_id", "rule_id"])


def downgrade() -> None:
    op.drop_index("ix_rule_violations_document_rule", table_name="rule_violations")
    op.drop_index("ix_rule_violations_rule_id", table_name="rule_violations")
    op.drop_index("ix_rule_violations_document_id", table_name="rule_violations")
    op.drop_table("rule_violations")
    op.drop_index("ix_rules_created_by", table_name="rules")
    op.drop_index("ix_rules_name", table_name="rules")
    op.drop_table("rules")
    op.execute("DROP TYPE IF EXISTS rule_severity_enum")