"""RagSource — referencia a uma fonte ingestada na RAG (cross-tenant ou privada).

Cada upload/URL/paste/feedback_loop vira 1 row em rag_sources + N chunks
correspondentes no Qdrant (referenciam back via metadata source_id).

Quando uma source e removida (delete), os chunks correspondentes
tambem sao apagados via service rag_ingest.delete_source().
"""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from dev_autonomo.common.enums import (
    RagSourceKind,
    RagSourceLicense,
    RagSourceQuality,
    RagSourceScope,
    RagSourceStatus,
)
from dev_autonomo.db.base import Base
from dev_autonomo.db.mixins import TimestampMixin

if TYPE_CHECKING:
    from dev_autonomo.db.models.core import Client, User


class RagSource(Base, TimestampMixin):
    """Fonte de conteudo ingestada na RAG da plataforma."""

    __tablename__ = "rag_sources"
    __table_args__ = (
        # Mesma fonte (source_hash) na mesma colecao nao deve ser
        # indexada duas vezes — caller deve checar antes de ingest novo.
        UniqueConstraint(
            "collection_slug", "source_hash", name="uq_rag_source_per_collection"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Identifica a colecao Qdrant alvo. Convencao:
    #   stack_patterns:{slug}              — cross-tenant
    #   stack_patterns:{slug}:{client_id}  — client_private (slug do cliente)
    #   playbook:{squad_id}                — privado da squad
    #   etc.
    collection_slug: Mapped[str] = mapped_column(String(128), index=True, nullable=False)

    kind: Mapped[RagSourceKind] = mapped_column(
        Enum(
            RagSourceKind,
            name="rag_source_kind_enum",
            create_type=False,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
    )

    # Identificador da fonte: URL, caminho de arquivo no storage, ou
    # PR URL pra feedback_loop. Nullable pra pasted_text.
    source_uri: Mapped[str | None] = mapped_column(String(1024))

    # Hash do conteudo extraido (SHA-256 ou similar) — usado pra dedup
    # via UniqueConstraint acima.
    source_hash: Mapped[str] = mapped_column(String(128), nullable=False)

    scope: Mapped[RagSourceScope] = mapped_column(
        Enum(
            RagSourceScope,
            name="rag_source_scope_enum",
            create_type=False,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
    )

    # Cliente dono (apenas se scope=client_private). NULL se cross_tenant.
    client_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("clients.id", ondelete="CASCADE"),
        index=True,
    )

    license: Mapped[RagSourceLicense] = mapped_column(
        Enum(
            RagSourceLicense,
            name="rag_source_license_enum",
            create_type=False,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
    )

    source_quality: Mapped[RagSourceQuality] = mapped_column(
        Enum(
            RagSourceQuality,
            name="rag_source_quality_enum",
            create_type=False,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
    )

    # Ex: "hybris-2305", "salesforce-spring-25" — usado pra filtro de
    # retrieval (rejeita chunks de versao diferente do projeto).
    stack_version: Mapped[str | None] = mapped_column(String(64))

    # User que subiu (SYSTEM_ADMIN ou CLIENT_ADMIN). Audit trail.
    uploaded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
    )

    # Numero de chunks indexados a partir desta fonte. Setado apos
    # pipeline completar.
    indexed_chunks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    status: Mapped[RagSourceStatus] = mapped_column(
        Enum(
            RagSourceStatus,
            name="rag_source_status_enum",
            create_type=False,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
    )

    # Mensagem de erro se status=failed.
    error_message: Mapped[str | None] = mapped_column(Text)

    # Tags livres pra filtragem/busca (ex: ["commerce", "b2b", "checkout"]).
    # JSONB pra suportar query @> '["b2b"]'::jsonb. Default empty list.
    tags: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)

    client: Mapped["Client | None"] = relationship(foreign_keys=[client_id])
    uploaded_by: Mapped["User | None"] = relationship(foreign_keys=[uploaded_by_user_id])
