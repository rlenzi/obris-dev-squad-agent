"""Pydantic schemas para endpoints de RAG sources (Bloco C)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from dev_autonomo.common.enums import (
    RagSourceKind,
    RagSourceLicense,
    RagSourceQuality,
    RagSourceScope,
    RagSourceStatus,
)


class RagSourceCreate(BaseModel):
    """Body comum pra criar fonte (admin ou cliente).

    Caller decide scope + collection_slug. Admin pode set cross_tenant;
    cliente sempre client_private.
    """

    kind: RagSourceKind
    license: RagSourceLicense
    source_quality: RagSourceQuality
    stack_version: str | None = Field(None, max_length=64)
    tags: list[str] = Field(default_factory=list)
    has_redistribution_right: bool = Field(
        default=False,
        description=(
            "Quando scope=cross_tenant, exige True como log auditavel de "
            "que admin Orbis tem direito de redistribuir o conteudo."
        ),
    )

    # Conteudo: 1 destes 3 dependendo do kind.
    pasted_text: str | None = None     # quando kind=PASTED_TEXT
    source_url: str | None = None      # quando kind=URL_FETCH
    # file_upload usa multipart separado, nao aparece aqui.


class RagSourcePublic(BaseModel):
    """Detalhe de uma fonte indexada."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    collection_slug: str
    kind: RagSourceKind
    source_uri: str | None
    source_hash: str
    scope: RagSourceScope
    client_id: UUID | None
    license: RagSourceLicense
    source_quality: RagSourceQuality
    stack_version: str | None
    uploaded_by_user_id: UUID | None
    indexed_chunks: int
    status: RagSourceStatus
    error_message: str | None
    tags: list[str]
    created_at: datetime
    updated_at: datetime


class RagSourceIngestResponse(BaseModel):
    """Retorno do POST de ingest."""

    rag_source_id: UUID
    status: RagSourceStatus
    indexed_chunks: int
    source_hash: str
    error_message: str | None = None
    deduplicated: bool = False


class StackCollectionSummary(BaseModel):
    """Resumo de uma colecao stack_patterns no painel admin."""

    stack_slug: str
    stack_name: str
    total_sources: int
    total_chunks: int
    sources_by_quality: dict[str, int]  # ex: {"official": 5, "orbis_curated": 12}
    clients_using: int                  # quantas squads ativas tocam essa stack
