"""Seed idempotente de stack_profiles.

Lê catálogo em src/dev_autonomo/seed_data/stack_profiles.py e faz
UPSERT em stack_profiles. Rodar várias vezes não duplica — atualiza
linhas existentes com a versão atual do catálogo.

Uso:
    python -m scripts.dev.seed_stack_profiles            # upsert all
    python -m scripts.dev.seed_stack_profiles --dry-run  # mostra o que faria
"""
from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dev_autonomo.db.models import StackProfile
from dev_autonomo.db.session import session_scope
from dev_autonomo.seed_data.stack_profiles import STACK_PROFILES


async def upsert_one(session: AsyncSession, profile_data: dict, dry_run: bool) -> str:
    """Insert se nao existe; update se existe. Retorna acao ('created' | 'updated' | 'unchanged')."""
    slug = profile_data["slug"]
    existing = (await session.execute(
        select(StackProfile).where(StackProfile.slug == slug)
    )).scalar_one_or_none()

    if existing is None:
        action = "would create" if dry_run else "created"
        if not dry_run:
            session.add(StackProfile(**profile_data))
        return action

    # Compara campos relevantes pra ver se mudou.
    changed_fields: list[str] = []
    for field in (
        "name", "description", "base_prompt_template",
        "default_tools", "default_model_alias",
        "conventions_seed", "active",
    ):
        if getattr(existing, field) != profile_data[field]:
            changed_fields.append(field)

    if not changed_fields:
        return "unchanged"

    action = f"would update [{', '.join(changed_fields)}]" if dry_run else f"updated [{', '.join(changed_fields)}]"
    if not dry_run:
        for field in changed_fields:
            setattr(existing, field, profile_data[field])
    return action


async def main(dry_run: bool):
    print(f"{'DRY-RUN' if dry_run else 'APPLY'} — {len(STACK_PROFILES)} stack profiles no catálogo")
    print("=" * 70)

    stats = {"created": 0, "updated": 0, "unchanged": 0}
    async with session_scope() as s:
        for profile in STACK_PROFILES:
            action = await upsert_one(s, profile, dry_run)
            print(f"  {profile['slug']:<35} {action}")
            if "creat" in action:
                stats["created"] += 1
            elif "updat" in action:
                stats["updated"] += 1
            else:
                stats["unchanged"] += 1
        if not dry_run:
            await s.commit()

    print("=" * 70)
    print(f"  Resumo: {stats['created']} criados, {stats['updated']} atualizados, {stats['unchanged']} unchanged")
    print(f"  Total no catálogo: {len(STACK_PROFILES)}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    asyncio.run(main(args.dry_run))
