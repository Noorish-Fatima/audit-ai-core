import enum
from typing import Optional, List
from sqlalchemy import String, ForeignKey, Integer, Index, Enum as SQLEnum, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class DocumentStatus(str, enum.Enum):
    pending = "pending"
    ocr_processing = "ocr_processing"
    extracting = "extracting"
    validating = "validating"
    review = "review"
    verified = "verified"
    flagged = "flagged"
    duplicate = "duplicate"


class Document(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "documents"

    original_filename: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )
    storage_path: Mapped[str] = mapped_column(
        String(1000),
        nullable=False,
    )
    mime_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    file_size: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    status: Mapped[DocumentStatus] = mapped_column(
        SQLEnum(DocumentStatus, name="document_status_enum", create_type=True),
        nullable=False,
        default=DocumentStatus.pending,
        index=True,
    )
    uploaded_by: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    raw_ocr_text: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    normalized_image_paths: Mapped[Optional[List[str]]] = mapped_column(
        JSONB,
        nullable=True,
        default=list,
    )

    sessions: Mapped[List["DocumentSession"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
    )
    extracted_fields: Mapped[List["ExtractedField"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
    )
    rule_violations: Mapped[List["RuleViolation"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
    )
    duplicate_flags: Mapped[List["DuplicateFlag"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        foreign_keys="DuplicateFlag.document_id",
    )
    fraud_flags: Mapped[List["FraudFlag"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_documents_status_created_at", "status", "created_at"),
        Index("ix_documents_uploaded_by_created_at", "uploaded_by", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<Document(id={self.id}, filename={self.original_filename}, status={self.status})>"


class DocumentSession(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "document_sessions"

    document_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    current_stage: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )
    progress_percent: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    stage_history: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
    )

    document: Mapped["Document"] = relationship(back_populates="sessions")

    __table_args__ = (
        Index("ix_document_sessions_document_id_updated_at", "document_id", "updated_at"),
    )

    def __repr__(self) -> str:
        return f"<DocumentSession(id={self.id}, document_id={self.document_id}, stage={self.current_stage})>"