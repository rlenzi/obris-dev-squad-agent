"""Skill template: receita reutilizavel para instanciar agentes."""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Enum, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from dev_autonomo.common.enums import AgentTier
from dev_autonomo.db.base import Base
from dev_autonomo.db.mixins import TimestampMixin

if TYPE_CHECKING:
    from dev_autonomo.db.models.agent import AgentInstance


class SkillTemplate(Base, TimestampMixin):
    """client_id NULL = template do sistema (compartilhado entre clientes)."""

    __tablename__ = "skill_templates"
    __table_args__ = (
        UniqueConstraint("client_id", "slug", "version", name="uq_skill_slug_version"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), index=True
    )

    slug: Mapped[str] = mapped_column(String(128))
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(String(1024))
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    tier: Mapped[AgentTier] = mapped_column(Enum(AgentTier, name="agent_tier_enum"), nullable=False)
    model_alias: Mapped[str] = mapped_column(String(64))

    stack_primary: Mapped[dict] = mapped_column(JSONB, default=dict)
    stack_secondary: Mapped[list] = mapped_column(JSONB, default=list)

    system_prompt_ref: Mapped[str] = mapped_column(String(512))
    tools_enabled: Mapped[list] = mapped_column(JSONB, default=list)
    knowledge_partitions: Mapped[list] = mapped_column(JSONB, default=list)

    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    instances: Mapped[list["AgentInstance"]] = relationship(back_populates="skill_template")
