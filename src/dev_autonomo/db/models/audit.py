"""Modelo de auditoria de tool calls: ToolAuthorizationAttempt."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from dev_autonomo.db.base import Base


class ToolAuthorizationAttempt(Base):
    """Log de cada tentativa de tool call passar pelo ManifestEnforcer.

    Util para:
    - Auditoria de seguranca (quem tentou acessar o que e quando).
    - Detectar agentes mal-comportados ou prompts adversariais.
    - Tunar manifestos: se ha muitos bloqueios legitimos, talvez o owns
      precise ser mais amplo (ou criar Cross-Squad Request).
    """

    __tablename__ = "tool_authorization_attempts"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), index=True
    )
    squad_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("squads.id", ondelete="CASCADE"), index=True
    )
    agent_instance_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("agent_instances.id", ondelete="SET NULL")
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="SET NULL"), index=True
    )

    tool_name: Mapped[str] = mapped_column(String(64), index=True)
    resource: Mapped[str] = mapped_column(String(1024))
    allowed: Mapped[bool] = mapped_column(Boolean, index=True)
    reason: Mapped[str] = mapped_column(String(64))
    matched_rule: Mapped[str | None] = mapped_column(String(255))
    suggestion: Mapped[str | None] = mapped_column(String(512))

    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
