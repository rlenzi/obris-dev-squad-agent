"""Retriever do Knowledge Hub com boundary filter baseado no manifesto da squad."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from qdrant_client.http.exceptions import UnexpectedResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dev_autonomo.common.repos import normalize_repo_ids
from dev_autonomo.db.models import Manifest, Squad
from dev_autonomo.knowledge.qdrant_client import (
    KnowledgePartition,
    QdrantKnowledgeStore,
)
from dev_autonomo.knowledge.voyage_client import VoyageEmbeddingClient

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class RetrievalHit:
    score: float
    kind: str
    name: str
    parent: str | None
    file_path: str
    language: str
    repo: str
    signature: str | None
    content: str
    start_line: int
    end_line: int


@dataclass(slots=True)
class RetrievalResult:
    hits: list[RetrievalHit]
    query: str
    partition: KnowledgePartition
    squad_id: UUID
    duration_seconds: float
    filtered_by_manifest: bool
    raw_results_before_filter: int
    discarded_out_of_scope: int
    partition_missing: bool = False


class ManifestNotFoundError(LookupError):
    """A squad nao tem um manifesto ativo (current_manifest_id NULL)."""


class KnowledgeRetriever:
    """Recupera chunks do Knowledge Hub respeitando o boundary do manifesto.

    Camada 2 da defesa em profundidade: o agente so consegue *ver* o que sua
    squad possui. Mesmo que o Qdrant tenha mais dados (em testes ou bugs),
    o retriever filtra antes de devolver.
    """

    DEFAULT_OVERFETCH_FACTOR = 3

    def __init__(
        self,
        session: AsyncSession,
        voyage: VoyageEmbeddingClient | None = None,
        qdrant: QdrantKnowledgeStore | None = None,
    ) -> None:
        self._session = session
        self._voyage = voyage or VoyageEmbeddingClient()
        self._qdrant = qdrant or QdrantKnowledgeStore()

    async def retrieve(
        self,
        *,
        squad_id: UUID,
        query: str,
        partition: KnowledgePartition = KnowledgePartition.CODE,
        limit: int = 10,
        kind_filter: str | None = None,
        repo_filter: str | None = None,
        strict_manifest: bool = True,
    ) -> RetrievalResult:
        """Busca semantica filtrada por manifest.

        strict_manifest=True (default): se squad nao tem manifest ativo, erra.
        strict_manifest=False: pula o filtro (modo dev/teste).
        """
        started = time.monotonic()

        # 1) Carrega manifest ativo
        manifest = await self._load_active_manifest(squad_id)
        if manifest is None and strict_manifest:
            raise ManifestNotFoundError(
                f"Squad {squad_id} nao tem manifest ativo. "
                "Defina current_manifest_id ou passe strict_manifest=False."
            )

        # 2) Embedding da query
        query_vec = await self._voyage.embed_query(query)

        # 3) Filtros nativos do Qdrant (matches exatos baratos)
        payload_filter: dict[str, Any] = {}
        if kind_filter:
            payload_filter["kind"] = kind_filter
        if repo_filter:
            payload_filter["repo"] = repo_filter

        # 4) Boundary filter pelo manifest: extrai allow-list de repos
        allowed_repos: set[str] | None = None
        if manifest is not None and partition == KnowledgePartition.CODE:
            owns = (manifest.content or {}).get("owns", {})
            repo_list = owns.get("repos", [])
            if repo_list:
                allowed_repos = normalize_repo_ids(repo_list)

        # 5) Over-fetch quando ha post-filter por manifesto
        fetch_limit = (
            limit * self.DEFAULT_OVERFETCH_FACTOR if allowed_repos else limit
        )
        try:
            raw = await self._qdrant.search(
                partition=partition,
                squad_id=squad_id,
                query_vector=query_vec,
                limit=fetch_limit,
                filter_payload=payload_filter or None,
            )
        except UnexpectedResponse as exc:
            if exc.status_code == 404:
                collection_name = self._qdrant.collection_name(partition, squad_id)
                logger.warning(
                    "Partition '%s' nao encontrada no Qdrant (collection '%s' inexistente). "
                    "Retornando lista vazia. Execute a mineracao para popular esta particao.",
                    partition.value,
                    collection_name,
                )
                duration = time.monotonic() - started
                return RetrievalResult(
                    hits=[],
                    query=query,
                    partition=partition,
                    squad_id=squad_id,
                    duration_seconds=duration,
                    filtered_by_manifest=False,
                    raw_results_before_filter=0,
                    discarded_out_of_scope=0,
                    partition_missing=True,
                )
            raise

        # 6) Post-filter por allow-list de repos
        hits: list[RetrievalHit] = []
        discarded = 0
        for point in raw:
            payload = point.payload or {}
            if allowed_repos is not None and payload.get("repo") not in allowed_repos:
                discarded += 1
                continue
            hits.append(
                RetrievalHit(
                    score=float(point.score),
                    kind=payload.get("kind", "unknown"),
                    name=payload.get("name", ""),
                    parent=payload.get("parent"),
                    file_path=payload.get("file_path", ""),
                    language=payload.get("language", ""),
                    repo=payload.get("repo", ""),
                    signature=payload.get("signature"),
                    content=payload.get("content", ""),
                    start_line=int(payload.get("start_line", 0) or 0),
                    end_line=int(payload.get("end_line", 0) or 0),
                )
            )
            if len(hits) >= limit:
                break

        duration = time.monotonic() - started
        return RetrievalResult(
            hits=hits,
            query=query,
            partition=partition,
            squad_id=squad_id,
            duration_seconds=duration,
            filtered_by_manifest=manifest is not None,
            raw_results_before_filter=len(raw),
            discarded_out_of_scope=discarded,
        )

    async def _load_active_manifest(self, squad_id: UUID) -> Manifest | None:
        stmt = (
            select(Manifest)
            .join(Squad, Squad.current_manifest_id == Manifest.id)
            .where(Squad.id == squad_id)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
