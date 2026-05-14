"""RagAuditLog — audit trail do pipeline de feedback loop (Bloco F)."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from dev_autonomo.common.enums import AuditDecision
from dev_autonomo.db.base import Base

if TYPE_CHECKING:
    pass


class RagAuditLog(Base):
    """Audit log — cada chunk avaliado pelo pipeline vira 1 linha."""

    __tablename__ = "rag_audit_log"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    rag_source_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("rag_sources.id", ondelete="SET NULL"),
        index=True,
    )
    stack_slug: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    pr_url: Mapped[str | None] = mapped_column(String(512))
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_preview: Mapped[str | None] = mapped_column(String(500))
    decision: Mapped[AuditDecision] = mapped_column(
        Enum(
            AuditDecision,
            name="audit_decision_enum",
            create_type=False,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
    )
    reasons: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    sonnet_verdict: Mapped[dict | None] = mapped_column(JSONB)
    haiku_tokens_in: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    haiku_tokens_out: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sonnet_tokens_in: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sonnet_tokens_out: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
