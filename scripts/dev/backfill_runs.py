"""Backfill: agrupa external_api_calls antigos (task_id NULL) em runs.

Cada AgentInstance fica com suas chamadas agrupadas por gap temporal — calls
do mesmo agente com menos de GAP_MINUTES de diferença entre si pertencem ao
mesmo run. Para cada grupo, cria uma Task local fake (jira_issue_key =
"HIST-{timestamp}") e atualiza external_api_calls.task_id correspondente.

Idempotente: re-execução não cria Tasks duplicadas pois usa a unique constraint
de (jira_workspace_url, jira_issue_key).

Uso:
    uv run python -m scripts.dev.backfill_runs
"""

from __future__ import annotations

import asyncio
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from dev_autonomo.db.models import AgentInstance, Client, Squad, Task
from dev_autonomo.db.models.cost import ExternalApiCall
from dev_autonomo.db.session import session_scope


GAP_MINUTES = 5  # se 2 calls do mesmo agente têm > 5min de gap, são runs diferentes


async def main() -> None:
    print("=" * 70)
    print("Backfill: agrupando external_api_calls em runs históricos")
    print("=" * 70)

    async with session_scope() as session:
        # Lista todos os agentes com calls não-vinculadas
        result = await session.execute(
            select(
                ExternalApiCall.agent_instance_id,
                ExternalApiCall.client_id,
            )
            .where(
                ExternalApiCall.task_id.is_(None),
                ExternalApiCall.agent_instance_id.is_not(None),
            )
            .distinct()
        )
        pairs = list(result.all())
        print(f"Agentes com calls a backfillar: {len(pairs)}")

        gap = timedelta(minutes=GAP_MINUTES)
        total_tasks_created = 0
        total_calls_updated = 0

        for agent_id, client_id in pairs:
            agent = (
                await session.execute(
                    select(AgentInstance).where(AgentInstance.id == agent_id)
                )
            ).scalar_one()
            client = (
                await session.execute(select(Client).where(Client.id == client_id))
            ).scalar_one()
            squad = (
                await session.execute(
                    select(Squad).where(Squad.id == agent.squad_id)
                )
            ).scalar_one()

            calls = (
                await session.execute(
                    select(ExternalApiCall.id, ExternalApiCall.occurred_at)
                    .where(
                        ExternalApiCall.agent_instance_id == agent_id,
                        ExternalApiCall.task_id.is_(None),
                    )
                    .order_by(ExternalApiCall.occurred_at.asc())
                )
            ).all()

            if not calls:
                continue

            # Agrupa por gap temporal
            groups: list[list] = []
            current: list = [calls[0]]
            for call in calls[1:]:
                prev_time = current[-1].occurred_at
                cur_time = call.occurred_at
                if cur_time - prev_time > gap:
                    groups.append(current)
                    current = [call]
                else:
                    current.append(call)
            groups.append(current)

            print(
                f"\n{agent.name}: {len(calls)} calls -> {len(groups)} runs históricos"
            )

            for group in groups:
                first_ts = group[0].occurred_at
                key = f"HIST-{first_ts.strftime('%Y%m%dT%H%M%S')}"

                # Idempotência: busca antes de criar
                existing_task = (
                    await session.execute(
                        select(Task).where(
                            Task.client_id == client.id,
                            Task.jira_workspace_url == client.jira_workspace_url,
                            Task.jira_issue_key == key,
                        )
                    )
                ).scalar_one_or_none()

                if existing_task is None:
                    task = Task(
                        client_id=client.id,
                        squad_id=squad.id,
                        jira_workspace_url=client.jira_workspace_url,
                        jira_issue_key=key,
                        title=f"Run histórico {first_ts.strftime('%d/%m %H:%M')}",
                        assigned_agent_id=agent.id,
                    )
                    session.add(task)
                    try:
                        await session.flush()
                        total_tasks_created += 1
                    except IntegrityError:
                        # Race condition ou ja criada por iteracao anterior
                        await session.rollback()
                        existing_task = (
                            await session.execute(
                                select(Task).where(
                                    Task.client_id == client.id,
                                    Task.jira_workspace_url == client.jira_workspace_url,
                                    Task.jira_issue_key == key,
                                )
                            )
                        ).scalar_one()
                        task = existing_task
                else:
                    task = existing_task

                # Atualiza calls do grupo com task_id
                call_ids = [c.id for c in group]
                await session.execute(
                    update(ExternalApiCall)
                    .where(ExternalApiCall.id.in_(call_ids))
                    .values(task_id=task.id)
                )
                total_calls_updated += len(call_ids)
                print(
                    f"  {key}: {len(group)} calls "
                    f"({first_ts.strftime('%H:%M:%S')} -> "
                    f"{group[-1].occurred_at.strftime('%H:%M:%S')})"
                )

        await session.commit()

        print()
        print("=" * 70)
        print(f"RESUMO: {total_tasks_created} Tasks criadas, {total_calls_updated} calls atualizadas")
        print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
