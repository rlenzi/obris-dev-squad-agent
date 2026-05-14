"""Onboarding analyzer — orquestra OA contra repos da squad.

Bloco E do roadmap stack-knowledge. Wizard cliente chama:
1. POST /client/squads/{id}/run-onboarding-analysis
   → start_analysis() dispara OA em background. Retorna task_id imediatamente.
2. GET /client/squads/{id}/onboarding-status (polling)
   → get_analysis_status() retorna estado sintético + progress + manifest se pronto.
3. POST /client/squads/{id}/finalize-setup
   → consome manifest, cria skill_templates + AgentInstances.
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

import anthropic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dev_autonomo.agent_runtime.managed_runner import (
    ManagedTaskSpec,
    run_managed_task,
)
from dev_autonomo.common.enums import AgentTier, MemoryStoreKind, TaskStage, TaskStatus
from dev_autonomo.common.repos import normalize_github_https_url
from dev_autonomo.config import get_settings
from dev_autonomo.db.models import (
    AgentInstance,
    Client,
    SkillTemplate,
    Squad,
    SquadMemoryStore,
    Task,
)

logger = logging.getLogger(__name__)


# Title sintético da Task de onboarding (pra identificar entre outras tasks).
_ONBOARDING_TASK_TITLE_PREFIX = "[onboarding-analysis]"


@dataclass(slots=True)
class OnboardingStatus:
    """Estado de uma análise de onboarding."""

    task_id: UUID | None
    status: Literal["not_started", "pending", "extracting", "analyzing", "proposing", "completed", "failed"]
    current_step: str
    progress_pct: int  # 0-100
    manifest_ready_at: datetime | None = None
    error_message: str | None = None


# ---------------------------------------------------------------------------
# Start
# ---------------------------------------------------------------------------


async def start_analysis(
    session: AsyncSession,
    *,
    client: Client,
    squad: Squad,
    repo_urls: list[str],
    github_token: str | None = None,
) -> UUID:
    """Dispara OA em background contra os repos da squad.

    Idempotente: se ja existe analysis em andamento pra essa squad,
    retorna a Task existente.
    """
    # Verifica se ja tem análise rodando.
    existing = await _find_active_onboarding_task(session, squad.id)
    if existing is not None:
        logger.info("onboarding_analysis ja existe pra squad=%s task=%s",
                    squad.id, existing.id)
        return existing.id

    # Cria Task local
    task = Task(
        client_id=client.id,
        squad_id=squad.id,
        jira_workspace_url=client.jira_workspace_url or "",
        jira_issue_key=f"ONBOARDING-{squad.id}",
        title=f"{_ONBOARDING_TASK_TITLE_PREFIX} {squad.slug}",
        current_stage=TaskStage.DEMAND_RECEIVED,
        status=TaskStatus.IN_PROGRESS,
    )
    session.add(task)
    await session.flush()
    task_id = task.id
    await session.commit()

    # Resolve OA skill_template global (onboarding-analyst-v1)
    oa_skill = (await session.execute(
        select(SkillTemplate).where(SkillTemplate.slug == "onboarding-analyst-v1")
    )).scalar_one_or_none()
    if oa_skill is None or not oa_skill.anthropic_agent_id:
        raise RuntimeError(
            "Skill 'onboarding-analyst-v1' nao provisionado. "
            "Rode: python -m scripts.dev.provision_managed_agents"
        )

    # Cria/recupera memory_store kind=ONBOARDING pra squad
    memory_store_id = await _ensure_onboarding_memory_store(session, squad)
    await session.commit()

    # Constroi spec
    from pathlib import Path
    prompt_path = Path(
        "/home/rubens/dev-autonomo-workspace/dev-autonomo/prompts/onboarding/managed.md"
    )

    resources: list[dict] = []
    for repo_url in repo_urls:
        canonical = normalize_github_https_url(repo_url)
        if canonical is None:
            logger.warning("repo_url ignorado (formato nao reconhecido): %s", repo_url)
            continue
        if github_token:
            resources.append({
                "type": "github_repository",
                "url": canonical,
                "authorization_token": github_token,
                "checkout": {"type": "branch", "name": "main"},
                "mount_path": f"/mnt/repo/{_repo_dir_name(canonical)}",
            })
    if memory_store_id:
        resources.append({
            "type": "memory_store",
            "memory_store_id": memory_store_id,
            "access": "read_write",
            "instructions": (
                "Salve o manifesto detectado em manifest.json neste store."
            ),
        })

    def build_prompt(issue_key: str) -> str:
        repo_list = "\n".join(f"  - /mnt/repo/{_repo_dir_name(r)} (do GitHub {r})" for r in repo_urls)
        return (
            f"Você é o Onboarding Analyst. Squad: **{squad.name}** "
            f"(slug: {squad.slug}, cliente: {client.name}).\n\n"
            f"Repositórios montados:\n{repo_list}\n\n"
            f"Siga o fluxo obrigatório do system prompt: liste /mnt/repo/, "
            f"escaneie cada repo, infira stack/framework, proponha agentes, "
            f"salve manifest.json no memory_store provisionado, termine com "
            f"resumo em PT-BR.\n"
        )

    spec = ManagedTaskSpec(
        agent_name="Onboarding Analyst Plataforma",
        system_prompt_path=prompt_path,
        client_slug="dev-autonomo",  # OA roda no contexto da plataforma
        squad_slug="plataforma",
        model=oa_skill.model_alias,
        resources=resources,
        user_prompt_builder=build_prompt,
    )

    # Dispara em background
    asyncio.create_task(_run_oa_background(spec, task_id, squad.id))

    return task_id


async def _run_oa_background(spec: ManagedTaskSpec, task_id: UUID, squad_id: UUID) -> None:
    """Wrapper que captura erro e atualiza Task status."""
    try:
        result = await run_managed_task(spec, f"ONBOARDING-{squad_id}")
        logger.info("oa_analysis done task=%s completed=%s session=%s",
                    task_id, result.completed, result.session_id)
        # Marca task como concluída (managed_runner ja persiste session_id)
        from dev_autonomo.db.session import session_scope
        async with session_scope() as s:
            tk = await s.get(Task, task_id)
            if tk:
                tk.status = TaskStatus.DONE if result.completed else TaskStatus.FAILED
                tk.current_stage = TaskStage.MERGED if result.completed else TaskStage.FAILED
                await s.commit()
    except Exception:
        logger.exception("oa_analysis falhou task=%s", task_id)
        from dev_autonomo.db.session import session_scope
        async with session_scope() as s:
            tk = await s.get(Task, task_id)
            if tk:
                tk.status = TaskStatus.FAILED
                tk.current_stage = TaskStage.FAILED
                await s.commit()


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


async def get_analysis_status(
    session: AsyncSession, squad: Squad,
) -> OnboardingStatus:
    """Retorna estado sintetico da analise mais recente."""
    task = await _find_latest_onboarding_task(session, squad.id)
    if task is None:
        return OnboardingStatus(
            task_id=None, status="not_started",
            current_step="Não iniciado", progress_pct=0,
        )

    # Mapeia para steps sinteticos
    if task.status == TaskStatus.PENDING:
        return OnboardingStatus(
            task_id=task.id, status="pending",
            current_step="Aguardando inicio", progress_pct=5,
        )
    if task.status == TaskStatus.FAILED:
        return OnboardingStatus(
            task_id=task.id, status="failed",
            current_step="Falhou",
            progress_pct=0,
            error_message="Veja logs do task pra detalhes.",
        )
    if task.status == TaskStatus.DONE:
        # Confere se manifest existe no memory_store
        manifest_ok = await _manifest_available(session, squad)
        if manifest_ok:
            return OnboardingStatus(
                task_id=task.id, status="completed",
                current_step="Manifesto pronto",
                progress_pct=100,
                manifest_ready_at=task.closed_at or task.updated_at,
            )
        # Done mas sem manifest — provavelmente agente nao escreveu.
        return OnboardingStatus(
            task_id=task.id, status="failed",
            current_step="Agente terminou mas manifest.json nao foi gerado",
            progress_pct=0,
            error_message="OA terminou sem produzir manifest.json — checar transcript.",
        )

    # IN_PROGRESS — sub-status baseado em existencia de session_id e manifest parcial.
    if task.anthropic_session_id is None:
        return OnboardingStatus(
            task_id=task.id, status="extracting",
            current_step="Lendo repositórios", progress_pct=20,
        )
    # Heuristica simples: nao temos como saber meio-do-caminho via API atual.
    # Retornamos "analyzing" com progress=50.
    return OnboardingStatus(
        task_id=task.id, status="analyzing",
        current_step="Detectando frameworks e gerando manifesto",
        progress_pct=50,
    )


# ---------------------------------------------------------------------------
# Manifest reader
# ---------------------------------------------------------------------------


async def read_manifest(session: AsyncSession, squad: Squad) -> dict | None:
    """Le manifest.json do memory_store kind=ONBOARDING da squad."""
    mem = (await session.execute(
        select(SquadMemoryStore).where(
            SquadMemoryStore.squad_id == squad.id,
            SquadMemoryStore.kind == MemoryStoreKind.ONBOARDING,
        )
    )).scalar_one_or_none()
    if mem is None:
        return None

    anth = _build_anthropic_client()
    try:
        memories = list(anth.beta.memory_stores.memories.list(
            memory_store_id=mem.anthropic_store_id, limit=50,
        ))
    except Exception as exc:
        logger.warning("falha ao listar memories: %s", exc)
        return None

    for memory in memories:
        path = getattr(memory, "path", "")
        if not path.endswith("manifest.json"):
            continue
        # Baixa conteudo
        try:
            content = anth.beta.memory_stores.memories.retrieve(
                memory_id=memory.id,
                memory_store_id=mem.anthropic_store_id,
            )
            text = getattr(content, "content", None) or ""
            if text:
                return json.loads(text)
        except Exception as exc:
            logger.warning("falha ao ler manifest.json: %s", exc)
            continue

    return None


# ---------------------------------------------------------------------------
# Finalize setup
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class FinalizeSkillSpec:
    """Spec do que o cliente confirmou na tela 5 (1 entry por agente)."""

    # Modo 1: usar skill catalog existente (slug global)
    catalog_skill_slug: str | None = None
    # Modo 2: criar skill a partir de draft (já editado)
    draft_to_materialize: dict | None = None
    # Comum: nome legivel do AgentInstance + dominio
    instance_name: str = ""
    domain_business: str = "general"


async def finalize_setup(
    session: AsyncSession,
    *,
    client: Client,
    squad: Squad,
    skills_spec: list[FinalizeSkillSpec],
) -> list[AgentInstance]:
    """Cria skill_templates (modo 2) + AgentInstances pra squad. Atomico.

    Caller commita.
    """
    from dev_autonomo.services import skill_proposer
    from dev_autonomo.services.skill_proposer import SkillTemplateDraft

    instances: list[AgentInstance] = []
    for spec in skills_spec:
        # Resolve SkillTemplate (cria se draft)
        if spec.draft_to_materialize:
            draft = SkillTemplateDraft(
                slug=spec.draft_to_materialize["slug"],
                name=spec.draft_to_materialize["name"],
                description=spec.draft_to_materialize.get("description", ""),
                tier=AgentTier(spec.draft_to_materialize["tier"]),
                model_alias=spec.draft_to_materialize["model_alias"],
                system_prompt=spec.draft_to_materialize["system_prompt"],
                tools_enabled=spec.draft_to_materialize.get("tools_enabled", []),
                stack_primary=spec.draft_to_materialize.get("stack_primary", {}),
                stack_secondary=spec.draft_to_materialize.get("stack_secondary", []),
                knowledge_partitions=spec.draft_to_materialize.get("knowledge_partitions", []),
                template_variables=spec.draft_to_materialize.get("template_variables", {}),
                parent_stack_profile_id=UUID(spec.draft_to_materialize["parent_stack_profile_id"]),
            )
            skill = await skill_proposer.materialize_skill_from_draft(
                session, draft=draft, client_id=client.id,
                edited_system_prompt=spec.draft_to_materialize.get("system_prompt"),
            )
        else:
            # catalog: filtra por slug global (client_id NULL)
            skill = (await session.execute(
                select(SkillTemplate).where(
                    SkillTemplate.slug == spec.catalog_skill_slug,
                    SkillTemplate.client_id.is_(None),
                )
            )).scalar_one_or_none()
            if skill is None:
                raise ValueError(
                    f"skill_template global '{spec.catalog_skill_slug}' nao encontrado"
                )

        instance = AgentInstance(
            client_id=client.id,
            squad_id=squad.id,
            skill_template_id=skill.id,
            name=spec.instance_name or skill.name,
            domain_business=spec.domain_business,
        )
        session.add(instance)
        await session.flush()
        instances.append(instance)

    return instances


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_anthropic_client() -> anthropic.Anthropic:
    return anthropic.Anthropic(
        api_key=get_settings().ANTHROPIC_API_KEY.get_secret_value()
    )


def _repo_dir_name(repo_url: str) -> str:
    """Extrai 'owner-repo' do URL pra usar como dir name."""
    cleaned = repo_url.rstrip("/").replace(".git", "")
    parts = cleaned.split("/")
    if len(parts) >= 2:
        return f"{parts[-2]}-{parts[-1]}"
    return cleaned.split("/")[-1] or "repo"


async def _find_active_onboarding_task(
    session: AsyncSession, squad_id: UUID,
) -> Task | None:
    """Task com title prefix + status IN_PROGRESS."""
    rows = (await session.execute(
        select(Task).where(
            Task.squad_id == squad_id,
            Task.title.like(f"{_ONBOARDING_TASK_TITLE_PREFIX}%"),
            Task.status == TaskStatus.IN_PROGRESS,
        ).order_by(Task.created_at.desc()).limit(1)
    )).scalars().all()
    return rows[0] if rows else None


async def _find_latest_onboarding_task(
    session: AsyncSession, squad_id: UUID,
) -> Task | None:
    """Task de onboarding mais recente (qualquer status)."""
    rows = (await session.execute(
        select(Task).where(
            Task.squad_id == squad_id,
            Task.title.like(f"{_ONBOARDING_TASK_TITLE_PREFIX}%"),
        ).order_by(Task.created_at.desc()).limit(1)
    )).scalars().all()
    return rows[0] if rows else None


async def _manifest_available(session: AsyncSession, squad: Squad) -> bool:
    """Tenta ler manifest pra confirmar disponibilidade (sem cachear)."""
    manifest = await read_manifest(session, squad)
    return manifest is not None


async def _ensure_onboarding_memory_store(
    session: AsyncSession, squad: Squad,
) -> str | None:
    """Reutiliza _ensure_onboarding_memory_store do managed_agent_run_trigger."""
    from dev_autonomo.control_plane.services.managed_agent_run_trigger import (
        _ensure_onboarding_memory_store as _ensure,
    )
    return await _ensure(session, squad)
