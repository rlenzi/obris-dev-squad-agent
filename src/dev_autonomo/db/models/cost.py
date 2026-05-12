"""Ledger interno de custo (ClaudeApiCall) e billing por periodo."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from dev_autonomo.db.base import Base
from dev_autonomo.db.mixins import TimestampMixin


class ClaudeApiCall(Base):
    """Cada chamada ao Claude vira uma row. Base de billing e otimizacao."""

    __tablename__ = "claude_api_calls"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), index=True
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="SET NULL"), index=True
    )
    agent_instance_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("agent_instances.id", ondelete="SET NULL")
    )

    model: Mapped[str] = mapped_column(String(64))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_creation_input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_read_input_tokens: Mapped[int] = mapped_column(Integer, default=0)

    cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0"))
    latency_ms: Mapped[int | None] = mapped_column(Integer)

    request_id: Mapped[str | None] = mapped_column(String(128))
    error: Mapped[str | None] = mapped_column(Text)

    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class BillingPeriod(Base, TimestampMixin):
    """Periodo de billing mensal. Materializa custo agregado por cliente."""

    __tablename__ = "billing_periods"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), index=True
    )
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)

    total_tokens_input: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens_output: Mapped[int] = mapped_column(Integer, default=0)
    total_cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0"))
    total_tasks_closed: Mapped[int] = mapped_column(Integer, default=0)

    base_fee_amount_brl: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    overage_amount_brl: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    invoice_amount_brl: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))

    invoice_status: Mapped[str] = mapped_column(String(32), default="draft")
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
