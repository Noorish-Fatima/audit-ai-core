"""add_ocr_fields_to_documents

Revision ID: 96e4f9a8a819
Revises: 012
Create Date: 2026-09-17 23:11:04.723988

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '96e4f9a8a819'
down_revision: Union[str, None] = '012'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("raw_ocr_text", sa.Text(), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column("normalized_image_paths", postgresql.JSONB(astext_type=sa.Text()), nullable=True, default=list),
    )


def downgrade() -> None:
    op.drop_column("documents", "normalized_image_paths")
    op.drop_column("documents", "raw_ocr_text")