"""Cleanup de recursos Anthropic criados durante smokes.

Mantém (KEEP):
- Agents persistidos em skill_templates.anthropic_agent_id
- Environments persistidos em clients.anthropic_environment_id
- Memory store ba-platform-insights (memstore_016YwvRspyqF3zbhz1wg3esw)

Deleta (DELETE) tudo que não está nessas listas.

Uso:
    python -m scripts.dev.cleanup_anthropic            # dry-run, lista o que deletaria
    python -m scripts.dev.cleanup_anthropic --apply    # executa
"""
from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

from anthropic import Anthropic
from dotenv import dotenv_values
from sqlalchemy import select

from dev_autonomo.db.models import Client, SkillTemplate
from dev_autonomo.db.session import session_scope


ENV = dotenv_values(Path("/home/rubens/dev-autonomo-workspace/secrets/.env"))
os.environ["ANTHROPIC_API_KEY"] = ENV["ANTHROPIC_API_KEY"]

KEEP_MEMORY_STORES = {"memstore_016YwvRspyqF3zbhz1wg3esw"}  # ba-platform-insights


async def load_keep_sets() -> tuple[set[str], set[str]]:
    """Retorna (agent_ids, environment_ids) persistidos no DB."""
    async with session_scope() as s:
        tpls = (await s.execute(
            select(SkillTemplate).where(SkillTemplate.anthropic_agent_id.is_not(None))
        )).scalars().all()
        clients = (await s.execute(
            select(Client).where(Client.anthropic_environment_id.is_not(None))
        )).scalars().all()
        agents = {t.anthropic_agent_id for t in tpls if t.anthropic_agent_id}
        envs = {c.anthropic_environment_id for c in clients if c.anthropic_environment_id}
    return agents, envs


def list_paged(method, **kwargs):
    """Itera page cursor da Anthropic."""
    page = method(limit=100, **kwargs)
    while True:
        for item in getattr(page, "data", []) or []:
            yield item
        # SDK SyncPageCursor — tenta avançar
        if not getattr(page, "has_more", False):
            break
        next_page = getattr(page, "get_next_page", None)
        if not next_page:
            break
        page = next_page()


def cleanup_resources(apply: bool) -> dict:
    """Lista (e opcionalmente deleta) recursos órfãos.

    Retorna dict com contadores.
    """
    client = Anthropic()
    keep_agents, keep_envs = asyncio.run(load_keep_sets())

    print(f"KEEP agents:        {len(keep_agents)}")
    for a in keep_agents:
        print(f"  - {a}")
    print(f"KEEP environments:  {len(keep_envs)}")
    for e in keep_envs:
        print(f"  - {e}")
    print(f"KEEP memory_stores: {len(KEEP_MEMORY_STORES)}")
    for m in KEEP_MEMORY_STORES:
        print(f"  - {m}")

    stats = {"agents": 0, "environments": 0, "sessions": 0, "memory_stores": 0, "files": 0}

    print("\n--- AGENTS ---")
    for agent in list_paged(client.beta.agents.list):
        agent_id = agent.id
        name = getattr(agent, "name", "?")
        if agent_id in keep_agents:
            print(f"  KEEP  {agent_id}  {name}")
            continue
        action = "DELETE" if apply else "would delete"
        print(f"  {action}  {agent_id}  {name}")
        if apply:
            try:
                client.beta.agents.archive(agent_id)
            except Exception as exc:
                print(f"    ! falhou: {exc}")
                continue
        stats["agents"] += 1

    print("\n--- ENVIRONMENTS ---")
    for env in list_paged(client.beta.environments.list):
        env_id = env.id
        name = getattr(env, "name", "?")
        if env_id in keep_envs:
            print(f"  KEEP  {env_id}  {name}")
            continue
        action = "DELETE" if apply else "would delete"
        print(f"  {action}  {env_id}  {name}")
        if apply:
            try:
                client.beta.environments.delete(env_id)
            except Exception as exc:
                print(f"    ! falhou: {exc}")
                continue
        stats["environments"] += 1

    print("\n--- SESSIONS ---")
    # Sessions associadas a agents que vão sumir, ou agents mantidos que tiveram smokes
    # Sessions são leves; deletar tudo que tiver mais de 24h ou simplesmente todas
    # (managed_runner sempre cria nova).
    for sess in list_paged(client.beta.sessions.list):
        sess_id = sess.id
        title = getattr(sess, "title", "?")
        status = getattr(sess, "status", "?")
        action = "DELETE" if apply else "would delete"
        print(f"  {action}  {sess_id}  status={status}  {title}")
        if apply:
            try:
                client.beta.sessions.delete(sess_id)
            except Exception as exc:
                print(f"    ! falhou: {exc}")
                continue
        stats["sessions"] += 1

    print("\n--- MEMORY STORES ---")
    for ms in list_paged(client.beta.memory_stores.list):
        ms_id = ms.id
        name = getattr(ms, "name", "?")
        if ms_id in KEEP_MEMORY_STORES:
            print(f"  KEEP  {ms_id}  {name}")
            continue
        action = "DELETE" if apply else "would delete"
        print(f"  {action}  {ms_id}  {name}")
        if apply:
            try:
                client.beta.memory_stores.delete(ms_id)
            except Exception as exc:
                print(f"    ! falhou: {exc}")
                continue
        stats["memory_stores"] += 1

    print("\n--- FILES ---")
    for f in list_paged(client.beta.files.list):
        f_id = f.id
        filename = getattr(f, "filename", "?") or getattr(f, "name", "?")
        action = "DELETE" if apply else "would delete"
        print(f"  {action}  {f_id}  {filename}")
        if apply:
            try:
                client.beta.files.delete(f_id)
            except Exception as exc:
                print(f"    ! falhou: {exc}")
                continue
        stats["files"] += 1

    print(f"\n=== Resumo ({'APPLIED' if apply else 'DRY-RUN'}) ===")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    return stats


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--apply", action="store_true", help="Executa deletes (sem isso, dry-run)")
    args = p.parse_args()
    cleanup_resources(apply=args.apply)
