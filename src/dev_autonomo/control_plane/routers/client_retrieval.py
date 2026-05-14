"""Router /client/squads/{id}/retrieval/search — Bloco G.

Expoe a busca RAG com rerank pra cliente debugar/visualizar o que o
agente vai receber. Tambem util pra testar manualmente: cliente pode
fazer query e ver quais chunks aparecem.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dev_autonomo.common.enums import UserRole
from dev_autonomo.control_plane.dependencies import (
    get_session,
    require_client_context,
)
from dev_autonomo.db.models import Client, Squad
from dev_autonomo.services import rag_retriever
from dev_autonomo.services.rag_retriever import RetrievalParams

router = APIRouter(prefix="/client/squads", tags=["client / retrieval"])


class RetrievalRequest(BaseModel):
    query: str = Field(..., min_length=3)
    stack_slug: str | None = None
    stack_version: str | None = None
    top_k: int = Field(20, ge=1, le=100)


class RetrievalHitPublic(BaseModel):
    content: str
    source_id: UUID | None
    score: float
    scope: str
    source_quality: str
    license: str
    source_uri: str | None
    stack_version: str | None
    collection_slug: str
    metadata: dict[str, Any]


class RetrievalResponse(BaseModel):
    hits: list[RetrievalHitPublic]
    total: int


@router.post("/{squad_id}/retrieval/search", response_model=RetrievalResponse)
async def squad_retrieval_search(
    squad_id: UUID,
    body: RetrievalRequest,
    ctx: tuple[Client, UserRole] = Depends(require_client_context),
    session: AsyncSession = Depends(get_session),
) -> RetrievalResponse:
    """Busca rerank-aware nas coleções da squad + stack."""
    client, _ = ctx
    squad = (await session.execute(
        select(Squad).where(Squad.id == squad_id, Squad.client_id == client.id)
    )).scalar_one_or_none()
    if squad is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="squad nao encontrada")

    params = RetrievalParams(
        query=body.query,
        squad_id=squad.id,
        client_id=client.id,
        stack_slug=body.stack_slug,
        stack_version=body.stack_version,
        top_k=body.top_k,
    )
    hits = await rag_retriever.search(session, params)

    return RetrievalResponse(
        hits=[
            RetrievalHitPublic(
                content=h.content,
                source_id=h.source_id,
                score=h.final_score,
                scope=h.scope,
                source_quality=h.source_quality,
                license=h.license,
                source_uri=h.source_uri,
                stack_version=h.stack_version,
                collection_slug=h.collection_slug,
                metadata=h.metadata,
            )
            for h in hits
        ],
        total=len(hits),
    )
