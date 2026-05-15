"""Smoke E2E parcial: state machine + cancel + status response.

Cria tudo no DB (client/user/squad), insere task fake do onboarding,
verifica que get_analysis_status retorna o esperado, testa cancel.
Nao chama Anthropic/Voyage real.
"""
import asyncio
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from dev_autonomo.common.enums import (
    OutcomeStatus, SquadStatus, TaskStage, TaskStatus,
)
from dev_autonomo.control_plane.schemas.onboarding import (
    OnboardingStatusResponse,
)
from dev_autonomo.db.models import Client, Squad, Task
from dev_autonomo.db.session import session_scope
from dev_autonomo.onboarding.analyzer import (
    cancel_analysis,
    get_analysis_status,
    _find_active_onboarding_task,
    _find_latest_onboarding_task,
)


async def _make_squad():
    """Cria client + squad fake pra teste. Returns (client_id, squad_id, cleanup_ids)."""
    async with session_scope() as s:
        client = Client(slug=f"smoke-{uuid4().hex[:8]}", name="smoke client")
        s.add(client)
        await s.flush()
        squad = Squad(
            client_id=client.id,
            slug=f"smoke-{uuid4().hex[:8]}",
            name="smoke squad",
            status=SquadStatus.PROVISIONING,
        )
        s.add(squad)
        await s.flush()
        await s.commit()
        return client.id, squad.id


async def _cleanup(client_id, squad_id):
    async with session_scope() as s:
        await s.execute(
            text("UPDATE squads SET current_manifest_id=NULL WHERE id=:s"),
            {"s": squad_id},
        )
        for tbl in ("tasks", "stacks", "squad_memory_stores", "manifests",
                    "agent_instances", "squads"):
            where = "id=:s" if tbl == "squads" else "squad_id=:s"
            await s.execute(
                text(f"DELETE FROM {tbl} WHERE {where}"),
                {"s": squad_id},
            )
        await s.execute(text("DELETE FROM clients WHERE id=:c"), {"c": client_id})
        await s.commit()


async def test_status_not_started():
    """Sem nenhuma task, status=not_started."""
    cid, sid = await _make_squad()
    try:
        async with session_scope() as s:
            squad = await s.get(Squad, sid)
            state = await get_analysis_status(s, squad)
        assert state == {"status": "not_started"}
        # Schema parsing OK?
        resp = OnboardingStatusResponse.model_validate(state)
        assert resp.status == "not_started"
        assert resp.task_id is None
        print("[not_started] OK")
    finally:
        await _cleanup(cid, sid)


async def test_status_in_progress():
    """Task IN_PROGRESS com scan_progress + step retorna granular."""
    cid, sid = await _make_squad()
    try:
        async with session_scope() as s:
            task = Task(
                client_id=cid, squad_id=sid,
                jira_workspace_url="",
                jira_issue_key=f"ONBOARDING-{sid}",
                title=f"[onboarding-analysis] smoke",
                current_stage=TaskStage.DEMAND_RECEIVED,
                status=TaskStatus.IN_PROGRESS,
                outcome_status=OutcomeStatus.PENDING,
                current_step="indexing",
                step_label="Estou pegando trechos do seu código…",
                scan_progress={
                    "started_at": "2026-05-15T10:00:00+00:00",
                    "total_files": 247,
                    "chunks_total": 6890,
                    "chunks_indexed": 2134,
                },
            )
            s.add(task)
            await s.commit()
            task_id = task.id

        async with session_scope() as s:
            squad = await s.get(Squad, sid)
            state = await get_analysis_status(s, squad)

        resp = OnboardingStatusResponse.model_validate(state)
        assert resp.status == "in_progress"
        assert resp.task_id == task_id
        assert resp.current_step == "indexing"
        assert "Estou pegando" in resp.step_label
        assert resp.scan_progress["chunks_indexed"] == 2134
        assert resp.scan_progress["chunks_total"] == 6890
        assert resp.started_at is not None
        assert resp.error_message is None
        print(f"[in_progress] OK step={resp.current_step} chunks={resp.scan_progress['chunks_indexed']}/{resp.scan_progress['chunks_total']}")
    finally:
        await _cleanup(cid, sid)


async def test_status_failed():
    """Task FAILED — error_message preenchido."""
    cid, sid = await _make_squad()
    try:
        async with session_scope() as s:
            task = Task(
                client_id=cid, squad_id=sid,
                jira_workspace_url="",
                jira_issue_key=f"ONBOARDING-{sid}",
                title=f"[onboarding-analysis] smoke",
                current_stage=TaskStage.DEMAND_RECEIVED,
                status=TaskStatus.FAILED,
                outcome_status=OutcomeStatus.FAILED,
                current_step="failed",
                step_label="clone_failed: repo_not_found",
                scan_progress={"failure_reason": "repo_not_found"},
            )
            s.add(task)
            await s.commit()

        async with session_scope() as s:
            squad = await s.get(Squad, sid)
            state = await get_analysis_status(s, squad)

        resp = OnboardingStatusResponse.model_validate(state)
        assert resp.status == "failed"
        assert "clone_failed" in resp.error_message
        print(f"[failed] OK error={resp.error_message[:40]}")
    finally:
        await _cleanup(cid, sid)


async def test_cancel_active():
    """Cancel task IN_PROGRESS muda pra CANCELLED."""
    cid, sid = await _make_squad()
    try:
        async with session_scope() as s:
            task = Task(
                client_id=cid, squad_id=sid,
                jira_workspace_url="",
                jira_issue_key=f"ONBOARDING-{sid}",
                title=f"[onboarding-analysis] smoke",
                current_stage=TaskStage.DEMAND_RECEIVED,
                status=TaskStatus.IN_PROGRESS,
                outcome_status=OutcomeStatus.PENDING,
                current_step="oa_scanning",
            )
            s.add(task)
            await s.commit()
            task_id = task.id

        async with session_scope() as s:
            squad = await s.get(Squad, sid)
            tid, prev, new = await cancel_analysis(s, squad)
        assert tid == task_id
        assert prev == "in_progress"
        assert new == "cancelled"

        # Verifica que task foi atualizada
        async with session_scope() as s:
            t = await s.get(Task, task_id)
            assert t.status == TaskStatus.CANCELLED
            assert t.current_step == "cancelled"
            assert "cancelled_at" in t.scan_progress

        # status via get_analysis_status
        async with session_scope() as s:
            squad = await s.get(Squad, sid)
            state = await get_analysis_status(s, squad)
        resp = OnboardingStatusResponse.model_validate(state)
        assert resp.status == "cancelled"
        print(f"[cancel_active] OK previous={prev} new={new}")
    finally:
        await _cleanup(cid, sid)


async def test_cancel_already_finished():
    """Cancel em task DONE retorna already_finished."""
    cid, sid = await _make_squad()
    try:
        async with session_scope() as s:
            task = Task(
                client_id=cid, squad_id=sid,
                jira_workspace_url="",
                jira_issue_key=f"ONBOARDING-{sid}",
                title=f"[onboarding-analysis] smoke",
                current_stage=TaskStage.DEMAND_RECEIVED,
                status=TaskStatus.DONE,
                outcome_status=OutcomeStatus.SATISFIED,
                current_step="completed",
            )
            s.add(task)
            await s.commit()

        async with session_scope() as s:
            squad = await s.get(Squad, sid)
            _, prev, new = await cancel_analysis(s, squad)
        assert prev == "done"
        assert new == "already_finished"
        print(f"[cancel_finished] OK previous={prev} new={new}")
    finally:
        await _cleanup(cid, sid)


async def test_find_active_idempotency():
    """_find_active_onboarding_task retorna so IN_PROGRESS/PENDING."""
    cid, sid = await _make_squad()
    try:
        # Cria 1 FAILED + 1 IN_PROGRESS
        async with session_scope() as s:
            for st in (TaskStatus.FAILED, TaskStatus.IN_PROGRESS):
                s.add(Task(
                    client_id=cid, squad_id=sid,
                    jira_workspace_url="",
                    jira_issue_key=f"ONBOARDING-{sid}-{st.value}",
                    title=f"[onboarding-analysis] smoke {st.value}",
                    current_stage=TaskStage.DEMAND_RECEIVED,
                    status=st,
                    outcome_status=OutcomeStatus.PENDING,
                ))
            await s.commit()

        async with session_scope() as s:
            active = await _find_active_onboarding_task(s, sid)
            latest = await _find_latest_onboarding_task(s, sid)
        assert active is not None
        assert active.status == TaskStatus.IN_PROGRESS
        assert latest is not None  # alguma task encontrada
        print("[find_active_idempotency] OK")
    finally:
        await _cleanup(cid, sid)


async def main():
    await test_status_not_started()
    await test_status_in_progress()
    await test_status_failed()
    await test_cancel_active()
    await test_cancel_already_finished()
    await test_find_active_idempotency()
    print("\n=== SMOKE ANALYZER STATE OK ===")


asyncio.run(main())
