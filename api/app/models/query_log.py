from typing import Optional
from sqlalchemy import String, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class NLQueryLog(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "nl_query_log"

    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    question_text: Mapped[str] = mapped_column(
        String(2000),
        nullable=False,
    )
    resolved_intent: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )
    tool_called: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )
    tool_args: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
    )
    response_text: Mapped[Optional[str]] = mapped_column(
        String(5000),
        nullable=True,
    )

    __table_args__ = (
        Index("ix_nl_query_log_user_created", "user_id", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<NLQueryLog(id={self.id}, user_id={self.user_id}, intent={self.resolved_intent})>"