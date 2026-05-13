"""Wrapper async do Qdrant com collection management por squad+partition."""

from __future__ import annotations

from enum import StrEnum
from typing import Any
from uuid import UUID

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)

from dev_autonomo.config import get_settings


class KnowledgePartition(StrEnum):
    CODE = "code"
    PLAYBOOK = "playbook"
    ARCHITECTURE = "architecture"
    CONVENTIONS = "conventions"
    API_CONTRACTS = "api_contracts"
    BUSINESS = "business"
    DECISIONS = "decisions"
    RUNBOOK = "runbook"


EMBEDDING_DIM = 1024  # voyage-code-3 padrao


class QdrantKnowledgeStore:
    """Acesso ao Qdrant particionado por (partition, squad_id).

    Cada combinacao (partition, squad_id) vira uma collection separada.
    Nome da collection: f"{partition}_{squad_id.hex}".
    """

    def __init__(self, client: AsyncQdrantClient | None = None) -> None:
        if client is None:
            settings = get_settings()
            client = AsyncQdrantClient(
                host=settings.QDRANT_HOST,
                port=settings.QDRANT_PORT,
                prefer_grpc=False,
            )
        self._client = client

    @staticmethod
    def collection_name(partition: KnowledgePartition, squad_id: UUID) -> str:
        return f"{partition.value}_{squad_id.hex}"

    async def ensure_collection(
        self,
        partition: KnowledgePartition,
        squad_id: UUID,
        vector_size: int = EMBEDDING_DIM,
    ) -> str:
        """Cria a collection se ainda nao existir. Retorna o nome."""
        name = self.collection_name(partition, squad_id)
        if not await self._client.collection_exists(name):
            await self._client.create_collection(
                collection_name=name,
                vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
            )
            # Indexes por payload usados em filtros frequentes
            for field in ("file_path", "kind", "name", "client_id", "repo"):
                await self._client.create_payload_index(
                    collection_name=name,
                    field_name=field,
                    field_schema="keyword",
                )
        return name

    UPSERT_BATCH_SIZE = 64

    async def upsert_points(
        self,
        partition: KnowledgePartition,
        squad_id: UUID,
        points: list[PointStruct],
    ) -> None:
        if not points:
            return
        name = self.collection_name(partition, squad_id)
        for i in range(0, len(points), self.UPSERT_BATCH_SIZE):
            batch = points[i : i + self.UPSERT_BATCH_SIZE]
            await self._client.upsert(collection_name=name, points=batch, wait=True)

    async def delete_by_file(
        self,
        partition: KnowledgePartition,
        squad_id: UUID,
        file_path: str,
    ) -> None:
        """Apaga todos os pontos vinculados a um arquivo (usado em reindex incremental)."""
        name = self.collection_name(partition, squad_id)
        await self._client.delete(
            collection_name=name,
            points_selector=Filter(
                must=[FieldCondition(key="file_path", match=MatchValue(value=file_path))]
            ),
            wait=True,
        )

    async def search(
        self,
        partition: KnowledgePartition,
        squad_id: UUID,
        query_vector: list[float],
        limit: int = 10,
        filter_payload: dict[str, Any] | None = None,
    ) -> list:
        """Busca por similaridade. filter_payload aplica match exato em campos do payload."""
        name = self.collection_name(partition, squad_id)
        flt = None
        if filter_payload:
            flt = Filter(
                must=[
                    FieldCondition(key=k, match=MatchValue(value=v))
                    for k, v in filter_payload.items()
                ]
            )
        result = await self._client.query_points(
            collection_name=name,
            query=query_vector,
            limit=limit,
            query_filter=flt,
            with_payload=True,
        )
        return result.points

    async def count(
        self,
        partition: KnowledgePartition,
        squad_id: UUID,
        filter_payload: dict[str, Any] | None = None,
    ) -> int:
        name = self.collection_name(partition, squad_id)
        flt = None
        if filter_payload:
            flt = Filter(
                must=[
                    FieldCondition(key=k, match=MatchValue(value=v))
                    for k, v in filter_payload.items()
                ]
            )
        result = await self._client.count(collection_name=name, count_filter=flt, exact=True)
        return result.count

    async def drop_collection(
        self, partition: KnowledgePartition, squad_id: UUID
    ) -> None:
        name = self.collection_name(partition, squad_id)
        await self._client.delete_collection(collection_name=name)

    async def close(self) -> None:
        await self._client.close()
