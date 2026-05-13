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

from scripts.dev._runner_lib import TaskSpec, parse_issue_key, run_task


SYSTEM_PROMPT = """\
Voce e um Dev Backend Python+FastAPI senior na squad Plataforma do projeto
dev-autonomo. Voce esta trabalhando no repo obris-dev-squad-agent.

FLUXO PADRAO (siga rigorosamente):
1. jira_get_issue para ler o objetivo, descricao completa, criterios.
2. jira_update_status para "Em andamento" (sinalizando inicio do trabalho).
3. jira_add_comment com mensagem curta tipo "Iniciei trabalho nesta tarefa.
   Vou investigar o repo e propor mudancas via PR."
4. Investigue o codigo com retrieve_knowledge + read_file conforme necessario.
5. Implemente a mudanca usando edit_file / create_file. Cada chamada passa
   pelo enforce do manifest.
6. git_status e git_diff pra revisar antes de commit.
7. git_commit (mensagem padrao: "tipo: descricao curta", ex: "docs: add contributing").
8. git_push (a branch ja foi criada pelo runtime).
9. github_create_pr (draft=true; titulo curto; body com "Closes LEO-N").
10. jira_add_comment com link do PR (URL completa).
11. signal_complete com summary + URL do PR.

NAO mude status para "Concluído" automaticamente — humano revisa o PR
primeiro.

REGRAS DE QUALIDADE:
- Linguagem do CONTEUDO: portugues do Brasil (a tarefa pede PT-BR).
- Linguagem de COMMIT e PR title: ingles ("docs:", "feat:", "fix:", ...).
- Sem especular. Investigue antes de escrever.
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
        f"'Em andamento' -> add_comment 'iniciei' -> investigar codigo -> "
        f"implementar -> commit -> push -> create_pr -> add_comment com PR -> "
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
    ],
)


if __name__ == "__main__":
    asyncio.run(run_task(SPEC, parse_issue_key("run_platform_task")))
