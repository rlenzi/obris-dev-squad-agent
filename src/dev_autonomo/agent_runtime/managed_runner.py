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
from dev_autonomo.common.enums import (
    ApiCallKind,
    ApiProvider,
    DreamJobStatus,
    OutcomeStatus,
)
from dev_autonomo.config import get_settings
from dev_autonomo.db.models import (
    AgentInstance,
    Client,
    DreamJob,
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

    # Resources mountados no container da session. Cada dict no formato
    # aceito por sessions.create(resources=[...]):
    #   {"type": "file", "file_id": "...", "mount_path": "/mnt/secrets/jira.env"}
    #   {"type": "github_repository", "url": "...", "authorization_token": "...",
    #    "checkout": {"type": "branch", "name": "main"}, "mount_path": "/mnt/repo"}
    #   {"type": "memory_store", "memory_store_id": "...", "access": "read_write"}
    resources: list[dict[str, Any]] = field(default_factory=list)

    # Outcome opcional (Anthropic grader). Quando set, dispara
    # user.define_outcome ANTES do user.message no stream.
    # Formato: {"description": str, "rubric_text": str, "max_iterations": int}
    outcome: dict[str, Any] | None = None

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
    outcome_verdict: str | None = None
    outcome_iterations: int = 0
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
    outcome: dict[str, Any] | None = None,
) -> tuple[str, list[str], str | None, int, list[dict[str, Any]]]:
    """Envia user.message e processa stream ate session.status_idle.

    Retorna (output_text, tool_names, outcome_verdict, outcome_iterations,
    spawned_threads). Cada thread eh dict {agent_name, agent_id, thread_id}.

    Se ``outcome`` for fornecido, envia user.define_outcome ANTES do
    user.message — ativa o grader independente da Anthropic.
    """
    tool_uses: list[str] = []
    output_parts: list[str] = []
    outcome_verdict: str | None = None
    outcome_iterations: int = 0
    spawned_threads: list[dict[str, Any]] = []

    with client.beta.sessions.events.stream(session_id) as stream:
        if outcome:
            client.beta.sessions.events.send(
                session_id,
                events=[{
                    "type": "user.define_outcome",
                    "description": outcome["description"],
                    "rubric": {"type": "text", "content": outcome["rubric_text"]},
                    "max_iterations": outcome.get("max_iterations", 3),
                }],
            )
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
                agent_name = getattr(event, "agent_name", None) or getattr(event, "agent_id", "?")
                thread_id = getattr(event, "thread_id", None) or getattr(event, "id", None)
                agent_id_ref = getattr(event, "agent_id", None)
                spawned_threads.append({
                    "agent_name": str(agent_name),
                    "agent_id": str(agent_id_ref) if agent_id_ref else None,
                    "thread_id": str(thread_id) if thread_id else None,
                })
                logger.info(
                    "session.thread_created: agent=%s thread_id=%s",
                    agent_name, thread_id,
                )
            elif etype and "outcome_evaluation" in etype:
                # Captura iteration count e verdict final do grader.
                iteration = getattr(event, "iteration", None)
                if isinstance(iteration, int):
                    outcome_iterations = max(outcome_iterations, iteration + 1)
                result = getattr(event, "result", None)
                if result is not None:
                    outcome_verdict = result
                logger.info(
                    "outcome_evaluation: %s iter=%s result=%s",
                    etype, iteration, result,
                )
            elif etype == "session.status_idle":
                break
    return (
        "".join(output_parts), tool_uses,
        outcome_verdict, outcome_iterations, spawned_threads,
    )


async def _persist_thread_as_child_task(
    session: AsyncSession,
    *,
    parent_task: Task,
    thread_info: dict[str, Any],
    child_index: int,
) -> None:
    """Cria uma Task filha representando uma thread spawnada pelo coordinator.

    Idempotente por (parent_task_id, anthropic_session_id=thread_id):
    se ja existe Task filha com mesmo thread_id, nao duplica.
    """
    thread_id = thread_info.get("thread_id")
    agent_name = thread_info.get("agent_name") or "?"

    if thread_id:
        existing = (
            await session.execute(
                select(Task).where(
                    Task.parent_task_id == parent_task.id,
                    Task.anthropic_session_id == thread_id,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return

    pseudo_key = (
        f"{parent_task.jira_issue_key}.thread-{child_index}"
        if parent_task.jira_issue_key
        else f"thread-{child_index}"
    )
    child = Task(
        client_id=parent_task.client_id,
        squad_id=parent_task.squad_id,
        jira_workspace_url=parent_task.jira_workspace_url,
        jira_issue_key=pseudo_key,
        title=f"Thread {child_index}: {agent_name}",
        parent_task_id=parent_task.id,
        anthropic_session_id=thread_id,
    )
    session.add(child)
    await session.flush()
    logger.info(
        "thread persistida como Task filha id=%s parent=%s thread_id=%s",
        child.id, parent_task.id, thread_id,
    )


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
        session_kwargs: dict[str, Any] = {
            "agent": agent_id,
            "environment_id": env_id,
            "title": f"{issue_key} - {agent_inst.name}",
        }
        if spec.resources:
            session_kwargs["resources"] = spec.resources
        anth_session = anthropic_client.beta.sessions.create(**session_kwargs)
        print(f"  session_id   = {anth_session.id}")

        # Persiste session_id como coluna queryable + payload legacy.
        task.anthropic_session_id = anth_session.id
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
    outcome_verdict: str | None = None
    outcome_iterations: int = 0
    spawned_threads: list[dict[str, Any]] = []
    try:
        (
            output_text, tool_uses,
            outcome_verdict, outcome_iterations, spawned_threads,
        ) = _stream_events(
            anthropic_client, anth_session.id, user_message, spec.outcome,
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

    # 6. Grava ExternalApiCall com usage agregado + persiste outcome
    async with session_scope() as session:
        if usage is not None:
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
        # Persiste outcome na Task se foi definido
        if spec.outcome:
            task_db = await session.get(Task, task.id)
            if task_db is not None:
                if outcome_verdict == "satisfied":
                    task_db.outcome_status = OutcomeStatus.SATISFIED
                elif outcome_verdict in ("failed", "unsatisfied"):
                    task_db.outcome_status = OutcomeStatus.FAILED
                else:
                    task_db.outcome_status = OutcomeStatus.PENDING
                task_db.outcome_iterations = outcome_iterations
                task_db.outcome_rubric_ref = spec.outcome.get("rubric_ref")

        # Persiste threads spawnadas pelo coordinator como Tasks filhas.
        # parent_task_id aponta pra task pai (coordinator).
        # anthropic_session_id na filha = thread_id (subsession).
        for idx, thread_info in enumerate(spawned_threads, start=1):
            await _persist_thread_as_child_task(
                session,
                parent_task=task,
                thread_info=thread_info,
                child_index=idx,
            )

        await session.commit()

    # 7. Cleanup leve da session na Anthropic (opcional)
    try:
        anthropic_client.beta.sessions.delete(anth_session.id)
    except Exception:
        pass

    completed = error is None and status_final == "idle"

    # 8. Hook de Dreaming pós-task (Bloco H).
    # Sempre registra DreamJob (CANDIDATE se flag off, RUNNING se on).
    # Quando o research preview Anthropic for liberado, basta setar
    # DREAMING_ENABLED=true no env — sem deploy de código.
    await _post_task_dream_hook(
        spec=spec,
        task_id=task.id,
        client_id=local_client.id,
        squad_id=squad.id,
        anth_session_id=anth_session.id,
        completed_ok=completed,
    )

    print("\n" + "=" * 70)
    print("RESULTADO")
    print("=" * 70)
    print(f"completed:    {completed}")
    print(f"status:       {status_final}")
    print(f"latencia:     {latency:.1f}s")
    print(f"tool calls:   {len(tool_uses)}")
    print(f"custo:        US$ {cost:.4f}")
    if error:
        print(f"ERRO:         {error}")

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
        outcome_verdict=outcome_verdict,
        outcome_iterations=outcome_iterations,
        error=error,
    )


# ---------------------------------------------------------------------------
# Dreaming hook pós-task (Bloco H)
# ---------------------------------------------------------------------------


_DEFAULT_DREAM_INSTRUCTIONS = (
    "Foco em padrões reutilizáveis pra próximos runs desta squad: "
    "convenções de código, decisões arquiteturais, armadilhas evitadas. "
    "Ignorar contexto efêmero (ids, paths temporários, timestamps)."
)


async def _post_task_dream_hook(
    *,
    spec: ManagedTaskSpec,
    task_id: UUID,
    client_id: UUID,
    squad_id: UUID,
    anth_session_id: str,
    completed_ok: bool,
) -> None:
    """Registra DreamJob pós-task. Bloco H do roadmap stack-knowledge.

    Sempre cria a linha em ``dream_jobs`` pra visibilidade do que seria
    consolidado (status CANDIDATE quando flag off ou access faltando).
    Quando ``DREAMING_ENABLED=True``, dispara consolidação em background
    via ``asyncio.create_task`` — não bloqueia o retorno da task.

    Sem memory_store no spec.resources, hook é no-op.
    Task que falhou, hook é no-op (não vale consolidar lixo).
    """
    if not completed_ok:
        return

    memory_store_id: str | None = None
    for resource in spec.resources:
        if resource.get("type") == "memory_store":
            memory_store_id = resource.get("memory_store_id")
            break

    if not memory_store_id:
        return

    settings = get_settings()
    model = settings.DREAMING_MODEL
    instructions = _DEFAULT_DREAM_INSTRUCTIONS

    async with session_scope() as session:
        dream_job = DreamJob(
            client_id=client_id,
            squad_id=squad_id,
            task_id=task_id,
            memory_store_id=memory_store_id,
            session_ids=[anth_session_id],
            model=model,
            instructions=instructions,
            status=DreamJobStatus.CANDIDATE,
        )
        session.add(dream_job)
        await session.flush()
        dream_job_id = dream_job.id
        await session.commit()

    logger.info(
        "dream_job criado id=%s status=candidate memory_store=%s session=%s",
        dream_job_id, memory_store_id, anth_session_id,
    )

    if not settings.DREAMING_ENABLED:
        return

    import asyncio
    asyncio.create_task(
        _execute_dream_job(dream_job_id, settings.DREAMING_ALLOW_RAW_HTTP)
    )


async def _execute_dream_job(dream_job_id: UUID, allow_raw_http: bool) -> None:
    """Executa consolidação Dreaming em background.

    ``dreaming.consolidate`` é síncrono (polling). Roda em thread separada
    via ``asyncio.to_thread`` pra não bloquear o event loop. Resultado vira
    update em ``dream_jobs``.
    """
    import asyncio

    from dev_autonomo.knowledge import dreaming

    async with session_scope() as session:
        dj = await session.get(DreamJob, dream_job_id)
        if dj is None:
            logger.warning("dream_job %s nao encontrado", dream_job_id)
            return
        memory_store_id = dj.memory_store_id
        session_ids = list(dj.session_ids)
        model = dj.model
        instructions = dj.instructions
        dj.status = DreamJobStatus.RUNNING
        await session.commit()

    try:
        result = await asyncio.to_thread(
            dreaming.consolidate,
            memory_store_id=memory_store_id,
            session_ids=session_ids,
            instructions=instructions,
            model=model,
            allow_raw_http=allow_raw_http,
        )
    except Exception as exc:
        logger.exception("dream_job %s falhou em consolidate", dream_job_id)
        async with session_scope() as session:
            dj = await session.get(DreamJob, dream_job_id)
            if dj is not None:
                dj.status = DreamJobStatus.FAILED
                dj.error = f"{type(exc).__name__}: {exc}"
                await session.commit()
        return

    status_map = {
        "completed": DreamJobStatus.COMPLETED,
        "failed": DreamJobStatus.FAILED,
        "skipped_unavailable": DreamJobStatus.SKIPPED_UNAVAILABLE,
        "running": DreamJobStatus.RUNNING,
    }
    final_status = status_map.get(result.status, DreamJobStatus.FAILED)

    async with session_scope() as session:
        dj = await session.get(DreamJob, dream_job_id)
        if dj is None:
            return
        dj.status = final_status
        dj.dream_id = result.dream_id
        dj.output_memory_store_id = result.output_memory_store_id
        dj.input_tokens = result.input_tokens
        dj.output_tokens = result.output_tokens
        dj.cost_usd = result.cost_usd
        dj.error = result.error
        await session.commit()

    logger.info(
        "dream_job %s finalizado status=%s output_store=%s cost=$%s",
        dream_job_id, final_status.value,
        result.output_memory_store_id, result.cost_usd,
    )
