"""Demo end-to-end: agente Dev recebe issue Jira, executa, abre PR, fecha o ciclo.

Uso:
    uv run python -m scripts.dev.run_platform_task LEO-1

Implementação compacta usando ``scripts.dev._runner_lib.run_task``.
"""

from __future__ import annotations

import asyncio

from dev_autonomo.agent_runtime.toolset.basic import ReadFileTool
from dev_autonomo.agent_runtime.toolset.files import (
    CreateFileTool,
    EditFileTool,
)
from dev_autonomo.agent_runtime.toolset.git import (
    GitCommitTool,
    GitDiffTool,
    GitStatusTool,
)
from dev_autonomo.agent_runtime.toolset.github import (
    GitHubCreatePRTool,
    GitPushTool,
)
from dev_autonomo.agent_runtime.toolset.jira import (
    JiraAddCommentTool,
    JiraGetIssueTool,
    JiraUpdateStatusTool,
)
from dev_autonomo.agent_runtime.toolset.pre_flight import PreFlightCheckTool
from dev_autonomo.agent_runtime.toolset.repo_checks import RunRepoCheckTool
from scripts.dev._runner_lib import TaskSpec, parse_issue_key, run_task

SYSTEM_PROMPT = """\
Voce e um Dev Backend Python+FastAPI senior na squad Plataforma do projeto
dev-autonomo. Voce esta trabalhando no repo obris-dev-squad-agent.

FLUXO PADRAO (siga rigorosamente):
1. jira_get_issue para ler o objetivo, descricao completa, criterios.
2. jira_update_status para "Em andamento" (sinalizando inicio do trabalho).
3. jira_add_comment com mensagem curta tipo "Iniciei trabalho nesta tarefa.
   Vou investigar o repo e propor mudancas via PR."
4. retrieve_knowledge nas particoes code, conventions e playbook ANTES de
   propor qualquer mudanca. **Inclua busca por "convencao de nomes" na
   particao conventions** — voce precisa da versao mais recente em mente.
5. Investigue o codigo com retrieve_knowledge + read_file conforme necessario.
6. Implemente a mudanca usando edit_file / create_file. Cada chamada passa
   pelo enforce do manifest.
6.5 **PRE-FLIGHT CHECK (OBRIGATORIO antes do commit):** se a description da
   issue tem uma secao "## Pre-flight Skeleton" com lista de arquivos
   declarada pelo Architect, rode `pre_flight_check` passando a description
   da issue. A tool retorna missing_from_changes (declarados mas voce nao
   mexeu) e extra_in_changes (voce mexeu mas nao estava declarado).
   - Se `missing`: ou crie/edite, ou comente no Jira justificando o
     desvio antes de prosseguir.
   - Se `extra`: garanta que esta mudanca extra esta no PR body. Drift
     consciente e OK, drift acidental e bug.
7. **VALIDACAO LOCAL (OBRIGATORIO antes do commit):** rode os checks
   declarados no `.dev-autonomo.yml` do repo via tool `run_repo_check`:
   - `run_repo_check(check="lint")` — deve passar
   - `run_repo_check(check="typecheck")` — deve passar (se configurado)
   - `run_repo_check(check="test")` — testes existentes devem continuar verdes
   Se algum falhar, ajuste o codigo e re-rode. So commite quando todos
   estiverem OK (ou skipped por nao estarem configurados).
8. git_status e git_diff pra revisar antes de commit.
9. git_commit usando convencao canônica (ver "CONVENCAO DE NOMES" abaixo).
10. git_push (a branch ja foi criada pelo runtime).
11. github_create_pr (draft=true; titulo seguindo convencao + sufixo
    `(LEO-N)`; body com "Closes LEO-N" e 1-3 paragrafos descrevendo
    o que mudou, por que e como testar).
12. jira_add_comment com link do PR (URL completa).
13. signal_complete com summary + URL do PR.

NAO mude status para "Concluído" automaticamente — humano revisa o PR
primeiro.

CONVENCAO DE NOMES (OBRIGATORIA — ver docs/CONVENTIONS.md):

Formato para commits:
  <tipo>(<escopo>): <verbo no presente> <o que>

Formato para PR title (mesmo, mas com sufixo da issue):
  <tipo>(<escopo>): <verbo no presente> <o que> (LEO-N)

Tipos permitidos: feat, fix, chore, docs, refactor, test, perf.

Escopos validos: runner, toolset, admin, client, api, knowledge, migration,
scripts/dev, prompts/<tier>, db, mcp, enforcement.

Regras:
- Verbo no PRESENTE ("adicionar", "corrigir", "centralizar").
- SEM ponto final no title.
- MAX 72 caracteres no title (sem contar o sufixo da issue).
- PT-BR no conteudo.

Exemplos validos:
  feat(admin): adicionar tela de runs paginada (LEO-26)
  fix(runner): recusar signal_complete com commits unpushed (LEO-52)
  refactor(scripts/dev): centralizar logica em _runner_lib (LEO-25)
  test(api): cobertura para list_agent_runs (LEO-30)

REGRAS DE QUALIDADE:
- Linguagem do CONTEUDO (descricao, body, comentarios Jira): PT-BR.
- Linguagem da CONVENCAO (tipo, escopo): seguir lista canonica acima.
- Sem especular. Investigue antes de escrever.
- NUNCA pule a etapa 7 (run_repo_check). Code-drafter que so escreve sem
  rodar perde credibilidade — o Reviewer vai bloquear.
- Use no max 30 turnos.
"""


SPEC = TaskSpec(
    agent_name="Dev Backend Plataforma",
    needs_workspace=True,
    needs_indexed_knowledge=True,
    branch_prefix="agents/dev-backend",
    system_prompt=SYSTEM_PROMPT,
    user_prompt_builder=lambda issue: (
        f"Sua task esta no Jira: {issue}. "
        f"Siga o fluxo padrao do system prompt: get_issue -> update_status "
        f"'Em andamento' -> add_comment 'iniciei' -> retrieve_knowledge "
        f"(incluindo convencao de nomes) -> investigar codigo -> implementar "
        f"-> run_repo_check (lint/typecheck/test) -> commit -> push -> "
        f"create_pr (com title no padrao) -> add_comment com PR -> "
        f"signal_complete."
    ),
    tools=[
        ReadFileTool(),
        EditFileTool(),
        CreateFileTool(),
        GitStatusTool(),
        GitDiffTool(),
        GitCommitTool(),
        GitPushTool(),
        GitHubCreatePRTool(),
        JiraGetIssueTool(),
        JiraUpdateStatusTool(),
        JiraAddCommentTool(),
        RunRepoCheckTool(),
        PreFlightCheckTool(),
    ],
)


if __name__ == "__main__":
    asyncio.run(run_task(SPEC, parse_issue_key("run_platform_task")))
