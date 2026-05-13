"""Cria Client+User+Squad+Manifest+SkillTemplates iniciais para desenvolvimento.

DESCARTAVEL: este script existe enquanto nao temos painel admin (task 7-8).
Quando o painel existir, esse seed vira o fluxo de "onboard novo cliente" + provisionar squad.

Idempotente: pode rodar varias vezes sem duplicar.

Uso:
    uv run python -m scripts.dev.seed_dev_data
"""

from __future__ import annotations

import asyncio
from decimal import Decimal

from sqlalchemy import select

from dev_autonomo.common.enums import (
    AgentTier,
    BillingPlanKind,
    SquadStatus,
    UserRole,
)
from dev_autonomo.db.models import (
    Client,
    ClientBillingPlan,
    ClientMembership,
    Manifest,
    SkillTemplate,
    Squad,
    User,
)
from dev_autonomo.db.session import session_scope

# ---- Constantes do "cliente zero" (o proprio usuario) ----

CLIENT_SLUG = "reco-orbis"
CLIENT_NAME = "Reco Orbis (cliente zero)"
JIRA_WORKSPACE_URL = "https://openflow.atlassian.net"
JIRA_EMAIL = "leonardo@openflow.com.br"

USER_EMAIL = "rubens.lenzi@hotmail.com"
USER_NAME = "Rubens Lenzi (system admin)"

SQUAD_SLUG = "reco-orbis-main"
SQUAD_NAME = "Squad Reco Orbis"
SQUAD_DOMAIN = "recommendation"

REPO_BACKEND = "https://github.com/rlenzi/reco.orbis.ai.api"
REPO_FRONTEND = "https://github.com/rlenzi/reco.obris.ai.frontend"


async def seed() -> None:
    async with session_scope() as session:
        # ---- 1. Client (tenant) ----
        client = (
            await session.execute(select(Client).where(Client.slug == CLIENT_SLUG))
        ).scalar_one_or_none()
        if client is None:
            client = Client(
                slug=CLIENT_SLUG,
                name=CLIENT_NAME,
                status="active",
                jira_workspace_url=JIRA_WORKSPACE_URL,
                jira_email=JIRA_EMAIL,
            )
            session.add(client)
            await session.flush()
            print(f"+ Client criado: {client.slug} ({client.id})")
        else:
            print(f"= Client ja existe: {client.slug} ({client.id})")

        # ---- 2. Billing plan (hibrido, com cota generosa para dev) ----
        plan = (
            await session.execute(
                select(ClientBillingPlan).where(ClientBillingPlan.client_id == client.id)
            )
        ).scalar_one_or_none()
        if plan is None:
            plan = ClientBillingPlan(
                client_id=client.id,
                plan_kind=BillingPlanKind.HYBRID,
                base_fee_monthly_brl=Decimal("0"),
                included_quota_tokens=10_000_000,
                included_quota_tasks=100,
                overage_markup_pct=Decimal("200"),
            )
            session.add(plan)
            print("+ Billing plan criado (HIBRIDO, 10M tokens / 100 tasks / 200% markup)")
        else:
            print("= Billing plan ja existe")

        # ---- 3. User (system admin) ----
        user = (
            await session.execute(select(User).where(User.email == USER_EMAIL))
        ).scalar_one_or_none()
        if user is None:
            # Senha default de dev: 'devauto-admin'. Trocar em prod.
            from dev_autonomo.control_plane.auth import hash_password
            user = User(
                email=USER_EMAIL,
                full_name=USER_NAME,
                hashed_password=hash_password("devauto-admin"),
                is_system_admin=True,
                active=True,
            )
            session.add(user)
            await session.flush()
            print(f"+ User criado: {user.email} (system_admin)")
        else:
            print(f"= User ja existe: {user.email}")

        # ---- 4. Client membership (admin do client) ----
        membership = (
            await session.execute(
                select(ClientMembership).where(
                    ClientMembership.client_id == client.id,
                    ClientMembership.user_id == user.id,
                )
            )
        ).scalar_one_or_none()
        if membership is None:
            membership = ClientMembership(
                client_id=client.id,
                user_id=user.id,
                role=UserRole.CLIENT_ADMIN,
            )
            session.add(membership)
            print(f"+ Membership criado: {user.email} eh CLIENT_ADMIN de {client.slug}")
        else:
            print(f"= Membership ja existe")

        # ---- 5. Squad ----
        squad = (
            await session.execute(
                select(Squad).where(
                    Squad.client_id == client.id, Squad.slug == SQUAD_SLUG
                )
            )
        ).scalar_one_or_none()
        if squad is None:
            squad = Squad(
                client_id=client.id,
                slug=SQUAD_SLUG,
                name=SQUAD_NAME,
                description="Squad unica que atende o produto Reco Orbis (back + front).",
                domain=SQUAD_DOMAIN,
                status=SquadStatus.PROVISIONING,
            )
            session.add(squad)
            await session.flush()
            print(f"+ Squad criada: {squad.slug} ({squad.id})")
        else:
            print(f"= Squad ja existe: {squad.slug}")

        # ---- 6. Manifest da squad (v1) ----
        manifest = (
            await session.execute(
                select(Manifest).where(
                    Manifest.squad_id == squad.id, Manifest.version == 1
                )
            )
        ).scalar_one_or_none()
        if manifest is None:
            content = {
                "owns": {
                    "repos": [REPO_BACKEND, REPO_FRONTEND],
                    "database_schemas": ["public"],
                    "jira_projects": ["LEO"],
                    "apis": {"publishes": ["/api/*"], "consumes": []},
                    "events": {"publishes": [], "consumes": []},
                },
                "humans_embedded": {
                    "tech_lead": USER_EMAIL,
                    "reviewers": [USER_EMAIL],
                },
            }
            manifest = Manifest(
                client_id=client.id,
                squad_id=squad.id,
                version=1,
                content=content,
                created_by_user_id=user.id,
            )
            session.add(manifest)
            await session.flush()
            squad.current_manifest_id = manifest.id
            print(f"+ Manifest v1 criado e linkado a squad")
        else:
            print(f"= Manifest v1 ja existe")

        # ---- 7. Skill templates iniciais (SYSTEM, compartilhados) ----
        skill_specs = [
            {
                "slug": "ba-generic-v1",
                "name": "BA Generico",
                "tier": AgentTier.BA,
                "model_alias": "claude-sonnet-4-6",
                "system_prompt_ref": "prompts/ba/generic.md",
                "tools_enabled": [
                    "retrieve_knowledge",
                    "jira_get_issue",
                    "jira_add_comment",
                    "jira_create_subtask",
                ],
                "knowledge_partitions": ["business:{squad}", "decisions:{squad}", "playbook:{squad}"],
            },
            {
                "slug": "architect-generic-v1",
                "name": "Architect Generico",
                "tier": AgentTier.ARCHITECT,
                "model_alias": "claude-sonnet-4-6",
                "system_prompt_ref": "prompts/architect/generic.md",
                "tools_enabled": [
                    "retrieve_knowledge",
                    "jira_get_issue",
                    "jira_create_subtask",
                    "jira_add_comment",
                    "jira_update_status",
                    "signal_complete",
                ],
                "knowledge_partitions": [
                    "code:{squad}",
                    "conventions:{squad}",
                    "playbook:{squad}",
                    "architecture:{squad}",
                ],
            },
            {
                "slug": "dev-backend-python-fastapi-v1",
                "name": "Dev Backend Python+FastAPI",
                "tier": AgentTier.DEV,
                "model_alias": "claude-sonnet-4-6",
                "stack_primary": {"lang": "python", "framework": "fastapi"},
                "stack_secondary": ["sqlalchemy", "alembic", "pydantic", "pytest"],
                "system_prompt_ref": "prompts/dev/backend-python-fastapi.md",
                "tools_enabled": [
                    "retrieve_knowledge",
                    "read_file",
                    "edit_file",
                    "create_file",
                    "run_tests",
                    "git_branch",
                    "git_commit",
                    "git_push",
                    "github_create_pr",
                    "jira_update_status",
                    "create_cross_squad_request",
                ],
                "knowledge_partitions": [
                    "code:{squad}",
                    "conventions:{squad}",
                    "playbook:{squad}",
                    "api_contracts:{squad}",
                ],
            },
            {
                "slug": "dev-frontend-react-vite-v1",
                "name": "Dev Frontend React+Vite",
                "tier": AgentTier.DEV,
                "model_alias": "claude-sonnet-4-6",
                "stack_primary": {"lang": "typescript", "framework": "react", "bundler": "vite"},
                "stack_secondary": ["tailwind", "radix-ui", "react-router"],
                "system_prompt_ref": "prompts/dev/frontend-react-vite.md",
                "tools_enabled": [
                    "retrieve_knowledge",
                    "read_file",
                    "edit_file",
                    "create_file",
                    "run_tests",
                    "git_branch",
                    "git_commit",
                    "git_push",
                    "github_create_pr",
                    "jira_update_status",
                ],
                "knowledge_partitions": [
                    "code:{squad}",
                    "conventions:{squad}",
                    "playbook:{squad}",
                    "api_contracts:{squad}",
                ],
            },
            {
                "slug": "onboarding-analyst-v1",
                "name": "Onboarding Analyst",
                "tier": AgentTier.ONBOARDING_ANALYST,
                "model_alias": "claude-opus-4-7",
                "system_prompt_ref": "prompts/onboarding/analyst.md",
                "tools_enabled": [
                    "retrieve_knowledge",
                    "analyze_repo",
                    "generate_architecture_doc",
                    "generate_conventions_doc",
                    "generate_interview_questions",
                    "synthesize_interview_responses",
                    "run_pr_replay_validation",
                ],
                "knowledge_partitions": [
                    "code:{squad}",
                    "architecture:{squad}",
                    "conventions:{squad}",
                ],
            },
        ]

        for spec in skill_specs:
            existing = (
                await session.execute(
                    select(SkillTemplate).where(
                        SkillTemplate.client_id.is_(None),  # system templates
                        SkillTemplate.slug == spec["slug"],
                        SkillTemplate.version == 1,
                    )
                )
            ).scalar_one_or_none()
            if existing is None:
                tpl = SkillTemplate(
                    client_id=None,
                    slug=spec["slug"],
                    name=spec["name"],
                    description=None,
                    version=1,
                    tier=spec["tier"],
                    model_alias=spec["model_alias"],
                    stack_primary=spec.get("stack_primary", {}),
                    stack_secondary=spec.get("stack_secondary", []),
                    system_prompt_ref=spec["system_prompt_ref"],
                    tools_enabled=spec["tools_enabled"],
                    knowledge_partitions=spec["knowledge_partitions"],
                    active=True,
                )
                session.add(tpl)
                print(f"+ SkillTemplate: {spec['slug']}")
            else:
                print(f"= SkillTemplate ja existe: {spec['slug']}")


def main() -> None:
    asyncio.run(seed())
    print("\nSeed concluido.")


if __name__ == "__main__":
    main()
