"""Skill proposer — gera draft de skill_template baseado em stack + manifest.

Bloco D do roadmap stack-knowledge. Fluxo:

1. OA (bloco T10) escreveu manifest.json no memory_store da squad.
2. Wizard cliente (bloco E) chama POST /client/squads/{id}/propose-skills
   passando o manifest.
3. Esse service:
   - Pega stack_profile da stack detectada.
   - Renderiza base_prompt_template com Jinja2 + variables do manifest.
   - Chama Claude Sonnet pra refinar/contextualizar.
   - Retorna SkillTemplateDraft.
4. Cliente edita o draft e POST /client/squads/{id}/skills cria
   skill_template + provisiona agent na Anthropic.

Cada chamada Claude gera ExternalApiCall com kind=SKILL_PROPOSAL
ligada ao client (custo visivel na cost page).

Foco: tier=DEV (skill_profile so cobre Dev por enquanto, decisao do
Bloco B). Outros tiers (BA/Architect/Reviewer) usam prompts manuais.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any
from uuid import UUID

import anthropic
from jinja2 import Environment, StrictUndefined
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dev_autonomo.common.claude_pricing import get_pricing
from dev_autonomo.common.enums import (
    AgentTier,
    ApiCallKind,
    ApiProvider,
)
from dev_autonomo.config import get_settings
from dev_autonomo.db.models import (
    ExternalApiCall,
    SkillTemplate,
    StackProfile,
)

logger = logging.getLogger(__name__)


PROPOSE_SKILL_MODEL = "claude-sonnet-4-6"

# Templates Jinja sao renderizados com StrictUndefined pra falhar cedo
# se variable esperada faltar (vs silenciosamente vazio).
_jinja_env = Environment(undefined=StrictUndefined, autoescape=False)


# Prompt meta — instrui Claude a refinar o template renderizado com
# detalhes do manifest da squad. Output esperado em JSON.
_REFINEMENT_PROMPT = """\
Voce esta gerando um system prompt de Dev Agent (Anthropic Managed Agent)
para uma squad especifica que vai trabalhar em codigo desta stack.

Contexto da stack (profile da plataforma):
- slug: {stack_slug}
- nome: {stack_name}
- linguagem/framework primario: {framework_main}

Manifest detectado pelo Onboarding Analyst (resumo dos repos):
```json
{manifest_json}
```

Template base ja renderizado:
```
{base_template_rendered}
```

Tarefa:
1. Refine o template base pra contextualizar com o manifest especifico
   (build_command/test_command/lint_command vindos do manifest).
2. Mantenha a estrutura do template (Identidade, Stack, Convencoes,
   Fluxo obrigatorio, Regras inegociaveis, RAG).
3. Acrescente 2-4 itens em "Convencoes desta stack" especificos pra
   esse repo (ex: organizacao de modulos, conventions visiveis no
   manifest). Se nao identificar nada especifico, mantenha generico.
4. NAO invente convencoes que nao tem suporte no manifest.
5. Retorne SOMENTE o system prompt final, sem preambulo ou JSON wrapper.
"""


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class SkillTemplateDraft:
    """Draft de skill_template gerado por propose_skill_from_stack."""

    slug: str             # sugerido (ex: dev-hybris-acme-pagamentos-v1)
    name: str             # ex: "Dev Hybris (Acme Pagamentos)"
    description: str
    tier: AgentTier       # geralmente DEV
    model_alias: str
    system_prompt: str    # ja renderizado e refinado
    tools_enabled: list[dict]
    stack_primary: dict
    stack_secondary: list
    knowledge_partitions: list
    template_variables: dict  # variables usadas no render (auditavel)
    parent_stack_profile_id: UUID


@dataclass(slots=True)
class ProposeResult:
    """Resultado de propose_skill_from_stack."""

    drafts: list[SkillTemplateDraft] = field(default_factory=list)
    api_call_cost_usd: Decimal = Decimal("0")
    input_tokens: int = 0
    output_tokens: int = 0
    api_call_id: UUID | None = None


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------


def render_skill_prompt(template: str, variables: dict[str, Any]) -> str:
    """Renderiza Jinja2 template com variables. Falha se variable faltar."""
    return _jinja_env.from_string(template).render(**variables)


def _variables_from_manifest(repo_entry: dict[str, Any]) -> dict[str, Any]:
    """Extrai variables Jinja a partir de uma entrada de repo no manifest.

    Manifest schema vem do OA prompt (prompts/onboarding/managed.md):
    {
      "repos": [
        {
          "name": "...",
          "primary_language": "...",
          "framework": "...",
          "build_command": "..." | null,
          "test_command": "..." | null,
          "lint_command": "..." | null,
          ...
        }
      ]
    }
    """
    return {
        "build_command": repo_entry.get("build_command") or "(nao detectado — verificar manualmente)",
        "test_command": repo_entry.get("test_command") or "(nao detectado)",
        "lint_command": repo_entry.get("lint_command") or "(nao detectado)",
        "stack_version": "(nao detectado)",  # pode vir de outro campo do manifest
    }


# ---------------------------------------------------------------------------
# Propose
# ---------------------------------------------------------------------------


def _build_anthropic_client() -> anthropic.Anthropic:
    return anthropic.Anthropic(
        api_key=get_settings().ANTHROPIC_API_KEY.get_secret_value()
    )


async def propose_skill_from_stack(
    session: AsyncSession,
    *,
    stack_slug: str,
    manifest_json: dict,
    client_id: UUID,
    task_id: UUID | None = None,
    anthropic_client: anthropic.Anthropic | None = None,
) -> ProposeResult:
    """Gera SkillTemplateDraft pra UMA stack detectada no manifest.

    Manifest pode ter multiplos repos — geramos 1 draft por repo cuja
    framework bate com a stack_slug pedida (geralmente 1 repo).

    Cada chamada gera 1 ExternalApiCall com kind=SKILL_PROPOSAL.
    """
    # 1. Resolve stack_profile
    profile = (await session.execute(
        select(StackProfile).where(StackProfile.slug == stack_slug)
    )).scalar_one_or_none()
    if profile is None:
        raise ValueError(f"stack profile '{stack_slug}' nao encontrado.")

    # 2. Identifica repos no manifest que batem com essa stack.
    repos = manifest_json.get("repos", []) or []
    matching_repos = [
        r for r in repos
        if _matches_stack(r, profile)
    ]
    if not matching_repos:
        # Sem match — gera draft generico com defaults do profile.
        matching_repos = [{"name": "default", "primary_language": "?", "framework": profile.name}]

    anth = anthropic_client or _build_anthropic_client()
    result = ProposeResult()

    for repo in matching_repos:
        variables = _variables_from_manifest(repo)

        # 3. Renderiza template base
        try:
            base_rendered = render_skill_prompt(profile.base_prompt_template, variables)
        except Exception as exc:
            logger.exception("render falhou stack=%s repo=%s: %s",
                             stack_slug, repo.get("name"), exc)
            continue

        # 4. Chama Claude pra refinar com manifest context
        import json as _json
        refinement_prompt = _REFINEMENT_PROMPT.format(
            stack_slug=profile.slug,
            stack_name=profile.name,
            framework_main=repo.get("framework", profile.name),
            manifest_json=_json.dumps(repo, indent=2),
            base_template_rendered=base_rendered,
        )

        started = time.monotonic()
        try:
            response = anth.messages.create(
                model=PROPOSE_SKILL_MODEL,
                max_tokens=4096,
                messages=[{"role": "user", "content": refinement_prompt}],
            )
        except Exception as exc:
            logger.exception("propose Claude call falhou: %s", exc)
            continue
        latency_ms = int((time.monotonic() - started) * 1000)

        refined_prompt = ""
        for block in response.content:
            if hasattr(block, "text"):
                refined_prompt += block.text
        refined_prompt = refined_prompt.strip()

        # 5. Persiste ExternalApiCall (custo visivel pro cliente)
        usage = response.usage
        input_tokens = getattr(usage, "input_tokens", 0) or 0
        output_tokens = getattr(usage, "output_tokens", 0) or 0
        cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
        cache_creation_obj = getattr(usage, "cache_creation_input_tokens", 0) or 0
        cache_creation = int(cache_creation_obj) if isinstance(cache_creation_obj, int) else 0

        pricing = get_pricing(PROPOSE_SKILL_MODEL, provider="anthropic")
        cost = pricing.cost_usd(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read,
            cache_write_tokens=cache_creation,
        )

        api_call = ExternalApiCall(
            client_id=client_id,
            task_id=task_id,
            agent_instance_id=None,
            provider=ApiProvider.ANTHROPIC,
            kind=ApiCallKind.SKILL_PROPOSAL,
            model=PROPOSE_SKILL_MODEL,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_creation_input_tokens=cache_creation,
            cache_read_input_tokens=cache_read,
            cost_usd=cost,
            latency_ms=latency_ms,
            request_id=getattr(response, "id", None),
            error=None,
        )
        session.add(api_call)
        await session.flush()

        # 6. Monta draft
        repo_slug_part = (repo.get("name") or "default").lower().replace(" ", "-")
        draft_slug = f"dev-{profile.slug}-{repo_slug_part}-v1"
        draft = SkillTemplateDraft(
            slug=draft_slug,
            name=f"Dev {profile.name} ({repo.get('name', 'default')})",
            description=f"Dev Agent para repo {repo.get('name')} usando {profile.name}.",
            tier=AgentTier.DEV,
            model_alias=profile.default_model_alias,
            system_prompt=refined_prompt or base_rendered,
            tools_enabled=list(profile.default_tools),
            stack_primary={
                "slug": profile.slug,
                "language": repo.get("primary_language"),
                "framework": repo.get("framework"),
            },
            stack_secondary=repo.get("stack_secondary", []),
            knowledge_partitions=[
                f"stack_patterns:{profile.slug}",
            ],
            template_variables=variables,
            parent_stack_profile_id=profile.id,
        )
        result.drafts.append(draft)
        result.api_call_cost_usd += cost
        result.input_tokens += input_tokens
        result.output_tokens += output_tokens
        result.api_call_id = api_call.id

    return result


def _matches_stack(repo_entry: dict, profile: StackProfile) -> bool:
    """Heuristica simples — bate por linguagem + framework keyword."""
    seed = profile.conventions_seed or {}
    expected_lang = (seed.get("language") or "").lower()
    expected_fw = (seed.get("framework") or "").lower()

    repo_lang = (repo_entry.get("primary_language") or "").lower()
    repo_fw = (repo_entry.get("framework") or "").lower()

    if expected_lang and expected_lang in repo_lang:
        if expected_fw and any(part in repo_fw for part in expected_fw.split()):
            return True
        if not expected_fw:
            return True
    return False


# ---------------------------------------------------------------------------
# Materialize draft -> SkillTemplate
# ---------------------------------------------------------------------------


async def materialize_skill_from_draft(
    session: AsyncSession,
    *,
    draft: SkillTemplateDraft,
    client_id: UUID,
    edited_system_prompt: str | None = None,
    anthropic_client: anthropic.Anthropic | None = None,
) -> SkillTemplate:
    """Persiste skill_template a partir do draft + provisiona agent na Anthropic.

    Caller (endpoint POST /client/squads/{id}/skills) chama isso apos
    cliente editar o draft. ``edited_system_prompt`` override do prompt
    do draft (caso cliente tenha mudado).
    """
    final_prompt = (edited_system_prompt or draft.system_prompt).strip()

    # 1. Cria SkillTemplate no DB
    skill = SkillTemplate(
        client_id=client_id,
        slug=draft.slug,
        name=draft.name,
        description=draft.description,
        version=1,
        tier=draft.tier,
        model_alias=draft.model_alias,
        stack_primary=draft.stack_primary,
        stack_secondary=draft.stack_secondary,
        system_prompt_ref="<generated>",
        system_prompt_template=draft.system_prompt,  # original do propose, pra audit
        template_variables=draft.template_variables,
        tools_enabled=draft.tools_enabled,
        knowledge_partitions=draft.knowledge_partitions,
        active=True,
        parent_stack_profile_id=draft.parent_stack_profile_id,
    )
    session.add(skill)
    await session.flush()

    # 2. Provisiona agent na Anthropic com o prompt final (editado)
    anth = anthropic_client or _build_anthropic_client()
    try:
        agent = anth.beta.agents.create(
            name=f"obris-{skill.slug}-v{skill.version}",
            model=skill.model_alias,
            system=final_prompt,
            tools=list(skill.tools_enabled),
        )
        skill.anthropic_agent_id = agent.id
        logger.info("skill provisionado client=%s slug=%s agent_id=%s",
                    client_id, skill.slug, agent.id)
    except Exception as exc:
        logger.exception("falha ao provisionar agent na Anthropic: %s", exc)
        # Skill fica no DB sem agent_id — cliente pode tentar reprovisionar.

    await session.flush()
    return skill
