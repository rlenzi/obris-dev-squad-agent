"""Router /client/squads/{id}/{run-onboarding-analysis,onboarding-status,finalize-setup}.

Bloco E do roadmap stack-knowledge — orquestra OA + materializacao
de skills + criacao de AgentInstances.
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dev_autonomo.common.encryption import SecretEncryptor
from dev_autonomo.common.enums import SecretKind, UserRole
from dev_autonomo.control_plane.dependencies import (
    get_session,
    require_client_context,
)
from dev_autonomo.control_plane.schemas.onboarding import (
    FinalizeSetupRequest,
    FinalizeSetupResponse,
    ManifestResponse,
    OnboardingStatusResponse,
    RunAnalysisRequest,
    RunAnalysisResponse,
)
from dev_autonomo.db.models import Client, EncryptedSecret, Squad
from dev_autonomo.services import onboarding_analyzer
from dev_autonomo.services.onboarding_analyzer import FinalizeSkillSpec

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/client/squads", tags=["client / onboarding"])


def _require_client_admin(role: UserRole) -> None:
    if role != UserRole.CLIENT_ADMIN:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="apenas CLIENT_ADMIN.",
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


async def _client_github_token(session: AsyncSession, client_id: UUID) -> str | None:
    """Decripta GitHub token do cliente, se existir."""
    cred = (await session.execute(
        select(EncryptedSecret).where(
            EncryptedSecret.client_id == client_id,
            EncryptedSecret.kind == SecretKind.GITHUB_TOKEN,
        )
    )).scalar_one_or_none()
    if cred is None:
        return None
    return SecretEncryptor().decrypt(cred.encrypted_value)


@router.post(
    "/{squad_id}/run-onboarding-analysis",
    response_model=RunAnalysisResponse,
)
async def run_onboarding_analysis(
    squad_id: UUID,
    body: RunAnalysisRequest,
    ctx: tuple[Client, UserRole] = Depends(require_client_context),
    session: AsyncSession = Depends(get_session),
) -> RunAnalysisResponse:
    """Dispara OA em background. Idempotente — re-run retorna mesmo task se ja rodando."""
    client, role = ctx
    _require_client_admin(role)
    squad = await _resolve_squad(session, client, squad_id)

    # Detecta se ja tem analise rodando
    existing = await onboarding_analyzer._find_active_onboarding_task(session, squad.id)
    already = existing is not None

    github_token = await _client_github_token(session, client.id)
    if github_token is None and any("github.com" in u for u in body.repo_urls):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=(
                "Cliente precisa de credencial GITHUB_TOKEN antes de rodar "
                "onboarding em repos privados. Configure em /client/credentials."
            ),
        )

    try:
        task_id = await onboarding_analyzer.start_analysis(
            session, client=client, squad=squad,
            repo_urls=body.repo_urls, github_token=github_token,
        )
    except RuntimeError as exc:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    await session.commit()

    return RunAnalysisResponse(
        task_id=task_id,
        status="already_running" if already else "started",
    )


@router.get(
    "/{squad_id}/onboarding-status",
    response_model=OnboardingStatusResponse,
)
async def get_onboarding_status(
    squad_id: UUID,
    ctx: tuple[Client, UserRole] = Depends(require_client_context),
    session: AsyncSession = Depends(get_session),
) -> OnboardingStatusResponse:
    """Polling endpoint — retorna estado sintetico."""
    client, _ = ctx
    squad = await _resolve_squad(session, client, squad_id)
    state = await onboarding_analyzer.get_analysis_status(session, squad)
    return OnboardingStatusResponse(
        task_id=state.task_id,
        status=state.status,
        current_step=state.current_step,
        progress_pct=state.progress_pct,
        manifest_ready_at=state.manifest_ready_at,
        error_message=state.error_message,
    )


@router.get(
    "/{squad_id}/onboarding-manifest",
    response_model=ManifestResponse,
)
async def get_onboarding_manifest(
    squad_id: UUID,
    ctx: tuple[Client, UserRole] = Depends(require_client_context),
    session: AsyncSession = Depends(get_session),
) -> ManifestResponse:
    """Le manifest.json do memory_store kind=ONBOARDING da squad."""
    client, _ = ctx
    squad = await _resolve_squad(session, client, squad_id)
    manifest = await onboarding_analyzer.read_manifest(session, squad)
    if manifest is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail="manifest ainda nao disponivel — aguarde OA terminar.",
        )
    return ManifestResponse(raw=manifest)


@router.post(
    "/{squad_id}/finalize-setup",
    response_model=FinalizeSetupResponse,
)
async def finalize_setup(
    squad_id: UUID,
    body: FinalizeSetupRequest,
    ctx: tuple[Client, UserRole] = Depends(require_client_context),
    session: AsyncSession = Depends(get_session),
) -> FinalizeSetupResponse:
    """Cria skill_templates (drafts) + AgentInstances."""
    client, role = ctx
    _require_client_admin(role)
    squad = await _resolve_squad(session, client, squad_id)

    specs = [
        FinalizeSkillSpec(
            catalog_skill_slug=entry.catalog_skill_slug,
            draft_to_materialize=entry.draft_to_materialize,
            instance_name=entry.instance_name,
            domain_business=entry.domain_business,
        )
        for entry in body.skills
    ]

    try:
        instances = await onboarding_analyzer.finalize_setup(
            session, client=client, squad=squad, skills_spec=specs,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc))
    await session.commit()

    return FinalizeSetupResponse(
        agent_instance_ids=[i.id for i in instances],
        created_skill_ids=[i.skill_template_id for i in instances],
    )
