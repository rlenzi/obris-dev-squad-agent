"""Runner novo baseado em Claude Managed Agents (Anthropic, beta abr/2026).

Substitui ``agent_runtime/worker.py`` + ``scripts/dev/_runner_lib.run_task``.

Fluxo:
1. Resolve identidades locais (Client, Squad, AgentInstance, SkillTemplate)
2. Cria/recupera Task local (espelho do Jira)
3. Cria/recupera Agent na Anthropic (cache por skill_template)
4. Cria/recupera Environment na Anthropic (cache por client)
5. Cria Session pra essa Task
6. Envia user.message
7. Stream events ate session.status_idle
8. Faz session.retrieve() e grava ExternalApiCall com usage real

Cache de Agent/Environment persiste em ``skill_templates.anthropic_agent_id``
e ``clients.anthropic_environment_id`` (migration c3d4e5f6a7b8).

session_id da Anthropic e persistido em ``Task.demand_payload['anthropic_session_id']``
pra rastreabilidade.

MCP servers: opcional, passa lista de dicts ``{type, url, ...}``. Vazio
significa que o agente roda só com tools nativas (bash + file ops + web).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

import anthropic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dev_autonomo.common.claude_pricing import get_pricing
from dev_autonomo.common.enums import ApiCallKind, ApiProvider
from dev_autonomo.config import get_settings
from dev_autonomo.db.models import (
    AgentInstance,
    Client,
    SkillTemplate,
    Squad,
    Task,
)
from dev_autonomo.db.models.cost import ExternalApiCall
from dev_autonomo.db.session import session_scope

logger = logging.getLogger(__name__)

ANTHROPIC_AGENT_TOOLSET = "agent_toolset_20260401"


@dataclass
class ManagedTaskSpec:
    """Especifica como rodar um agente via Managed Agents.

    Sem ``tools`` — Managed Agents traz toolset nativo (bash + file ops +
    web search). Pra acessar Jira/GitHub/nosso Knowledge Hub use
    ``mcp_servers`` apontando pra servers MCP HTTP/stdio.
    """

    agent_name: str  # AgentInstance.name no DB local
    system_prompt: str = ""
    system_prompt_path: Path | None = None

    client_slug: str = "dev-autonomo"
    squad_slug: str = "plataforma"

    model: str = "claude-sonnet-4-6"

    # MCP servers que o agent vai conectar. Cada item dict no formato
    # esperado pelo SDK (ver docs/managed-agents/mcp-servers).
    mcp_servers: list[dict[str, Any]] = field(default_factory=list)

    # Env vars injetadas no container (uteis pra tokens que tools nativas
    # tipo bash possam usar via curl, ex JIRA_TOKEN).
    environment_vars: dict[str, str] = field(default_factory=dict)

    # Multiagent coordinator topology. Quando set, este agent vira
    # coordinator que delega a sub-agents listados.
    # Formato canonico: {"type": "coordinator", "agents": [<agent_id>, ...]}
    # Os sub-agent IDs devem estar criados ANTES (resolva via DB e passe).
    multiagent: dict[str, Any] | None = None

    user_prompt_builder: Any = None  # Callable[[str], str]


@dataclass
class ManagedRunResult:
    completed: bool
    session_id: str | None
    tool_calls: list[str]
    output_text: str
    latency_seconds: float
    cost_usd: Decimal
    input_tokens: int
    output_tokens: int
    cache_creation_tokens: int
    cache_read_tokens: int
    status_final: str | None
    error: str | None = None


async def _resolve_identities(
    session: AsyncSession, spec: ManagedTaskSpec
) -> tuple[Client, Squad, AgentInstance, SkillTemplate]:
    client = (
        await session.execute(
            select(Client).where(Client.slug == spec.client_slug)
        )
    ).scalar_one()
    squad = (
        await session.execute(
            select(Squad).where(
                Squad.client_id == client.id, Squad.slug == spec.squad_slug
            )
        )
    ).scalar_one()
    agent = (
        await session.execute(
            select(AgentInstance).where(
                AgentInstance.squad_id == squad.id,
                AgentInstance.name == spec.agent_name,
            )
        )
    ).scalar_one_or_none()
    if agent is None:
        raise RuntimeError(
            f"AgentInstance '{spec.agent_name}' nao encontrado na squad "
            f"'{squad.slug}' do cliente '{client.slug}'. Provisione antes "
            f"via seed ou painel."
        )
    tpl = (
        await session.execute(
            select(SkillTemplate).where(SkillTemplate.id == agent.skill_template_id)
        )
    ).scalar_one()
    return client, squad, agent, tpl


async def _ensure_task(
    session: AsyncSession,
    client: Client,
    squad: Squad,
    agent: AgentInstance,
    issue_key: str,
) -> Task:
    """Cria ou recupera Task local. Idempotente por jira_issue_key."""
    is_pr = issue_key.isdigit()
    jira_key = f"PR-{issue_key}" if is_pr else issue_key
    title = f"Review PR #{issue_key}" if is_pr else f"Issue {issue_key}"
    existing = (
        await session.execute(
            select(Task).where(
                Task.client_id == client.id,
                Task.jira_workspace_url == client.jira_workspace_url,
                Task.jira_issue_key == jira_key,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        if existing.assigned_agent_id != agent.id:
            existing.assigned_agent_id = agent.id
        return existing

    task = Task(
        client_id=client.id,
        squad_id=squad.id,
        jira_workspace_url=client.jira_workspace_url,
        jira_issue_key=jira_key,
        title=title,
        assigned_agent_id=agent.id,
    )
    session.add(task)
    await session.flush()
    return task


def _build_anthropic_client() -> anthropic.Anthropic:
    settings = get_settings()
    return anthropic.Anthropic(
        api_key=settings.ANTHROPIC_API_KEY.get_secret_value()
    )


async def _ensure_agent(
    session: AsyncSession,
    anth_client: anthropic.Anthropic,
    skill_template: SkillTemplate,
    system_prompt: str,
    model: str,
    mcp_servers: list[dict[str, Any]],
    multiagent: dict[str, Any] | None = None,
) -> str:
    """Cria (ou recupera do DB) um Agent na Anthropic pra esse skill template.

    Persiste em ``skill_templates.anthropic_agent_id``.

    Quando ``multiagent`` e fornecido, cria como coordinator com sub-agents
    listados no roster. Sub-agent IDs devem ja existir (caller resolve).
    """
    if skill_template.anthropic_agent_id:
        return skill_template.anthropic_agent_id

    tools: list[dict[str, Any]] = [{"type": ANTHROPIC_AGENT_TOOLSET}]
    extras: dict[str, Any] = {}
    if mcp_servers:
        extras["mcp_servers"] = mcp_servers
    if multiagent:
        extras["multiagent"] = multiagent

    agent_obj = anth_client.beta.agents.create(
        name=f"obris-{skill_template.slug}-v{skill_template.version}",
        model=model,
        system=system_prompt,
        tools=tools,
        **extras,
    )
    logger.info(
        "managed_runner: agent criado tpl=%s agent_id=%s",
        skill_template.slug, agent_obj.id,
    )
    skill_template.anthropic_agent_id = agent_obj.id
    await session.flush()
    return agent_obj.id


async def _ensure_environment(
    session: AsyncSession,
    anth_client: anthropic.Anthropic,
    local_client: Client,
    environment_vars: dict[str, str],
) -> str:
    """Cria (ou recupera do DB) um Environment cloud unrestricted.

    Persiste em ``clients.anthropic_environment_id``.
    """
    if local_client.anthropic_environment_id:
        return local_client.anthropic_environment_id

    config: dict[str, Any] = {
        "type": "cloud",
        "networking": {"type": "unrestricted"},
    }
    # NOTA: passar env vars via config.env é rejeitado pela API
    # ("Extra inputs are not permitted"). Caminho canonico e vaults +
    # credentials (sub-fase propria). Pra MVP, secrets viajam inline no
    # user.message via user_prompt_builder.

    env = anth_client.beta.environments.create(
        name=f"obris-{local_client.slug}-{int(time.time())}",
        config=config,
    )
    logger.info(
        "managed_runner: environment criado client=%s env_id=%s",
        local_client.slug, env.id,
    )
    local_client.anthropic_environment_id = env.id
    await session.flush()
    return env.id


def _stream_events(
    client: anthropic.Anthropic,
    session_id: str,
    user_message: str,
) -> tuple[str, list[str]]:
    """Envia user.message e processa stream ate session.status_idle.

    Retorna (output_text_concatenado, lista_de_tool_names).
    """
    tool_uses: list[str] = []
    output_parts: list[str] = []

    with client.beta.sessions.events.stream(session_id) as stream:
        client.beta.sessions.events.send(
            session_id,
            events=[
                {
                    "type": "user.message",
                    "content": [{"type": "text", "text": user_message}],
                }
            ],
        )
        for event in stream:
            etype = getattr(event, "type", None)
            if etype == "agent.message":
                for block in getattr(event, "content", []) or []:
                    text = getattr(block, "text", "")
                    if text:
                        output_parts.append(text)
                        logger.debug("agent.message: %s", text[:200])
            elif etype == "agent.tool_use":
                name = getattr(event, "name", "?")
                tool_uses.append(name)
                logger.info("agent.tool_use: %s", name)
            elif etype == "agent.tool_result":
                is_err = getattr(event, "is_error", False)
                content = getattr(event, "content", None)
                preview = ""
                if isinstance(content, list):
                    for blk in content:
                        text = getattr(blk, "text", None)
                        if text:
                            preview = text[:300].replace("\n", " ⏎ ")
                            break
                logger.info(
                    "agent.tool_result is_error=%s preview=%s",
                    is_err, preview,
                )
            elif etype == "session.status_running":
                logger.debug("session.status_running")
            elif etype == "session.thread_created":
                logger.info(
                    "session.thread_created: agent=%s",
                    getattr(event, "agent_name", "?"),
                )
            elif etype == "session.status_idle":
                break
    return "".join(output_parts), tool_uses


async def _record_usage(
    session: AsyncSession,
    *,
    client_id: UUID,
    task_id: UUID,
    agent_instance_id: UUID,
    model: str,
    usage: Any,
    latency_ms: int,
    request_id: str | None,
) -> Decimal:
    """Persiste 1 ExternalApiCall com o usage agregado do session.

    Diferente do worker.py antigo (que gravava 1 call por turno do loop),
    o Managed Agents devolve agregado da sessao inteira. Gravamos como
    1 ApiCall só pra simplificar billing — depois podemos aumentar
    granularidade.
    """
    input_tokens = getattr(usage, "input_tokens", 0) or 0
    output_tokens = getattr(usage, "output_tokens", 0) or 0
    cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0

    cache_creation_obj = getattr(usage, "cache_creation", None)
    if cache_creation_obj is None:
        cache_creation = 0
    else:
        # cache_creation pode ter ephemeral_5m_input_tokens + ephemeral_1h_input_tokens
        cache_creation = (
            (getattr(cache_creation_obj, "ephemeral_5m_input_tokens", 0) or 0)
            + (getattr(cache_creation_obj, "ephemeral_1h_input_tokens", 0) or 0)
        )

    pricing = get_pricing(model, provider="anthropic")
    cost = pricing.cost_usd(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_tokens=cache_read,
        cache_write_tokens=cache_creation,
    )

    call = ExternalApiCall(
        client_id=client_id,
        task_id=task_id,
        agent_instance_id=agent_instance_id,
        provider=ApiProvider.ANTHROPIC,
        kind=ApiCallKind.CHAT,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_creation_input_tokens=cache_creation,
        cache_read_input_tokens=cache_read,
        cost_usd=cost,
        latency_ms=latency_ms,
        request_id=request_id,
        error=None,
    )
    session.add(call)
    await session.flush()
    return cost


async def run_managed_task(
    spec: ManagedTaskSpec, issue_key: str
) -> ManagedRunResult:
    """Roda agente via Managed Agents contra a issue informada."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    for noisy in ("sqlalchemy.engine", "httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    print("=" * 70)
    print(f"Task {issue_key} · {spec.agent_name} · managed_runner")
    print("=" * 70)

    if spec.system_prompt_path is not None:
        system_prompt = spec.system_prompt_path.read_text(encoding="utf-8")
    elif spec.system_prompt:
        system_prompt = spec.system_prompt
    else:
        raise RuntimeError(
            "ManagedTaskSpec precisa de system_prompt ou system_prompt_path"
        )

    if spec.user_prompt_builder is None:
        raise RuntimeError("ManagedTaskSpec precisa de user_prompt_builder")

    anthropic_client = _build_anthropic_client()
    started_at = time.monotonic()

    async with session_scope() as session:
        local_client, squad, agent_inst, tpl = await _resolve_identities(
            session, spec
        )
        task = await _ensure_task(
            session, local_client, squad, agent_inst, issue_key
        )
        await session.commit()

        print(f"\nCliente:  {local_client.name} ({local_client.slug})")
        print(f"Squad:    {squad.name}")
        print(f"Agente:   {agent_inst.name}")
        print(f"Skill:    {tpl.slug} v{tpl.version}")
        print(f"Issue:    {issue_key}")
        print(f"Task:     {task.id}")

        # 1. Agent na Anthropic
        print("\n-- Anthropic setup --")
        agent_id = await _ensure_agent(
            session, anthropic_client, tpl, system_prompt, spec.model,
            spec.mcp_servers, spec.multiagent,
        )
        print(f"  agent_id     = {agent_id}")

        # 2. Environment
        env_id = await _ensure_environment(
            session, anthropic_client, local_client, spec.environment_vars,
        )
        print(f"  environment  = {env_id}")

        # 3. Session
        anth_session = anthropic_client.beta.sessions.create(
            agent=agent_id,
            environment_id=env_id,
            title=f"{issue_key} - {agent_inst.name}",
        )
        print(f"  session_id   = {anth_session.id}")

        # Persiste session_id no Task local (rastreabilidade)
        payload = dict(task.demand_payload or {})
        payload["anthropic_session_id"] = anth_session.id
        payload["anthropic_agent_id"] = agent_id
        payload["anthropic_environment_id"] = env_id
        task.demand_payload = payload
        await session.commit()

    # 4. User message + stream (fora de session_scope pra nao prender DB
    # conexao durante minutos de stream)
    user_message = spec.user_prompt_builder(issue_key)
    print(f"\nuser.message:\n{user_message[:200]}{'...' if len(user_message) > 200 else ''}")
    print("\n-- Stream --")

    error: str | None = None
    output_text = ""
    tool_uses: list[str] = []
    try:
        output_text, tool_uses = _stream_events(
            anthropic_client, anth_session.id, user_message
        )
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        logger.exception("stream falhou: %s", error)

    latency = time.monotonic() - started_at
    print(f"\n-- Stream encerrado ({latency:.1f}s) --")
    print(f"chars output: {len(output_text)}")
    print(f"tool calls:   {len(tool_uses)} ({', '.join(tool_uses) if tool_uses else 'nenhuma'})")

    # 5. session.retrieve() pra usage final
    cost = Decimal("0")
    status_final = None
    usage = None
    try:
        final = anthropic_client.beta.sessions.retrieve(anth_session.id)
        usage = getattr(final, "usage", None)
        status_final = getattr(final, "status", None)
    except Exception as exc:
        logger.warning("session.retrieve falhou: %s", exc)

    # 6. Grava ExternalApiCall com usage agregado
    if usage is not None:
        async with session_scope() as session:
            cost = await _record_usage(
                session,
                client_id=local_client.id,
                task_id=task.id,
                agent_instance_id=agent_inst.id,
                model=spec.model,
                usage=usage,
                latency_ms=int(latency * 1000),
                request_id=anth_session.id,
            )
            await session.commit()

    # 7. Cleanup leve da session na Anthropic (opcional)
    try:
        anthropic_client.beta.sessions.delete(anth_session.id)
    except Exception:
        pass

    # 8. (FUTURO) Hook de Dreaming pós-task — consolida insights desta
    # session no memory_store da squad.
    #
    # Pré-requisitos pra ativar:
    #   - Access ao research preview Dreaming (request form Anthropic).
    #   - Memory_store ativo no spec (ex: spec.memory_store_id).
    #   - Decisão de cadência (toda task? lote diário? threshold N
    #     tasks?). Recomendado: lote diário pra economizar.
    #   - Tabela DB ``dream_jobs`` registrando id, status, sessions,
    #     output_memory_store_id (alembic migration pendente).
    #
    # Quando ativar, descomentar e mover pra um worker async/cron, não
    # bloqueante no run_managed_task:
    #
    # from dev_autonomo.knowledge import dreaming
    # if spec.memory_store_id and not error:
    #     dream_result = dreaming.consolidate(
    #         memory_store_id=spec.memory_store_id,
    #         session_ids=[anth_session.id],  # ou lote acumulado
    #         instructions="Foco em padroes reutilizaveis pra proximos runs.",
    #         model="claude-sonnet-4-6",
    #     )
    #     # Gravar dream_result em dream_jobs, promover output_memory_store_id
    #     # se status == "completed".

    print("\n" + "=" * 70)
    print("RESULTADO")
    print("=" * 70)
    print(f"completed:    {error is None and status_final == 'idle'}")
    print(f"status:       {status_final}")
    print(f"latencia:     {latency:.1f}s")
    print(f"tool calls:   {len(tool_uses)}")
    print(f"custo:        US$ {cost:.4f}")
    if error:
        print(f"ERRO:         {error}")

    completed = error is None and status_final == "idle"

    input_tokens = getattr(usage, "input_tokens", 0) if usage else 0
    output_tokens = getattr(usage, "output_tokens", 0) if usage else 0
    cache_read = getattr(usage, "cache_read_input_tokens", 0) if usage else 0
    cache_creation_obj = getattr(usage, "cache_creation", None) if usage else None
    cache_creation = (
        (getattr(cache_creation_obj, "ephemeral_5m_input_tokens", 0) or 0)
        + (getattr(cache_creation_obj, "ephemeral_1h_input_tokens", 0) or 0)
    ) if cache_creation_obj else 0

    return ManagedRunResult(
        completed=completed,
        session_id=anth_session.id,
        tool_calls=tool_uses,
        output_text=output_text,
        latency_seconds=latency,
        cost_usd=cost,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_creation_tokens=cache_creation,
        cache_read_tokens=cache_read,
        status_final=status_final,
        error=error,
    )
