"""SquadMemoryStore — referencia a um memory_store Anthropic por squad."""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from dev_autonomo.common.enums import MemoryStoreKind
from dev_autonomo.db.base import Base
from dev_autonomo.db.mixins import TimestampMixin

if TYPE_CHECKING:
    from dev_autonomo.db.models.squad import Squad


class SquadMemoryStore(Base, TimestampMixin):
    """Referencia a um memory_store provisionado na Anthropic pra essa squad.

    Squad pode ter varios stores diferenciados por ``kind`` (insights,
    playbook, conventions, onboarding). UNIQUE(squad_id, kind) garante
    no maximo 1 store por kind.

    ``anthropic_store_id`` e o ID retornado por
    ``c.beta.memory_stores.create()``. ``last_dream_id`` registra o dream
    que produziu esse store atual (None enquanto Dreaming nao roda).
    """

    __tablename__ = "squad_memory_stores"
    __table_args__ = (
        UniqueConstraint("squad_id", "kind", name="uq_squad_memory_kind"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    squad_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("squads.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    anthropic_store_id: Mapped[str] = mapped_column(String(64), nullable=False)
    kind: Mapped[MemoryStoreKind] = mapped_column(
        Enum(MemoryStoreKind, name="memory_store_kind_enum"), nullable=False
    )
    description: Mapped[str | None] = mapped_column(String(1024))
    last_dream_id: Mapped[str | None] = mapped_column(String(64))

    squad: Mapped["Squad"] = relationship(back_populates="memory_stores")
