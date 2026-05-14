"""Provisiona todos os Managed Agents da squad Plataforma.

Idempotente: skill_templates com anthropic_agent_id ja preenchido sao
pulados. Sub-agents (Dev BE/FE, BA, Reviewer, OA) sao criados antes do
Architect (coordinator) que depende deles.

Mapping skill_template -> prompt_path (precisa managed.md):
- ba-generic-v1              -> prompts/ba/managed.md
- architect-generic-v1       -> prompts/architect/managed.md
- dev-backend-python-fastapi -> prompts/dev/managed.md
- dev-frontend-react-vite    -> prompts/dev/managed.md (mesmo prompt; especializacao via run config)
- reviewer-generic-v1        -> prompts/reviewer/managed.md  (TODO criar)
- onboarding-analyst-v1      -> prompts/onboarding/managed.md (TODO criar — T10)

Uso:
    python -m scripts.dev.provision_managed_agents             # provisiona faltantes
    python -m scripts.dev.provision_managed_agents --force     # recria mesmo se ja existe
"""
from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

from anthropic import Anthropic
from dotenv import dotenv_values
from sqlalchemy import select

from dev_autonomo.agent_runtime.managed_runner import (
    ANTHROPIC_AGENT_TOOLSET,
    _ensure_agent,
)
from dev_autonomo.db.models import SkillTemplate
from dev_autonomo.db.session import session_scope


ENV = dotenv_values(Path("/home/rubens/dev-autonomo-workspace/secrets/.env"))
os.environ["ANTHROPIC_API_KEY"] = ENV["ANTHROPIC_API_KEY"]
PROMPTS_BASE = Path("/home/rubens/dev-autonomo-workspace/dev-autonomo/prompts")

# Ordem importa: Architect precisa dos Devs.
TIERS = [
    {"slug": "ba-generic-v1",                 "prompt": "ba/managed.md",          "model": "claude-sonnet-4-6",  "coord_of": None},
    {"slug": "dev-backend-python-fastapi-v1", "prompt": "dev/managed.md",         "model": "claude-sonnet-4-6",  "coord_of": None},
    {"slug": "dev-frontend-react-vite-v1",    "prompt": "dev/managed.md",         "model": "claude-sonnet-4-6",  "coord_of": None},
    # OA e Reviewer precisam de managed.md ainda — pulamos por ora se faltar.
    {"slug": "onboarding-analyst-v1",         "prompt": "onboarding/managed.md",  "model": "claude-opus-4-7",    "coord_of": None, "optional": True},
    {"slug": "reviewer-generic-v1",           "prompt": "reviewer/managed.md",    "model": "claude-sonnet-4-6",  "coord_of": None, "optional": True},
    # Architect por ultimo — depende de dev-backend + dev-frontend ja criados.
    {"slug": "architect-generic-v1",          "prompt": "architect/managed.md",   "model": "claude-opus-4-7",
     "coord_of": ["dev-backend-python-fastapi-v1", "dev-frontend-react-vite-v1"]},
]


async def provision_one(
    session,
    anth: Anthropic,
    config: dict,
    force: bool,
) -> dict:
    slug = config["slug"]
    prompt_rel = config["prompt"]
    model = config["model"]
    coord_of = config.get("coord_of")
    optional = config.get("optional", False)

    prompt_path = PROMPTS_BASE / prompt_rel
    if not prompt_path.exists():
        msg = f"prompt nao existe: {prompt_path}"
        if optional:
            return {"slug": slug, "status": "skipped_no_prompt", "msg": msg}
        return {"slug": slug, "status": "missing_prompt", "msg": msg}

    tpl = (await session.execute(
        select(SkillTemplate).where(SkillTemplate.slug == slug)
    )).scalar_one_or_none()
    if tpl is None:
        return {"slug": slug, "status": "missing_skill_template"}

    if tpl.anthropic_agent_id and not force:
        return {"slug": slug, "status": "already_provisioned", "agent_id": tpl.anthropic_agent_id}

    if force and tpl.anthropic_agent_id:
        # Archive antigo antes de recriar
        try:
            anth.beta.agents.archive(tpl.anthropic_agent_id)
        except Exception as exc:
            print(f"  warn: archive antigo falhou: {exc}")
        tpl.anthropic_agent_id = None
        await session.flush()

    # Resolve multiagent se coord_of
    multiagent = None
    if coord_of:
        sub_ids = []
        for sub_slug in coord_of:
            sub = (await session.execute(
                select(SkillTemplate).where(SkillTemplate.slug == sub_slug)
            )).scalar_one()
            if not sub.anthropic_agent_id:
                return {"slug": slug, "status": "sub_agent_not_ready", "sub": sub_slug}
            sub_ids.append(sub.anthropic_agent_id)
        multiagent = {"type": "coordinator", "agents": sub_ids}

    prompt = prompt_path.read_text()
    agent_id = await _ensure_agent(
        session, anth, tpl, prompt, model, [], multiagent,
    )
    await session.flush()
    return {"slug": slug, "status": "created", "agent_id": agent_id, "multiagent": multiagent}


async def main(force: bool):
    anth = Anthropic()
    async with session_scope() as s:
        results = []
        for cfg in TIERS:
            print(f"\n--- {cfg['slug']} ---")
            res = await provision_one(s, anth, cfg, force)
            print(f"  -> {res}")
            results.append(res)
        await s.commit()

    print("\n" + "=" * 70)
    print("Resumo:")
    for r in results:
        flag = {
            "created": "🆕",
            "already_provisioned": "✓",
            "skipped_no_prompt": "⏭",
            "missing_skill_template": "❌",
            "missing_prompt": "❌",
            "sub_agent_not_ready": "❌",
        }.get(r["status"], "?")
        agent_id = r.get("agent_id", "")
        print(f"  {flag} {r['slug']:<40} {r['status']:<25} {agent_id}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--force", action="store_true", help="Re-cria mesmo se ja provisionado")
    args = p.parse_args()
    asyncio.run(main(args.force))
