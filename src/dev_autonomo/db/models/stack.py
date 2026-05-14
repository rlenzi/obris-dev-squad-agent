"""Stack — instancia de uma stack detectada/declarada em uma squad.

Diferente de StackProfile (template global, ex: python-fastapi como
generico), Stack e a instancia REAL dessa stack numa squad: paths
especificos no codigo, framework version detectada, convencoes
particulares deste cliente.

Fluxo:
- onboarding_analyzer detecta python-fastapi em src/dev_autonomo/ →
  cria Stack(squad=X, slug=python-fastapi, paths=["src/dev_autonomo/"],
  parent_stack_profile_id=<global python-fastapi>, status=DETECTED).
- Cliente quer adicionar uma area que vai comecar do zero (ex: mobile)
  → cria Stack manual (status=MANUAL) sem parent_stack_profile_id, ou
  com parent apontando pra um stack_profile generico.
- Cada agente Dev da squad atrelado a uma ou mais Stacks define seu
  escopo de atuacao.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from dev_autonomo.common.enums import StackStatus
from dev_autonomo.db.base import Base
from dev_autonomo.db.mixins import TimestampMixin


class Stack(Base, TimestampMixin):
    """Stack persistida em uma squad — peca central do redesign."""

    __tablename__ = "stacks"
    __table_args__ = (
        UniqueConstraint("squad_id", "slug", name="uq_stack_squad_slug"),
    )

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
    # Link opcional com template global (StackProfile). Pode ser None
    # quando o cliente cria stack manual sem template correspondente.
    parent_stack_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("stack_profiles.id", ondelete="SET NULL"),
        index=True,
    )

    slug: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    # Lista de paths no repositorio onde essa stack vive (ex: ["src/api/", "src/web/"]).
    # JSONB pra suportar zero ou multiplos paths.
    paths: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    framework: Mapped[str | None] = mapped_column(String(128))
    framework_version: Mapped[str | None] = mapped_column(String(64))

    # Convencoes detectadas/declaradas (testing, naming, commit style, etc).
    # Schema flexivel pra evoluir sem migrations.
    conventions: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    status: Mapped[StackStatus] = mapped_column(
        Enum(
            StackStatus,
            name="stack_status_enum",
            create_type=False,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        default=StackStatus.DETECTED,
    )

    # Quando foi detectada pela analise. None pra stacks MANUAL.
    detected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )
