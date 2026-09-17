"""add_check_constraints_for_enum_columns

Revision ID: 010
Revises: 009
Create Date: 2024-01-15 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # documents.status
    op.create_check_constraint(
        "ck_documents_status",
        "documents",
        "status IN ('pending', 'ocr_processing', 'extracting', 'validating', 'review', 'verified', 'flagged', 'duplicate')",
    )

    # users.role
    op.create_check_constraint(
        "ck_users_role",
        "users",
        "role IN ('admin', 'approver', 'auditor')",
    )

    # rules.severity
    op.create_check_constraint(
        "ck_rules_severity",
        "rules",
        "severity IN ('low', 'medium', 'high', 'critical')",
    )

    # fraud_flags.flag_type
    op.create_check_constraint(
        "ck_fraud_flags_flag_type",
        "fraud_flags",
        "flag_type IN ('bank_change', 'new_vendor_high_amount', 'round_number_threshold')",
    )

    # fraud_flags.severity (reusing rule severity values)
    op.create_check_constraint(
        "ck_fraud_flags_severity",
        "fraud_flags",
        "severity IN ('low', 'medium', 'high', 'critical')",
    )

    # duplicate_flags.match_type
    op.create_check_constraint(
        "ck_duplicate_flags_match_type",
        "duplicate_flags",
        "match_type IN ('exact_key', 'fuzzy_match')",
    )

    # extracted_fields.extraction_method
    op.create_check_constraint(
        "ck_extracted_fields_extraction_method",
        "extracted_fields",
        "extraction_method IN ('text_model', 'vision_model', 'ocr_only')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_documents_status", "documents", type_="check")
    op.drop_constraint("ck_users_role", "users", type_="check")
    op.drop_constraint("ck_rules_severity", "rules", type_="check")
    op.drop_constraint("ck_fraud_flags_flag_type", "fraud_flags", type_="check")
    op.drop_constraint("ck_fraud_flags_severity", "fraud_flags", type_="check")
    op.drop_constraint("ck_duplicate_flags_match_type", "duplicate_flags", type_="check")
    op.drop_constraint("ck_extracted_fields_extraction_method", "extracted_fields", type_="check")
