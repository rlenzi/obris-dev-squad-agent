"""Smoke test do Claude Managed Agents (beta, abril/2026).

Objetivo: rodar o equivalente ao nosso BA Agent (refina demanda) usando
o harness managed da Anthropic em vez do nosso `agent_runtime/worker.py`.
Comparar:
  - Linhas de código necessarias (esse arquivo vs worker.py + toolset/*)
  - Latencia (tempo do user.message ate session.status_idle)
  - Custo (tokens reportados pelo final event + session-hour)
  - Qualidade da saida (refinamento similar ao nosso?)

NAO toca DB nosso, NAO toca Jira real. Demanda passada como texto direto.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from anthropic import Anthropic

PROMPT_PATH = Path(__file__).parent.parent.parent / "prompts" / "ba" / "generic.md"

FAKE_DEMAND = """\
Demanda Jira (LEO-XX-SMOKE):

**Título:** feat(painel): mostrar última atividade de cada agente no dashboard

**Descrição:**
Hoje o painel cliente lista as squads e os agentes em cada uma, mas não dá
pra ver de cara se um agente está parado faz tempo. Queremos que cada
linha de agente mostre quando ele rodou pela última vez e qual foi o
status do último run.

(Demanda intencionalmente vaga para smoke test do BA Agent — espera-se
que o BA refine com ACs claros e identifique ambiguidades.)
"""


def main() -> None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        # Tenta pegar do settings (pydantic_settings carrega de env/config)
        try:
            from dev_autonomo.config import get_settings
            os.environ["ANTHROPIC_API_KEY"] = (
                get_settings().ANTHROPIC_API_KEY.get_secret_value()
            )
        except Exception as exc:
            print(f"erro ao pegar ANTHROPIC_API_KEY: {exc}")
            print("seta a env var manualmente: export ANTHROPIC_API_KEY=...")
            sys.exit(1)

    if not PROMPT_PATH.exists():
        print(f"prompt nao encontrado: {PROMPT_PATH}")
        sys.exit(1)

    system_prompt = PROMPT_PATH.read_text(encoding="utf-8")
    client = Anthropic()

    print("=" * 70)
    print("Smoke: BA Agent via Claude Managed Agents")
    print("=" * 70)

    # 1. Cria agente
    print("\n[1/4] Criando agente...")
    agent = client.beta.agents.create(
        name="BA Smoke (obris)",
        model="claude-sonnet-4-6",
        system=system_prompt,
        tools=[{"type": "agent_toolset_20260401"}],
    )
    print(f"  agent.id = {agent.id}")
    print(f"  version  = {agent.version}")

    # 2. Cria environment (cloud, network unrestricted)
    print("\n[2/4] Criando environment...")
    env = client.beta.environments.create(
        name=f"ba-smoke-{int(time.time())}",
        config={
            "type": "cloud",
            "networking": {"type": "unrestricted"},
        },
    )
    print(f"  environment.id = {env.id}")

    # 3. Cria session
    print("\n[3/4] Criando session...")
    session = client.beta.sessions.create(
        agent=agent.id,
        environment_id=env.id,
        title="BA smoke run",
    )
    print(f"  session.id = {session.id}")

    # 4. Stream events
    print("\n[4/4] Streaming events...")
    start = time.monotonic()
    tool_uses: list[str] = []
    full_message_parts: list[str] = []

    with client.beta.sessions.events.stream(session.id) as stream:
        client.beta.sessions.events.send(
            session.id,
            events=[
                {
                    "type": "user.message",
                    "content": [{"type": "text", "text": FAKE_DEMAND}],
                }
            ],
        )

        for event in stream:
            etype = getattr(event, "type", None)
            if etype == "agent.message":
                for block in getattr(event, "content", []):
                    text = getattr(block, "text", "")
                    if text:
                        print(text, end="", flush=True)
                        full_message_parts.append(text)
            elif etype == "agent.tool_use":
                tool_name = getattr(event, "name", "?")
                tool_uses.append(tool_name)
                print(f"\n[tool: {tool_name}]\n", flush=True)
            elif etype == "session.status_idle":
                print("\n\n[session idle — agente terminou]")
                break

    elapsed = time.monotonic() - start

    print("\n" + "=" * 70)
    print("RESULTADO")
    print("=" * 70)
    print(f"latencia       : {elapsed:.1f}s")
    print(f"tool calls     : {len(tool_uses)}  ({', '.join(tool_uses) if tool_uses else 'nenhum'})")
    print(f"chars saida    : {sum(len(p) for p in full_message_parts)}")

    # 5. Detalhes finais da sessao (usage)
    try:
        final = client.beta.sessions.retrieve(session.id)
        usage = getattr(final, "usage", None)
        if usage is not None:
            print(f"usage          : {usage}")
        status = getattr(final, "status", "?")
        print(f"status final   : {status}")
    except Exception as exc:
        print(f"(sem detalhes finais: {exc})")

    # Cleanup leve (não bloqueia, beta pode não suportar)
    try:
        client.beta.sessions.delete(session.id)
        print("session deletada.")
    except Exception:
        pass


if __name__ == "__main__":
    main()
