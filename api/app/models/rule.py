import enum
from typing import Optional, List
from sqlalchemy import String, ForeignKey, Boolean, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class RuleSeverity(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class Rule(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "rules"

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
        index=True,
    )
    description: Mapped[Optional[str]] = mapped_column(
        String(1000),
        nullable=True,
    )
    condition: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
    )
    severity: Mapped[RuleSeverity] = mapped_column(
        String(20),
        nullable=False,
        default=RuleSeverity.medium,
    )
    active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )
    created_by: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    violations: Mapped[List["RuleViolation"]] = relationship(
        back_populates="rule",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Rule(id={self.id}, name={self.name}, severity={self.severity})>"


class RuleViolation(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "rule_violations"

    document_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    rule_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("rules.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    details: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
    )

    document: Mapped["Document"] = relationship(back_populates="rule_violations")
    rule: Mapped["Rule"] = relationship(back_populates="violations")

    __table_args__ = (
        Index("ix_rule_violations_document_rule", "document_id", "rule_id"),
    )

    def __repr__(self) -> str:
        return f"<RuleViolation(id={self.id}, document_id={self.document_id}, rule_id={self.rule_id})>"