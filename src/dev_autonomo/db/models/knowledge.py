"""Tabelas do Knowledge Hub: indexing jobs, playbook, onboarding runs."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from dev_autonomo.db.base import Base
from dev_autonomo.db.mixins import TimestampMixin


class KnowledgeIndexingJob(Base, TimestampMixin):
    """Job de indexacao (full, incremental, playbook_mine, replay_validation)."""

    __tablename__ = "knowledge_indexing_jobs"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), index=True
    )
    squad_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("squads.id", ondelete="CASCADE"), index=True
    )

    kind: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="queued")

    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    result: Mapped[dict | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PlaybookEntry(Base, TimestampMixin):
    """Entry estruturada do playbook (conhecimento tacito capturado)."""

    __tablename__ = "playbook_entries"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), index=True
    )
    squad_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("squads.id", ondelete="CASCADE"), index=True
    )

    scope_glob: Mapped[str] = mapped_column(String(255))
    rule_text: Mapped[str] = mapped_column(Text)
    example_code: Mapped[str | None] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(32), default="medium")

    origin: Mapped[str] = mapped_column(String(255))
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    embedding_vector_id: Mapped[str | None] = mapped_column(String(128))


class OnboardingRun(Base, TimestampMixin):
    """Execucao do fluxo de onboarding de um projeto numa squad."""

    __tablename__ = "onboarding_runs"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), index=True
    )
    squad_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("squads.id", ondelete="CASCADE"), index=True
    )

    repos: Mapped[list] = mapped_column(JSONB, default=list)
    status_per_stage: Mapped[dict] = mapped_column(JSONB, default=dict)

    total_cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0"))
    interview_jira_issue_key: Mapped[str | None] = mapped_column(String(64))
    calibration_score_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
