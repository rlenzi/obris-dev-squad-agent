# Managed Agents — status da migração

Este documento registra o estado atual da migração do runtime dev-autonomo para
**Claude Managed Agents** (toolset nativo, sem MCP customizado).

Destina-se a novos colaboradores que precisam entender que o runtime antigo está
em processo de **deprecation** e onde encontrar o runner novo.

## Estado em 2026-05-14

- ✅ **Fase 0 — Smoke API:** integração básica com a API Anthropic confirmada; autenticação e chamadas simples validadas.
- ✅ **Fase 1 — `managed_runner.py` estabilizado:** runner com toolset nativo (bash, file ops, web) operacional e cobrindo o ciclo completo de execução de agente.
- ✅ **Fase 2 — BA E2E via toolset nativo:** agente BA executando fluxo completo de refinamento (leitura Jira → análise → geração de CAs → comentário) inteiramente via ferramentas nativas, sem MCP.
- 🚧 **Fase 3 — Dev E2E via toolset nativo (este PR):** agente Dev executando fluxo completo de implementação (leitura issue → branch → código → commit → PR → comentário Jira) via toolset nativo.

## Próximos passos

- **Fase 4:** Reviewer E2E via toolset nativo — agente Reviewer analisando PRs e postando parecer no GitHub/Jira sem MCP.
- **Fase 5:** Architect E2E via toolset nativo — decomposição de épicos e criação de sub-tarefas inteiramente via toolset nativo.
- **Fase 6:** Remoção do runtime legado — desativar worker.py/worktree.py baseados em MCP após validação dos agentes migrados.
- **Fase 7:** Hardening e observabilidade — logging estruturado, métricas de latência/custo por fase e alertas no painel admin.

## Arquivos de referência

| Arquivo | Descrição |
|---|---|
| [`src/dev_autonomo/agent_runtime/managed_runner.py`](../src/dev_autonomo/agent_runtime/managed_runner.py) | Runner principal do Managed Agents (Fase 1+) |
| [`prompts/ba/managed.md`](../prompts/ba/managed.md) | System prompt do agente BA no modo Managed Agents |
| [`prompts/dev/managed.md`](../prompts/dev/managed.md) | System prompt do agente Dev no modo Managed Agents |
