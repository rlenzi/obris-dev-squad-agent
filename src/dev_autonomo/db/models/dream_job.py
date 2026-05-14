"""DreamJob — registro de consolidações Dreaming (Bloco H).

Toda task encerrada com sucesso gera 1 DreamJob. Enquanto o research
preview Dreaming não estiver liberado pra org (ou DREAMING_ENABLED for
False), os jobs ficam como ``CANDIDATE`` — registro pra visibilidade do
que seria consolidado. Quando o access vier, os jobs novos viram
``RUNNING -> COMPLETED/FAILED`` automaticamente.

Schema desenhado pra suportar 2 cadências sem mudança:
- pós-task (1 session por job, task_id setado)
- batch diário (N sessions por job, task_id NULL, instructions agregadas)
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from dev_autonomo.common.enums import DreamJobStatus
from dev_autonomo.db.base import Base

if TYPE_CHECKING:
    pass


class DreamJob(Base):
    """Job de consolidação Dreaming (research preview Anthropic)."""

    __tablename__ = "dream_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    squad_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("squads.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tasks.id", ondelete="SET NULL"),
        index=True,
    )
    memory_store_id: Mapped[str] = mapped_column(String(128), nullable=False)
    session_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    instructions: Mapped[str | None] = mapped_column(Text)
    status: Mapped[DreamJobStatus] = mapped_column(
        Enum(
            DreamJobStatus,
            name="dream_job_status_enum",
            create_type=False,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        default=DreamJobStatus.CANDIDATE,
    )
    dream_id: Mapped[str | None] = mapped_column(String(128))
    output_memory_store_id: Mapped[str | None] = mapped_column(String(128))
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(12, 6), nullable=False, default=Decimal("0")
    )
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
