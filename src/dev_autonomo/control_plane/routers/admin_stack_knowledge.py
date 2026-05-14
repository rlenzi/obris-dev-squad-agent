"""Router /admin/stack-knowledge — gerencia coleções stack_patterns:{slug} (cross-tenant).

SYSTEM_ADMIN apenas. Sobe material publico (docs oficiais) ou
conhecimento Orbis (experiencia do admin) em coleções cross-tenant.
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from dev_autonomo.common.enums import (
    RagSourceKind,
    RagSourceLicense,
    RagSourceQuality,
    RagSourceScope,
)
from dev_autonomo.control_plane.dependencies import (
    get_current_user,
    get_session,
    require_system_admin,
)
from dev_autonomo.control_plane.schemas.rag_source import (
    RagSourceIngestResponse,
    RagSourcePublic,
    StackCollectionSummary,
)
from dev_autonomo.db.models import RagSource, StackProfile, User
from dev_autonomo.services import rag_ingest

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin/stack-knowledge",
    tags=["admin / stack knowledge"],
    dependencies=[Depends(require_system_admin)],
)


def _collection_slug_for_stack(stack_slug: str) -> str:
    return f"stack_patterns:{stack_slug}"


@router.get("", response_model=list[StackCollectionSummary])
async def list_stack_collections(
    session: AsyncSession = Depends(get_session),
) -> list[StackCollectionSummary]:
    """Lista colecoes stack_patterns:{slug} com contadores agregados."""
    profiles = (await session.execute(
        select(StackProfile).where(StackProfile.active.is_(True)).order_by(StackProfile.name)
    )).scalars().all()

    summaries: list[StackCollectionSummary] = []
    for profile in profiles:
        slug = _collection_slug_for_stack(profile.slug)
        agg = (await session.execute(
            select(
                func.count(RagSource.id),
                func.coalesce(func.sum(RagSource.indexed_chunks), 0),
            ).where(RagSource.collection_slug == slug)
        )).one()
        total_sources, total_chunks = int(agg[0] or 0), int(agg[1] or 0)

        by_quality_rows = (await session.execute(
            select(RagSource.source_quality, func.count(RagSource.id))
            .where(RagSource.collection_slug == slug)
            .group_by(RagSource.source_quality)
        )).all()
        sources_by_quality = {
            row[0].value: int(row[1]) for row in by_quality_rows
        }

        summaries.append(StackCollectionSummary(
            stack_slug=profile.slug,
            stack_name=profile.name,
            total_sources=total_sources,
            total_chunks=total_chunks,
            sources_by_quality=sources_by_quality,
            clients_using=0,  # TODO: agregar via squads.manifest stack
        ))
    return summaries


@router.get("/{stack_slug}/sources", response_model=list[RagSourcePublic])
async def list_sources(
    stack_slug: str,
    session: AsyncSession = Depends(get_session),
) -> list[RagSource]:
    """Lista fontes indexadas naquela stack (cross-tenant)."""
    collection = _collection_slug_for_stack(stack_slug)
    rows = (await session.execute(
        select(RagSource)
        .where(
            RagSource.collection_slug == collection,
            RagSource.scope == RagSourceScope.CROSS_TENANT,
        )
        .order_by(RagSource.created_at.desc())
    )).scalars().all()
    return rows


@router.post(
    "/{stack_slug}/sources/text",
    response_model=RagSourceIngestResponse,
    status_code=status.HTTP_201_CREATED,
)
async def ingest_pasted_text(
    stack_slug: str,
    text: str = Form(..., min_length=50),
    license: RagSourceLicense = Form(...),
    source_quality: RagSourceQuality = Form(...),
    stack_version: str | None = Form(None),
    tags: str = Form("", description="CSV de tags"),
    has_redistribution_right: bool = Form(False),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> RagSourceIngestResponse:
    """Ingest de texto colado direto (cross-tenant admin)."""
    _validate_redistribution(license, has_redistribution_right)
    await _ensure_stack_exists(session, stack_slug)

    request = rag_ingest.IngestRequest(
        collection_slug=_collection_slug_for_stack(stack_slug),
        kind=RagSourceKind.PASTED_TEXT,
        scope=RagSourceScope.CROSS_TENANT,
        license=license,
        source_quality=source_quality,
        stack_version=stack_version,
        tags=[t.strip() for t in tags.split(",") if t.strip()],
        uploaded_by_user_id=current_user.id,
    )
    result = await rag_ingest.ingest(session, request, raw_text=text)
    await session.commit()
    return _ingest_to_response(result)


@router.post(
    "/{stack_slug}/sources/url",
    response_model=RagSourceIngestResponse,
    status_code=status.HTTP_201_CREATED,
)
async def ingest_url(
    stack_slug: str,
    url: str = Form(..., min_length=10),
    license: RagSourceLicense = Form(...),
    source_quality: RagSourceQuality = Form(...),
    stack_version: str | None = Form(None),
    tags: str = Form(""),
    has_redistribution_right: bool = Form(False),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> RagSourceIngestResponse:
    """Fetch + ingest de URL (cross-tenant admin)."""
    _validate_redistribution(license, has_redistribution_right)
    await _ensure_stack_exists(session, stack_slug)

    request = rag_ingest.IngestRequest(
        collection_slug=_collection_slug_for_stack(stack_slug),
        kind=RagSourceKind.URL_FETCH,
        scope=RagSourceScope.CROSS_TENANT,
        license=license,
        source_quality=source_quality,
        stack_version=stack_version,
        tags=[t.strip() for t in tags.split(",") if t.strip()],
        source_uri=url,
        uploaded_by_user_id=current_user.id,
    )
    result = await rag_ingest.ingest(session, request)
    await session.commit()
    return _ingest_to_response(result)


@router.post(
    "/{stack_slug}/sources/file",
    response_model=RagSourceIngestResponse,
    status_code=status.HTTP_201_CREATED,
)
async def ingest_file(
    stack_slug: str,
    file: UploadFile = File(...),
    license: RagSourceLicense = Form(...),
    source_quality: RagSourceQuality = Form(...),
    stack_version: str | None = Form(None),
    tags: str = Form(""),
    has_redistribution_right: bool = Form(False),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> RagSourceIngestResponse:
    """Upload de arquivo (PDF/DOCX/MD/TXT) cross-tenant admin."""
    _validate_redistribution(license, has_redistribution_right)
    await _ensure_stack_exists(session, stack_slug)

    content = await file.read()
    if len(content) > 50 * 1024 * 1024:  # 50MB
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            detail="arquivo > 50MB nao suportado")

    request = rag_ingest.IngestRequest(
        collection_slug=_collection_slug_for_stack(stack_slug),
        kind=RagSourceKind.FILE_UPLOAD,
        scope=RagSourceScope.CROSS_TENANT,
        license=license,
        source_quality=source_quality,
        stack_version=stack_version,
        tags=[t.strip() for t in tags.split(",") if t.strip()],
        source_uri=file.filename,
        uploaded_by_user_id=current_user.id,
    )
    result = await rag_ingest.ingest(
        session, request,
        file_bytes=content, file_name=file.filename or "unnamed",
    )
    await session.commit()
    return _ingest_to_response(result)


@router.delete(
    "/{stack_slug}/sources/{source_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_source(
    stack_slug: str,
    source_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> None:
    """Remove fonte + seus chunks no Qdrant."""
    collection = _collection_slug_for_stack(stack_slug)
    source = (await session.execute(
        select(RagSource).where(
            RagSource.id == source_id,
            RagSource.collection_slug == collection,
        )
    )).scalar_one_or_none()
    if source is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="fonte nao encontrada")
    await rag_ingest.delete_source(session, source_id)
    await session.commit()


# ---- helpers ----


def _validate_redistribution(
    license: RagSourceLicense, has_redistribution_right: bool,
) -> None:
    if license == RagSourceLicense.REDISTRIBUTABLE and not has_redistribution_right:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=(
                "Para license=redistributable em coleção cross-tenant, "
                "precisa marcar has_redistribution_right=true (log auditável)."
            ),
        )


async def _ensure_stack_exists(session: AsyncSession, stack_slug: str) -> None:
    profile = (await session.execute(
        select(StackProfile).where(StackProfile.slug == stack_slug)
    )).scalar_one_or_none()
    if profile is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=f"stack profile '{stack_slug}' não encontrado. "
                   f"Veja GET /admin/stack-knowledge pra lista válida.",
        )


def _ingest_to_response(result: rag_ingest.IngestResult) -> RagSourceIngestResponse:
    return RagSourceIngestResponse(
        rag_source_id=result.rag_source_id,
        status=result.status,
        indexed_chunks=result.indexed_chunks,
        source_hash=result.source_hash,
        error_message=result.error_message,
        deduplicated=(result.error_message or "").startswith("ja existe"),
    )
