"""Squad (unidade de provisionamento) e Manifest (contrato de owns)."""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from dev_autonomo.common.enums import SquadStatus
from dev_autonomo.db.base import Base
from dev_autonomo.db.mixins import TimestampMixin

if TYPE_CHECKING:
    from dev_autonomo.db.models.agent import AgentInstance
    from dev_autonomo.db.models.core import Client
    from dev_autonomo.db.models.squad_memory_store import SquadMemoryStore


class Squad(Base, TimestampMixin):
    __tablename__ = "squads"
    __table_args__ = (UniqueConstraint("client_id", "slug", name="uq_squad_client_slug"),)

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), index=True
    )
    slug: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(String(1024))
    domain: Mapped[str | None] = mapped_column(String(128))

    status: Mapped[SquadStatus] = mapped_column(
        Enum(SquadStatus, name="squad_status_enum"), default=SquadStatus.PROVISIONING
    )

    current_manifest_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("manifests.id", ondelete="SET NULL", use_alter=True)
    )

    client: Mapped["Client"] = relationship(back_populates="squads")
    agents: Mapped[list["AgentInstance"]] = relationship(
        back_populates="squad",
        cascade="all, delete-orphan",
        foreign_keys="AgentInstance.squad_id",
    )
    manifests: Mapped[list["Manifest"]] = relationship(
        back_populates="squad",
        cascade="all, delete-orphan",
        foreign_keys="Manifest.squad_id",
    )
    memory_stores: Mapped[list["SquadMemoryStore"]] = relationship(
        back_populates="squad",
        cascade="all, delete-orphan",
    )


class Manifest(Base, TimestampMixin):
    __tablename__ = "manifests"
    __table_args__ = (UniqueConstraint("squad_id", "version", name="uq_manifest_squad_version"),)

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    squad_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("squads.id", ondelete="CASCADE"), index=True
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), index=True
    )

    version: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[dict] = mapped_column(JSONB, nullable=False)

    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )

    squad: Mapped["Squad"] = relationship(back_populates="manifests", foreign_keys=[squad_id])
