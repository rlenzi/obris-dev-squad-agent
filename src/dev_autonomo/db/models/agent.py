"""Agent instance (agente provisionado) e AgentMessage (A2A)."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from dev_autonomo.common.enums import AgentInstanceStatus
from dev_autonomo.db.base import Base
from dev_autonomo.db.mixins import TimestampMixin

if TYPE_CHECKING:
    from dev_autonomo.db.models.skill import SkillTemplate
    from dev_autonomo.db.models.squad import Squad


class AgentInstance(Base, TimestampMixin):
    __tablename__ = "agent_instances"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), index=True
    )
    squad_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("squads.id", ondelete="CASCADE"), index=True
    )
    skill_template_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("skill_templates.id", ondelete="RESTRICT")
    )

    name: Mapped[str] = mapped_column(String(255))
    domain_business: Mapped[str | None] = mapped_column(String(128))

    status: Mapped[AgentInstanceStatus] = mapped_column(
        Enum(AgentInstanceStatus, name="agent_instance_status_enum"),
        default=AgentInstanceStatus.IDLE,
    )
    config_overrides: Mapped[dict] = mapped_column(JSONB, default=dict)
    last_active_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    squad: Mapped["Squad"] = relationship(back_populates="agents", foreign_keys=[squad_id])
    skill_template: Mapped["SkillTemplate"] = relationship(back_populates="instances")


class AgentMessage(Base, TimestampMixin):
    """Mensagem A2A entre tiers (BA -> Architect -> Dev)."""

    __tablename__ = "agent_messages"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), index=True
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), index=True
    )

    from_agent_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("agent_instances.id", ondelete="SET NULL")
    )
    to_agent_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("agent_instances.id", ondelete="SET NULL")
    )

    message_kind: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)

    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
