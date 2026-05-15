"""Onboarding Analyzer v2 — orquestrador das 6 etapas com state machine.

Substitui ``services/onboarding_analyzer.py`` (que sera deprecated). O v2
roda em background apos ``POST /run-onboarding-analysis`` e atualiza
``Task.current_step`` + ``Task.step_label`` + ``Task.scan_progress`` em
cada transicao pra que o frontend (tela 2 viva) mostre progresso real.

Sequencia:
  1. clone local       — git clone shallow em CLONE_BASE_DIR/{cid}/{tid}/
  2. scan filesystem   — classifica arquivos elegiveis (chunk_kind)
  3. oa_scan           — Managed Agent escaneia, produz OnboardingAnalysisOutput
  4. indexing          — RAG ingest dos arquivos elegiveis em playbook:{sid}
  5. finalizing        — persiste Stacks + manifest no memory_store
  6. grading           — Claude Haiku checa rubric; retry OA ate 3x se falhar

Erros:
  - qualquer etapa que explode → marca task FAILED com motivo claro,
    NAO propaga pra fora do background task (event loop main precisa
    seguir vivo)
  - cleanup do clone SEMPRE em finally, sucesso ou falha

Cancel:
  - cliente pode disparar POST cancel-onboarding-analysis
  - background task checa task.status a cada step transition; se virou
    CANCELLED, sai cedo com cleanup
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import ValidationError

from dev_autonomo.common.enums import (
    MemoryStoreKind, OutcomeStatus, StackStatus, TaskStage, TaskStatus,
)
from dev_autonomo.common.repos import normalize_github_https_url
from dev_autonomo.config import get_settings
from dev_autonomo.db.models import (
    Client, Squad, SquadMemoryStore, Stack, StackProfile, Task,
)
from dev_autonomo.db.session import session_scope
from dev_autonomo.onboarding.grader import (
    DEFAULT_OA_RUBRIC, GraderVerdict, grade_output,
)
from dev_autonomo.onboarding.local_repo_clone import (
    CloneError, cleanup_clone, clone_repo, get_clone_path,
)
from dev_autonomo.onboarding.rag_indexer import (
    IndexResult, index_scanned_files,
)
from dev_autonomo.onboarding.repo_scanner import ScanResult, scan_filesystem
from dev_autonomo.onboarding.schemas import OnboardingAnalysisOutput

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------


# Mensagens em primeira pessoa pra cada etapa. Aparecem na tela 2 viva.
STEP_LABELS: dict[str, str] = {
    "cloning": (
        "Trazendo seu código pra eu poder ler. Não fico com cópia depois, "
        "é só durante a análise."
    ),
    "scanning": (
        "Estou olhando arquivo por arquivo pra entender a forma do projeto: "
        "que linguagens aparecem, que frameworks são usados, como as pastas "
        "estão organizadas, onde está o quê."
    ),
    "oa_scanning": (
        "Agora estou explorando o seu código com mais profundidade — lendo "
        "READMEs, configs, amostras de cada área, histórico de commits. "
        "Isso vai me dizer quais agentes fazem sentido pra sua squad."
    ),
    "indexing": (
        "Esse é o passo mais demorado. Estou pegando trechos do seu código "
        "e transformando em uma base de busca que os agentes vão consultar "
        "depois — quando precisarem entender uma convenção, achar onde algo "
        "está implementado ou seguir um padrão que você já usa."
    ),
    "finalizing": (
        "Quase pronto. Estou organizando as stacks que detectei e salvando "
        "tudo na sua squad."
    ),
    "grading": (
        "Pedindo uma segunda opinião antes de finalizar — um avaliador "
        "independente vai conferir que cobri o suficiente do seu código."
    ),
}


_ONBOARDING_TASK_TITLE_PREFIX = "[onboarding-analysis]"


# ---------------------------------------------------------------------------
# API publica
# ---------------------------------------------------------------------------


async def start_analysis(
    session: AsyncSession,
    *,
    client: Client,
    squad: Squad,
    repo_urls: list[str],
    github_token: str | None = None,
) -> UUID:
    """Dispara OA scan v2 em background contra os repos da squad.

    Idempotente: se ja existe analise IN_PROGRESS pra essa squad, retorna
    o task_id existente sem criar nova. Pra retentar apos falha, cancele
    a task FAILED primeiro (ou aguarde cleanup automatico).

    Args:
        session: para criar a Task (commit antes de retornar).
        client: tenant.
        squad: squad alvo.
        repo_urls: lista de URLs. V2 atual indexa o PRIMEIRO repo; multi-repo
            no setup inicial fica como melhoria futura.
        github_token: opcional, decriptado da credencial do cliente quando
            o repo eh privado.

    Returns:
        UUID da task criada (ou existente, se idempotente).

    Raises:
        ValueError: se nao houver repo_url valida.
        RuntimeError: se algum pre-requisito faltar (skill OA nao
            provisionado ainda).
    """
    if not repo_urls:
        raise ValueError("repo_urls vazio — analise precisa de pelo menos 1 repo")

    valid_urls = [
        normalize_github_https_url(u) for u in repo_urls
    ]
    valid_urls = [u for u in valid_urls if u is not None]
    if not valid_urls:
        raise ValueError(
            "Nenhum repo_url valido apos normalizacao. Aceito apenas URLs "
            "do GitHub (https://github.com/owner/repo).",
        )

    # Idempotency
    existing = await _find_active_onboarding_task(session, squad.id)
    if existing is not None:
        logger.info(
            "oa_v2: ja existe analise ativa pra squad=%s task=%s",
            squad.id, existing.id,
        )
        return existing.id

    # Cria Task
    task = Task(
        client_id=client.id,
        squad_id=squad.id,
        jira_workspace_url=client.jira_workspace_url or "",
        jira_issue_key=f"ONBOARDING-{squad.id}",
        title=f"{_ONBOARDING_TASK_TITLE_PREFIX} {squad.slug}",
        current_stage=TaskStage.DEMAND_RECEIVED,
        status=TaskStatus.IN_PROGRESS,
        outcome_status=OutcomeStatus.PENDING,
        current_step=None,
        step_label=None,
        scan_progress={"started_at": datetime.now(tz=timezone.utc).isoformat()},
    )
    session.add(task)
    await session.flush()
    task_id = task.id
    await session.commit()

    # Dispara background
    asyncio.create_task(_run_analysis_in_background(
        task_id=task_id,
        client_id=client.id,
        client_name=client.name,
        squad_id=squad.id,
        squad_slug=squad.slug,
        squad_name=squad.name,
        repo_url=valid_urls[0],
        github_token=github_token,
    ))
    return task_id


async def _find_active_onboarding_task(
    session: AsyncSession, squad_id: UUID,
) -> Task | None:
    """Retorna task de onboarding em status ativo (PENDING/IN_PROGRESS)."""
    stmt = (
        select(Task)
        .where(
            Task.squad_id == squad_id,
            Task.title.like(f"{_ONBOARDING_TASK_TITLE_PREFIX}%"),
            Task.status.in_([TaskStatus.PENDING, TaskStatus.IN_PROGRESS]),
        )
        .order_by(Task.created_at.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def _find_latest_onboarding_task(
    session: AsyncSession, squad_id: UUID,
) -> Task | None:
    """Retorna a task de onboarding mais recente (qualquer status)."""
    stmt = (
        select(Task)
        .where(
            Task.squad_id == squad_id,
            Task.title.like(f"{_ONBOARDING_TASK_TITLE_PREFIX}%"),
        )
        .order_by(Task.created_at.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_analysis_status(
    session: AsyncSession, squad: Squad,
) -> dict[str, Any]:
    """Le estado granular pra polling do frontend.

    Retorna dict pronto pro Pydantic OnboardingStatusResponse parsear.
    """
    task = await _find_latest_onboarding_task(session, squad.id)
    if task is None:
        return {"status": "not_started"}

    status_map = {
        TaskStatus.IN_PROGRESS: "in_progress",
        TaskStatus.PENDING: "in_progress",
        TaskStatus.DONE: "completed",
        TaskStatus.FAILED: "failed",
        TaskStatus.CANCELLED: "cancelled",
        TaskStatus.BLOCKED: "in_progress",
    }
    high_level = status_map.get(task.status, "in_progress")
    scan_progress = dict(task.scan_progress or {})

    started_at = None
    started_iso = scan_progress.get("started_at")
    if started_iso:
        try:
            started_at = datetime.fromisoformat(started_iso)
        except ValueError:
            pass

    manifest_ready_at = None
    if high_level == "completed":
        store = (await session.execute(
            select(SquadMemoryStore).where(
                SquadMemoryStore.squad_id == squad.id,
                SquadMemoryStore.kind == MemoryStoreKind.ONBOARDING,
            )
        )).scalar_one_or_none()
        if store is not None:
            manifest_ready_at = store.updated_at

    return {
        "task_id": task.id,
        "status": high_level,
        "current_step": task.current_step,
        "step_label": task.step_label,
        "scan_progress": scan_progress,
        "started_at": started_at,
        "manifest_ready_at": manifest_ready_at,
        "closed_at": task.closed_at,
        "error_message": (
            task.step_label if task.status == TaskStatus.FAILED else None
        ),
    }


async def read_manifest(
    session: AsyncSession, squad: Squad,
) -> dict[str, Any] | None:
    """Le manifest do memory_store ONBOARDING da squad. None se nao existe."""
    store = (await session.execute(
        select(SquadMemoryStore).where(
            SquadMemoryStore.squad_id == squad.id,
            SquadMemoryStore.kind == MemoryStoreKind.ONBOARDING,
        )
    )).scalar_one_or_none()
    if store is None:
        return None
    return store.content


async def cancel_analysis(
    session: AsyncSession, squad: Squad,
) -> tuple[UUID, str, str]:
    """Cancela a analise ativa da squad.

    Returns (task_id, previous_status, new_status).
    """
    task = await _find_latest_onboarding_task(session, squad.id)
    if task is None:
        raise ValueError("nao ha analise de onboarding pra cancelar")

    previous = task.status.value
    if task.status in (
        TaskStatus.IN_PROGRESS, TaskStatus.PENDING, TaskStatus.BLOCKED,
    ):
        task.status = TaskStatus.CANCELLED
        task.current_step = "cancelled"
        task.step_label = "Análise cancelada pelo cliente."
        task.closed_at = datetime.now(tz=timezone.utc)
        merged = dict(task.scan_progress or {})
        merged["cancelled_at"] = datetime.now(tz=timezone.utc).isoformat()
        task.scan_progress = merged
        await session.commit()
        return task.id, previous, "cancelled"

    return task.id, previous, "already_finished"


# ---------------------------------------------------------------------------
# Background runner
# ---------------------------------------------------------------------------


async def _run_analysis_in_background(
    *,
    task_id: UUID,
    client_id: UUID,
    client_name: str,
    squad_id: UUID,
    squad_slug: str,
    squad_name: str,
    repo_url: str,
    github_token: str | None,
) -> None:
    """Orquestrador das 6 etapas. NUNCA propaga exception — sempre tenta
    marcar task com motivo antes de sair. Cleanup do clone garantido."""
    settings = get_settings()
    clone_target = get_clone_path(client_id, task_id)

    try:
        # Etapa 1: clone local
        await _update_step(task_id, "cloning")
        if await _check_cancelled(task_id):
            return
        try:
            clone_result = await clone_repo(
                repo_url=repo_url,
                target_path=clone_target,
                github_token=github_token,
                depth=1,
                timeout_seconds=300,
            )
        except CloneError as exc:
            await _mark_failed(task_id, f"clone_failed: {exc}")
            return

        # Etapa 2: scan filesystem
        await _update_step(task_id, "scanning")
        if await _check_cancelled(task_id):
            return
        scan = scan_filesystem(clone_result.path)
        await _patch_scan_progress(task_id, {
            "total_files": scan.total_eligible,
            "files_excluded": scan.total_excluded,
            "clone_size_bytes": clone_result.size_bytes,
        })

        # Etapa 3 + 6 (loop OA + grader)
        await _update_step(task_id, "oa_scanning")
        if await _check_cancelled(task_id):
            return
        oa_output = await _oa_scan_with_grader_loop(
            task_id=task_id,
            squad_slug=squad_slug,
            squad_name=squad_name,
            client_name=client_name,
            repo_url=repo_url,
            github_token=github_token,
            max_iterations=settings.OA_GRADER_MAX_ITERATIONS,
        )
        if oa_output is None:
            return  # ja marcou falha ou cancellation

        # Etapa 4: RAG ingest
        await _update_step(task_id, "indexing", {
            "chunks_estimated": _estimate_chunks(scan),
        })
        if await _check_cancelled(task_id):
            return
        repo_canonical = _extract_repo_slug(repo_url)
        async with session_scope() as session:
            index_result = await index_scanned_files(
                client_id=client_id,
                squad_id=squad_id,
                task_id=task_id,
                repo_canonical=repo_canonical,
                files=scan.files,
                stacks=oa_output.stacks,
                session=session,
                progress_cb=lambda done, total: _update_chunks_progress(
                    task_id, done, total,
                ),
            )
            await session.commit()
        await _patch_scan_progress(task_id, {
            "chunks_indexed": index_result.chunks_indexed,
            "files_indexed": index_result.files_indexed,
            "embedding_cost_usd": str(index_result.cost_usd),
        })

        # Etapa 5: persistir Stacks + manifest
        await _update_step(task_id, "finalizing")
        if await _check_cancelled(task_id):
            return
        async with session_scope() as session:
            await _persist_stacks(session, client_id, squad_id, oa_output.stacks)
            await _save_manifest(
                session, client_id, squad_id, oa_output,
                clone_metadata={
                    "repo_url": repo_url,
                    "commit_hash": clone_result.commit_hash,
                    "default_branch": clone_result.default_branch,
                    "indexed_chunks": index_result.chunks_indexed,
                },
            )
            await session.commit()

        # Etapa final
        await _mark_completed(task_id, oa_output)
        logger.info(
            "oa_v2: analise concluida task=%s stacks=%d chunks=%d",
            task_id, len(oa_output.stacks), index_result.chunks_indexed,
        )

    except Exception as exc:
        logger.exception("oa_v2: erro inesperado task=%s", task_id)
        await _mark_failed(task_id, f"unexpected_error: {type(exc).__name__}: {exc}")
    finally:
        cleanup_clone(clone_target)


# ---------------------------------------------------------------------------
# Etapa 3 + 6: OA + grader loop
# ---------------------------------------------------------------------------


async def _oa_scan_with_grader_loop(
    *,
    task_id: UUID,
    squad_slug: str,
    squad_name: str,
    client_name: str,
    repo_url: str,
    github_token: str | None,
    max_iterations: int,
) -> OnboardingAnalysisOutput | None:
    """Roda OA scan, valida JSON, passa pro grader. Se grader falhar e tiver
    iteracao restante, refaz com feedback. Retorna None apos esgotar
    tentativas (marca task FAILED)."""
    from dev_autonomo.agent_runtime.managed_runner import (
        ManagedTaskSpec, run_managed_task,
    )

    feedback_extra = ""
    last_validation_error = ""

    for iteration in range(1, max_iterations + 1):
        if await _check_cancelled(task_id):
            return None
        await _patch_scan_progress(task_id, {
            "oa_iterations": iteration,
            "oa_iteration_started_at": datetime.now(tz=timezone.utc).isoformat(),
        })

        # Monta prompt do OA pra esta iteracao
        oa_prompt = _build_oa_prompt(
            squad_name=squad_name, squad_slug=squad_slug,
            client_name=client_name, repo_url=repo_url,
            feedback_corrective=feedback_extra,
        )

        resources: list[dict[str, Any]] = [{
            "type": "github_repository",
            "url": repo_url,
            "authorization_token": github_token,
            "checkout": {"type": "branch", "name": "main"},
            "mount_path": "/mnt/repo",
        }] if github_token else []
        spec = ManagedTaskSpec(
            agent_name=f"oa-{squad_slug}",
            system_prompt=_OA_SYSTEM_PROMPT,
            initial_user_message=oa_prompt,
            model="claude-opus-4-7",  # Opus pra OA — qualidade > custo
            resources=resources,
        )

        try:
            result = await run_managed_task(spec, f"ONBOARDING-{task_id}")
        except Exception as exc:
            logger.exception("oa_v2: managed_runner falhou iteration=%d", iteration)
            await _mark_failed(task_id, f"oa_run_failed: {exc}")
            return None

        if not result.output_text:
            await _mark_failed(task_id, "oa_returned_empty_output")
            return None

        # Tenta validar JSON
        try:
            oa_output = _parse_oa_json_output(result.output_text)
        except (json.JSONDecodeError, ValidationError) as exc:
            last_validation_error = str(exc)[:500]
            logger.warning(
                "oa_v2: iter=%d JSON invalido: %s",
                iteration, last_validation_error[:200],
            )
            feedback_extra = (
                "Sua resposta anterior nao bateu no schema JSON exigido. "
                f"Erro: {last_validation_error}\n\n"
                "Refaca produzindo JSON valido conforme o schema do "
                "OnboardingAnalysisOutput. Sem prosa fora do JSON."
            )
            continue

        # Etapa 6: grader
        await _update_step(task_id, "grading")
        if await _check_cancelled(task_id):
            return None
        try:
            verdict: GraderVerdict = await grade_output(
                oa_output, rubric=DEFAULT_OA_RUBRIC,
            )
        except Exception as exc:
            logger.exception("oa_v2: grader falhou iter=%d", iteration)
            await _mark_failed(task_id, f"grader_failed: {exc}")
            return None

        await _patch_scan_progress(task_id, {
            f"grader_iter_{iteration}": {
                "passed": verdict.overall_passed,
                "checks": [
                    {"id": c.check_id, "passed": c.passed, "reason": c.reason}
                    for c in verdict.checks
                ],
                "cost_usd": str(verdict.cost_usd),
            },
        })

        if verdict.overall_passed:
            logger.info(
                "oa_v2: grader aprovou na iter=%d cost=$%s",
                iteration, verdict.cost_usd,
            )
            return oa_output

        # Grader rejeitou — prepara feedback pra proxima iter
        feedback_extra = (
            "Sua analise anterior nao passou no rubric. Feedback do grader:\n\n"
            f"{verdict.feedback_for_retry}\n\n"
            "Refaca o scan corrigindo os pontos acima. Mantenha o formato JSON."
        )
        # Volta ao topo do loop pra tentar de novo
        await _update_step(task_id, "oa_scanning")

    # Esgotou max_iterations
    await _mark_failed(
        task_id,
        f"oa_failed_grader_after_{max_iterations}_iterations: {feedback_extra[:300]}",
    )
    return None


def _parse_oa_json_output(output_text: str) -> OnboardingAnalysisOutput:
    """Extrai JSON do output do OA (com ou sem markdown fence) e valida."""
    text = output_text.strip()
    # Strip markdown fence
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[-1].strip() == "```":
            text = "\n".join(lines[1:-1])
        else:
            text = "\n".join(lines[1:])

    # As vezes OA solta um pouco de texto antes/depois do JSON puro.
    # Tentamos achar o primeiro { e ultimo } como heuristica de fallback.
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace > 0 and last_brace > first_brace:
        text = text[first_brace:last_brace + 1]

    return OnboardingAnalysisOutput.model_validate_json(text)


# ---------------------------------------------------------------------------
# Persistencia de Stacks + manifest
# ---------------------------------------------------------------------------


async def _persist_stacks(
    session: AsyncSession,
    client_id: UUID,
    squad_id: UUID,
    stacks_detected: list,
) -> None:
    """Cria Stack DETECTED no DB pra cada stack do OA output.

    Idempotente — se stack com mesmo (squad_id, slug) ja existe, atualiza
    paths/framework/conventions em vez de duplicar.
    """
    for detected in stacks_detected:
        # Lookup parent_stack_profile global por slug (se houver match)
        parent_profile = (await session.execute(
            select(StackProfile).where(StackProfile.slug == detected.slug)
        )).scalar_one_or_none()
        parent_id = parent_profile.id if parent_profile is not None else None

        existing = (await session.execute(
            select(Stack).where(
                Stack.squad_id == squad_id, Stack.slug == detected.slug,
            )
        )).scalar_one_or_none()

        if existing is None:
            stack = Stack(
                client_id=client_id,
                squad_id=squad_id,
                parent_stack_profile_id=parent_id,
                slug=detected.slug,
                name=detected.name,
                paths=detected.paths,
                framework=detected.framework,
                framework_version=detected.framework_version,
                conventions={
                    "observed_patterns": detected.conventions.observed_patterns,
                    "recommended_for_agents": (
                        detected.conventions.recommended_for_agents
                    ),
                },
                status=StackStatus.DETECTED,
                detected_at=datetime.now(tz=timezone.utc),
            )
            session.add(stack)
        else:
            existing.name = detected.name
            existing.paths = detected.paths
            existing.framework = detected.framework
            existing.framework_version = detected.framework_version
            existing.conventions = {
                "observed_patterns": detected.conventions.observed_patterns,
                "recommended_for_agents": (
                    detected.conventions.recommended_for_agents
                ),
            }
            existing.status = StackStatus.DETECTED
            existing.detected_at = datetime.now(tz=timezone.utc)
            if parent_id is not None:
                existing.parent_stack_profile_id = parent_id

    await session.flush()


async def _save_manifest(
    session: AsyncSession,
    client_id: UUID,
    squad_id: UUID,
    oa_output: OnboardingAnalysisOutput,
    clone_metadata: dict[str, Any],
) -> None:
    """Salva manifest derivado no memory_store da squad.

    Manifest reflete tudo que o OA descobriu — vira fonte de verdade pra
    proxima etapa (tela 3 frontend renderiza dele).
    """
    store = (await session.execute(
        select(SquadMemoryStore).where(
            SquadMemoryStore.squad_id == squad_id,
            SquadMemoryStore.kind == MemoryStoreKind.ONBOARDING,
        )
    )).scalar_one_or_none()

    manifest_content = {
        "summary": oa_output.summary,
        "stacks": [s.model_dump() for s in oa_output.stacks],
        "jira_projects": oa_output.jira_projects,
        "anti_patterns_detected": [
            ap.model_dump() for ap in oa_output.anti_patterns_detected
        ],
        "recommended_agents": [
            a.model_dump() for a in oa_output.recommended_agents
        ],
        "tool_calls_summary": oa_output.tool_calls_summary.model_dump(),
        "clone_metadata": clone_metadata,
        "saved_at": datetime.now(tz=timezone.utc).isoformat(),
    }

    if store is None:
        new_store = SquadMemoryStore(
            client_id=client_id,
            squad_id=squad_id,
            kind=MemoryStoreKind.ONBOARDING,
            content=manifest_content,
        )
        session.add(new_store)
    else:
        store.content = manifest_content

    await session.flush()


# ---------------------------------------------------------------------------
# State machine — updates ao Task
# ---------------------------------------------------------------------------


async def _update_step(
    task_id: UUID, step: str, scan_progress_patch: dict | None = None,
) -> None:
    """Atualiza current_step + step_label num commit isolado."""
    async with session_scope() as session:
        task = await session.get(Task, task_id)
        if task is None:
            logger.warning("oa_v2: task %s nao encontrada pra update_step", task_id)
            return
        task.current_step = step
        task.step_label = STEP_LABELS.get(step, step)
        if scan_progress_patch:
            merged = dict(task.scan_progress or {})
            merged.update(scan_progress_patch)
            task.scan_progress = merged
        await session.commit()


async def _patch_scan_progress(task_id: UUID, patch: dict) -> None:
    async with session_scope() as session:
        task = await session.get(Task, task_id)
        if task is None:
            return
        merged = dict(task.scan_progress or {})
        merged.update(patch)
        task.scan_progress = merged
        await session.commit()


async def _update_chunks_progress(task_id: UUID, done: int, total: int) -> None:
    await _patch_scan_progress(task_id, {
        "chunks_indexed": done,
        "chunks_total": total,
    })


async def _mark_completed(task_id: UUID, oa_output: OnboardingAnalysisOutput) -> None:
    async with session_scope() as session:
        task = await session.get(Task, task_id)
        if task is None:
            return
        task.status = TaskStatus.DONE
        task.current_step = "completed"
        task.step_label = "Análise concluída."
        task.outcome_status = OutcomeStatus.SATISFIED
        task.closed_at = datetime.now(tz=timezone.utc)
        merged = dict(task.scan_progress or {})
        merged["completed_at"] = datetime.now(tz=timezone.utc).isoformat()
        merged["stacks_detected"] = len(oa_output.stacks)
        merged["agents_recommended"] = len(oa_output.recommended_agents)
        task.scan_progress = merged
        await session.commit()


async def _mark_failed(task_id: UUID, reason: str) -> None:
    """Marca task como FAILED com reason em step_label e scan_progress."""
    logger.error("oa_v2: task=%s falhou: %s", task_id, reason)
    async with session_scope() as session:
        task = await session.get(Task, task_id)
        if task is None:
            return
        task.status = TaskStatus.FAILED
        task.current_step = "failed"
        task.step_label = reason[:1000]
        task.outcome_status = OutcomeStatus.FAILED
        task.closed_at = datetime.now(tz=timezone.utc)
        merged = dict(task.scan_progress or {})
        merged["failed_at"] = datetime.now(tz=timezone.utc).isoformat()
        merged["failure_reason"] = reason
        task.scan_progress = merged
        await session.commit()


async def _check_cancelled(task_id: UUID) -> bool:
    """Verifica se o cliente cancelou via endpoint. Retorna True se sim
    (caller deve sair early com cleanup)."""
    async with session_scope() as session:
        task = await session.get(Task, task_id)
        if task is None:
            return True
        if task.status == TaskStatus.CANCELLED:
            logger.info("oa_v2: task %s cancelada pelo cliente", task_id)
            return True
    return False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _estimate_chunks(scan: ScanResult) -> int:
    """Estimativa rough: ~1 chunk a cada 3200 chars de bytes elegiveis."""
    return max(1, scan.total_bytes_eligible // 3200)


def _extract_repo_slug(repo_url: str) -> str:
    """Extrai 'owner/repo' canonical de uma URL GitHub.

    Ex: https://github.com/rlenzi/obris-dev-squad-agent.git
        → rlenzi/obris-dev-squad-agent
    """
    canonical = normalize_github_https_url(repo_url) or repo_url
    return canonical.removeprefix("https://github.com/").rstrip("/")


# ---------------------------------------------------------------------------
# Prompts do OA
# ---------------------------------------------------------------------------


_OA_SYSTEM_PROMPT = """Você é o Onboarding Analyst — um agente especialista em fazer code review e analise profunda de novos projetos pra propor uma squad de agentes autônomos adequada.

# Sua missão

Receber um repositório (montado em /mnt/repo via github_repository resource) e produzir UM ÚNICO JSON estruturado descrevendo:
- Stacks detectadas (com paths, framework, version, e convenções)
- Padrões observados vs recomendados (descritivo vs prescritivo — distinção CRÍTICA)
- Anti-patterns identificados (com path:line concreto)
- Projetos Jira referenciados em commits/PR templates
- Agentes recomendados pra essa squad

# Princípios

1. **Profundidade > velocidade.** Você NÃO está aqui pra ser rápido — está aqui pra ser preciso. Varra muitos arquivos. Não amostre 5 quando deveria amostrar 30.
2. **Honestidade descritiva.** Em observed_patterns, descreva HONESTAMENTE o que viu — inclusive divergências, anti-padrões, inconsistências.
3. **Editorial prescritivo.** Em recommended_for_agents, recomende BOA PRÁTICA pra stack — NÃO copie literalmente padrões problemáticos que viu. Filtra.
4. **Evidência sempre concreta.** Anti-patterns sem path:line são rejeitados pelo grader. Liste 1+ ocorrências reais.
5. **Schema rígido.** Output é JSON validado por Pydantic. Campo extra rejeita. Campo faltando rejeita.

# Tools que você tem

- bash: ls, find, grep, git log, head, tail, wc, etc. Use livremente.
- file read: leia arquivos diretamente.
- Você está em /mnt/repo dentro de um sandbox isolado.

# Como você trabalha (passo a passo)

1. **Mapeie a estrutura**: `ls -la /mnt/repo` + `find /mnt/repo -maxdepth 3 -type d` pra entender forma do projeto.
2. **Leia identidade**: README*, CONTRIBUTING*, docs/*.md, qualquer .md na raiz que explica o projeto.
3. **Leia manifestos**: pyproject.toml, package.json, Cargo.toml, pom.xml, go.mod, Gemfile, Dockerfile, docker-compose.yml, .github/workflows/, .dev-autonomo.yml. CADA um encontrado.
4. **Amostra profunda de código**: pra CADA área identificada (cada path do repo que parece ser uma "stack"), leia 15-25 arquivos representativos. Não 5. Não os primeiros. Pegue espalhado pra captar variação real.
5. **Amostra de testes**: se houver tests/, leia 5-10 arquivos pra extrair testing_framework, test_layout, padrões de fixture.
6. **Histórico Git**: `git -C /mnt/repo log --oneline -100` pra detectar Jira refs ([A-Z]+-[0-9]+), padrão de commit message, áreas mais ativas.
7. **CI/CD**: leia .github/workflows/* (ou GitLab CI, etc.) pra entender pipeline + comandos de build/test usados.

# Estrutura de saída obrigatória

```json
{
  "summary": "Prosa em primeira pessoa, ~5-8 frases descrevendo o que você encontrou. Será mostrado literal pro cliente na tela do wizard.",
  "stacks": [
    {
      "slug": "kebab-case-lowercase",
      "name": "Display name humano (ex: Backend Python/FastAPI)",
      "paths": ["src/api/", "src/admin/"],
      "framework": "fastapi",
      "framework_version": "0.115.0",
      "conventions": {
        "observed_patterns": {
          "testing": "frase substantiva descrevendo padrão observado, com qualificadores",
          "naming": "...",
          "imports": "...",
          "error_handling": "...",
          "commits": "..."
        },
        "recommended_for_agents": {
          "testing": "diretriz prescritiva pra agente seguir — filtrada, não copia anti-padrão",
          "naming": "...",
          "imports": "...",
          "error_handling": "...",
          "commits": "..."
        }
      }
    }
  ],
  "jira_projects": ["LEO", "ADMIN"],
  "anti_patterns_detected": [
    {
      "issue": "descrição específica do problema",
      "severity": "low|medium|high",
      "occurrences": ["src/foo.py:42", "src/bar.py:117"],
      "recommendation": "o que agentes devem fazer em vez disso"
    }
  ],
  "recommended_agents": [
    {
      "tier": "ba|architect|dev|reviewer",
      "stack_slug": "<obrigatório pra dev, null pros outros>",
      "rationale": "por que esse agente faz sentido nessa squad"
    }
  ],
  "tool_calls_summary": {
    "file_reads": 42,
    "bash_commands": 15,
    "grep_searches": 5,
    "glob_searches": 3,
    "git_log_called": true,
    "git_log_max_count": 100
  }
}
```

# Goals (rubric que vai te avaliar)

Um grader independente vai checar:
- scan_breadth: file_reads >= 15 * número de stacks
- conventions_depth: 5+ categorias em observed_patterns E em recommended_for_agents, cada uma com 2+ frases substantivas
- anti_patterns_evidence: occurrences com path:line concreto (não vagueza)
- tests_examined: se há tests/, você leu 5+ deles
- git_history_checked: git_log_max_count >= 50

Se o grader rejeitar, você refaz com feedback. Máximo 3 tentativas.

# IMPORTANTE

- Responda APENAS com o JSON. Sem prosa antes ou depois. Sem markdown fence.
- Architect e ao menos 1 Dev em recommended_agents (essenciais pra pipeline).
- Cada Dev tem stack_slug.
- jira_projects vazio é OK se não houver referência Jira no repo.
"""


def _build_oa_prompt(
    *,
    squad_name: str,
    squad_slug: str,
    client_name: str,
    repo_url: str,
    feedback_corrective: str = "",
) -> str:
    base = (
        f"Cliente: **{client_name}**\n"
        f"Squad: **{squad_name}** (slug: {squad_slug})\n"
        f"Repositório: {repo_url}\n\n"
        "O repositório está montado em /mnt/repo. Faça scan profundo conforme "
        "as instruções do system prompt e produza o JSON estruturado.\n\n"
        "Lembre: profundidade > velocidade. Leia muitos arquivos. Não amostre raso."
    )
    if feedback_corrective:
        base += f"\n\n## CORREÇÕES NECESSÁRIAS\n\n{feedback_corrective}"
    return base
