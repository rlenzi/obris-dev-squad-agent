"""RAG retriever com rerank + filtros (Bloco G).

Combina ate 3 colecoes Qdrant numa query unica:
  1. playbook:{squad_id}                  — playbook privado da squad
  2. stack_patterns:{slug}:{client_id}    — RAG stack privada do cliente
  3. stack_patterns:{slug}                — RAG stack cross-tenant

Reranking heuristico (sem chamada extra ao Voyage rerank-2 pra MVP):
  - Score base = cosine similarity do Qdrant
  - Weight por escopo: privada cliente = 1.5x, stack privada = 1.3x,
    cross-tenant = 1.0x
  - Weight por quality: official = 1.3x, orbis_curated = 1.25x,
    partner = 1.15x, field_proven = 1.1x, community = 1.0x, internal = 1.2x
  - Boost recencia: chunks <30 dias = +20% (calculo aproximado via
    rag_source.created_at se disponivel)

Filtros pre-rerank:
  - stack_version: rejeita chunks de versao diferente se query especifica
  - license: pra cross-tenant rejeita partner_only e client_internal

Output: top-N chunks com {content, source_id, score, scope, source_quality,
license, source_uri, metadata}.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from qdrant_client.models import Filter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dev_autonomo.knowledge.qdrant_client import QdrantKnowledgeStore
from dev_autonomo.knowledge.voyage_client import VoyageEmbeddingClient
from dev_autonomo.db.models import RagSource
from dev_autonomo.services.rag_ingest import qdrant_collection_for_slug

logger = logging.getLogger(__name__)


# Pesos de rerank
_SCOPE_WEIGHTS: dict[str, float] = {
    "squad_private": 1.5,
    "client_private": 1.3,
    "cross_tenant": 1.0,
}

_QUALITY_WEIGHTS: dict[str, float] = {
    "official": 1.3,
    "orbis_curated": 1.25,
    "internal": 1.2,
    "partner": 1.15,
    "field_proven": 1.1,
    "community": 1.0,
}

_RECENCY_BOOST_DAYS = 30
_RECENCY_BOOST_MULTIPLIER = 1.2


@dataclass(slots=True)
class RetrievalHit:
    """1 chunk retornado por search()."""

    content: str
    source_id: UUID | None
    raw_score: float          # cosine do Qdrant
    final_score: float        # apos rerank
    scope: str                # squad_private | client_private | cross_tenant
    source_quality: str
    license: str
    source_uri: str | None
    stack_version: str | None
    collection_slug: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RetrievalParams:
    """Parametros de uma query."""

    query: str
    squad_id: UUID | None = None       # se setado, busca em playbook + private
    client_id: UUID | None = None      # pra stack private
    stack_slug: str | None = None      # pra cross-tenant + stack private
    stack_version: str | None = None   # filtro estrito se setado
    top_k: int = 20
    candidates_per_collection: int = 25  # top-K por colecao antes do rerank


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


async def search(
    session: AsyncSession,
    params: RetrievalParams,
    voyage_client: VoyageEmbeddingClient | None = None,
    qdrant_store: QdrantKnowledgeStore | None = None,
) -> list[RetrievalHit]:
    """Executa busca em ate 3 colecoes + rerank heuristico."""
    voyage = voyage_client or VoyageEmbeddingClient()
    qdrant = qdrant_store or QdrantKnowledgeStore()

    # 1. Embed query
    query_embed = await voyage.embed_query(params.query)
    qvec = query_embed.vector

    # 2. Resolve colecoes-alvo
    collections: list[tuple[str, str]] = []  # [(qdrant_collection_name, scope)]
    if params.squad_id:
        slug = f"playbook:{params.squad_id}"
        collections.append((qdrant_collection_for_slug(slug), "squad_private"))
    if params.stack_slug and params.client_id:
        slug = f"stack_patterns:{params.stack_slug}:{params.client_id}"
        collections.append((qdrant_collection_for_slug(slug), "client_private"))
    if params.stack_slug:
        slug = f"stack_patterns:{params.stack_slug}"
        collections.append((qdrant_collection_for_slug(slug), "cross_tenant"))

    if not collections:
        return []

    # 3. Busca em cada colecao
    all_hits: list[RetrievalHit] = []
    for collection_name, scope in collections:
        try:
            results = await qdrant._client.search(
                collection_name=collection_name,
                query_vector=qvec,
                limit=params.candidates_per_collection,
                with_payload=True,
            )
        except Exception as exc:
            logger.debug("colecao %s nao existe ou erro: %s", collection_name, exc)
            continue

        for point in results:
            payload = point.payload or {}
            stack_version = payload.get("stack_version")
            license_str = payload.get("license", "unknown")

            # Filtros pre-rerank
            if params.stack_version and stack_version and stack_version != params.stack_version:
                continue
            if scope == "cross_tenant" and license_str in ("partner_only", "client_internal"):
                continue

            all_hits.append(RetrievalHit(
                content=str(payload.get("content", ""))[:4000],
                source_id=_to_uuid(payload.get("rag_source_id")),
                raw_score=float(point.score),
                final_score=float(point.score),  # recalculado abaixo
                scope=scope,
                source_quality=str(payload.get("source_quality", "community")),
                license=str(license_str),
                source_uri=payload.get("source_uri"),
                stack_version=stack_version,
                collection_slug=str(payload.get("collection_slug", "")),
                metadata={
                    "chunk_index": payload.get("chunk_index"),
                    "tags": payload.get("tags", []),
                },
            ))

    if not all_hits:
        return []

    # 4. Boost recencia: busca created_at dos rag_sources distintos
    source_ids = {h.source_id for h in all_hits if h.source_id}
    recency_boost: dict[UUID, bool] = {}
    if source_ids:
        rows = (await session.execute(
            select(RagSource.id, RagSource.created_at).where(
                RagSource.id.in_(source_ids)
            )
        )).all()
        cutoff = datetime.now(tz=timezone.utc) - timedelta(days=_RECENCY_BOOST_DAYS)
        for row in rows:
            recency_boost[row.id] = row.created_at >= cutoff

    # 5. Aplica weights
    for hit in all_hits:
        scope_w = _SCOPE_WEIGHTS.get(hit.scope, 1.0)
        quality_w = _QUALITY_WEIGHTS.get(hit.source_quality, 1.0)
        recency_w = _RECENCY_BOOST_MULTIPLIER if recency_boost.get(hit.source_id, False) else 1.0
        hit.final_score = hit.raw_score * scope_w * quality_w * recency_w

    # 6. Dedup por content hash (chunks identicos em multiplas colecoes —
    #    fica com o de maior final_score)
    by_content: dict[str, RetrievalHit] = {}
    for hit in all_hits:
        key = hit.content[:200]  # heuristica simples
        existing = by_content.get(key)
        if existing is None or hit.final_score > existing.final_score:
            by_content[key] = hit

    # 7. Ordena por final_score desc, retorna top-K
    ranked = sorted(by_content.values(), key=lambda h: h.final_score, reverse=True)
    return ranked[: params.top_k]


def _to_uuid(value: Any) -> UUID | None:
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except Exception:
        return None
