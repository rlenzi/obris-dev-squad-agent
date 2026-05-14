"""Router /client/squads/{id}/knowledge — coleção privada da squad."""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dev_autonomo.common.enums import (
    RagSourceKind,
    RagSourceLicense,
    RagSourceQuality,
    RagSourceScope,
    UserRole,
)
from dev_autonomo.control_plane.dependencies import (
    get_current_user,
    get_session,
    require_client_context,
)
from dev_autonomo.control_plane.schemas.rag_source import (
    RagSourceIngestResponse,
    RagSourcePublic,
)
from dev_autonomo.db.models import Client, RagSource, Squad, User
from dev_autonomo.services import rag_ingest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/client/squads", tags=["client / squad knowledge"])


def _collection_for_squad(squad_id: UUID) -> str:
    return f"playbook:{squad_id}"


def _require_client_admin(role: UserRole) -> None:
    if role != UserRole.CLIENT_ADMIN:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="apenas CLIENT_ADMIN pode gerenciar knowledge da squad.",
        )


async def _resolve_squad(
    session: AsyncSession, client: Client, squad_id: UUID,
) -> Squad:
    squad = (await session.execute(
        select(Squad).where(Squad.id == squad_id, Squad.client_id == client.id)
    )).scalar_one_or_none()
    if squad is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="squad nao encontrada")
    return squad


@router.get(
    "/{squad_id}/knowledge/sources",
    response_model=list[RagSourcePublic],
)
async def list_squad_sources(
    squad_id: UUID,
    ctx: tuple[Client, UserRole] = Depends(require_client_context),
    session: AsyncSession = Depends(get_session),
) -> list[RagSource]:
    """Lista fontes privadas da squad (qualquer membership le)."""
    client, _ = ctx
    await _resolve_squad(session, client, squad_id)
    collection = _collection_for_squad(squad_id)
    rows = (await session.execute(
        select(RagSource)
        .where(
            RagSource.collection_slug == collection,
            RagSource.scope == RagSourceScope.CLIENT_PRIVATE,
            RagSource.client_id == client.id,
        )
        .order_by(RagSource.created_at.desc())
    )).scalars().all()
    return rows


@router.post(
    "/{squad_id}/knowledge/sources/text",
    response_model=RagSourceIngestResponse,
    status_code=status.HTTP_201_CREATED,
)
async def ingest_squad_text(
    squad_id: UUID,
    text: str = Form(..., min_length=50),
    source_quality: RagSourceQuality = Form(RagSourceQuality.INTERNAL),
    stack_version: str | None = Form(None),
    tags: str = Form(""),
    ctx: tuple[Client, UserRole] = Depends(require_client_context),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> RagSourceIngestResponse:
    """Cliente sobe texto privado pra squad. License default=client_internal."""
    client, role = ctx
    _require_client_admin(role)
    await _resolve_squad(session, client, squad_id)

    request = rag_ingest.IngestRequest(
        collection_slug=_collection_for_squad(squad_id),
        kind=RagSourceKind.PASTED_TEXT,
        scope=RagSourceScope.CLIENT_PRIVATE,
        license=RagSourceLicense.CLIENT_INTERNAL,
        source_quality=source_quality,
        stack_version=stack_version,
        tags=[t.strip() for t in tags.split(",") if t.strip()],
        client_id=client.id,
        uploaded_by_user_id=current_user.id,
    )
    result = await rag_ingest.ingest(session, request, raw_text=text)
    await session.commit()
    return _ingest_to_response(result)


@router.post(
    "/{squad_id}/knowledge/sources/file",
    response_model=RagSourceIngestResponse,
    status_code=status.HTTP_201_CREATED,
)
async def ingest_squad_file(
    squad_id: UUID,
    file: UploadFile = File(...),
    source_quality: RagSourceQuality = Form(RagSourceQuality.INTERNAL),
    stack_version: str | None = Form(None),
    tags: str = Form(""),
    ctx: tuple[Client, UserRole] = Depends(require_client_context),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> RagSourceIngestResponse:
    """Cliente sobe arquivo privado pra squad."""
    client, role = ctx
    _require_client_admin(role)
    await _resolve_squad(session, client, squad_id)

    content = await file.read()
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            detail="arquivo > 50MB nao suportado")

    request = rag_ingest.IngestRequest(
        collection_slug=_collection_for_squad(squad_id),
        kind=RagSourceKind.FILE_UPLOAD,
        scope=RagSourceScope.CLIENT_PRIVATE,
        license=RagSourceLicense.CLIENT_INTERNAL,
        source_quality=source_quality,
        stack_version=stack_version,
        tags=[t.strip() for t in tags.split(",") if t.strip()],
        source_uri=file.filename,
        client_id=client.id,
        uploaded_by_user_id=current_user.id,
    )
    result = await rag_ingest.ingest(
        session, request, file_bytes=content, file_name=file.filename or "unnamed",
    )
    await session.commit()
    return _ingest_to_response(result)


@router.delete(
    "/{squad_id}/knowledge/sources/{source_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_squad_source(
    squad_id: UUID,
    source_id: UUID,
    ctx: tuple[Client, UserRole] = Depends(require_client_context),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Remove fonte privada da squad."""
    client, role = ctx
    _require_client_admin(role)
    await _resolve_squad(session, client, squad_id)

    source = await session.get(RagSource, source_id)
    if source is None or source.client_id != client.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="fonte nao encontrada")
    await rag_ingest.delete_source(session, source_id)
    await session.commit()


def _ingest_to_response(result: rag_ingest.IngestResult) -> RagSourceIngestResponse:
    return RagSourceIngestResponse(
        rag_source_id=result.rag_source_id,
        status=result.status,
        indexed_chunks=result.indexed_chunks,
        source_hash=result.source_hash,
        error_message=result.error_message,
        deduplicated=(result.error_message or "").startswith("ja existe"),
    )
