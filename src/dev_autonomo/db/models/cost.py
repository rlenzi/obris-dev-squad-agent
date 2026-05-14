"""Ledger interno de custo unificado + billing por periodo.

ExternalApiCall agrega TODAS as chamadas a APIs externas que geram custo:
Anthropic (Claude), Voyage (embeddings), GitHub (futuro), Jira (futuro), etc.
Cada row contem provider, kind, model, tokens, latencia e custo USD.

BillingPeriod materializa custo agregado por cliente em janelas mensais
para faturamento.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from dev_autonomo.common.enums import ApiCallKind, ApiProvider
from dev_autonomo.db.base import Base
from dev_autonomo.db.mixins import TimestampMixin


class ExternalApiCall(Base):
    """Cada chamada a uma API externa vira uma row. Base de billing e otimizacao.

    Cobre Anthropic, Voyage, e futuros providers (GitHub API, Jira, etc).
    """

    __tablename__ = "external_api_calls"

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

    provider: Mapped[ApiProvider] = mapped_column(
        Enum(
            ApiProvider,
            name="api_provider_enum",
            create_type=False,
            values_callable=lambda e: [m.value for m in e],
        ),
        index=True,
    )
    kind: Mapped[ApiCallKind] = mapped_column(
        Enum(
            ApiCallKind,
            name="api_call_kind_enum",
            create_type=False,
            values_callable=lambda e: [m.value for m in e],
        ),
        index=True,
    )
    model: Mapped[str | None] = mapped_column(String(128))

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

    # Custos diretos (somatorio de external_api_calls)
    total_tokens_input: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens_output: Mapped[int] = mapped_column(Integer, default=0)
    total_cost_direct_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0"))
    total_cost_direct_brl: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))

    # Custos indiretos (overhead + fixo)
    total_cost_infra_brl: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    total_cost_fixed_brl: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))

    # Custo total real do dev-autonomo
    total_cost_full_brl: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))

    # Cobranca aplicada
    total_tasks_closed: Mapped[int] = mapped_column(Integer, default=0)
    base_fee_amount_brl: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    overage_amount_brl: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    invoice_amount_brl: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))

    invoice_status: Mapped[str] = mapped_column(String(32), default="draft")
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
