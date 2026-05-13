# Convenções de nomes — dev-autonomo

Convenção canônica para títulos de issues Jira, PRs do GitHub e mensagens de
commit. Vale para **humanos e agentes** (Architect, Dev, Reviewer, BA).

A convenção segue [Conventional Commits](https://www.conventionalcommits.org/)
adaptada ao projeto.

## Formato

### Issue Jira (campo `summary`)

```
<tipo>(<escopo>): <verbo no presente> <o que>
```

### Pull Request (title)

```
<tipo>(<escopo>): <verbo no presente> <o que> (LEO-N)
```

A diferença é o sufixo `(LEO-N)` referenciando a issue Jira que originou o
trabalho. GitHub adiciona `(#NUM_PR)` automaticamente após o merge — não
incluir manualmente.

### Commits

Mesma convenção do PR, mas **sem** o sufixo `(LEO-N)`:

```
<tipo>(<escopo>): <verbo no presente> <o que>
```

## Tipos permitidos

| Tipo | Quando usar |
|---|---|
| `feat` | Funcionalidade nova visível ao usuário ou aos agentes |
| `fix` | Correção de bug que afeta comportamento |
| `chore` | Manutenção sem mudança funcional (renomear, mover, format) |
| `docs` | Apenas documentação (README, MD, docstrings, comentários) |
| `refactor` | Reorganização de código sem mudança de comportamento externo |
| `test` | Adicionar/atualizar testes — sem código de produção mudando |
| `perf` | Otimização de performance |

## Escopos permitidos

Lista controlada — adicione novos escopos via PR atualizando esta lista.

| Escopo | O que abrange |
|---|---|
| `runner` | `src/dev_autonomo/agent_runtime/` (worker, worktree, context) |
| `toolset` | Tools dos agentes (`toolset/basic.py`, `toolset/github.py`, etc.) |
| `admin` | `web/admin/` — painel admin React |
| `client` | `web/client/` — painel cliente React (a criar) |
| `api` | `src/dev_autonomo/control_plane/` — FastAPI (routers, services, schemas) |
| `knowledge` | `src/dev_autonomo/knowledge/` — indexer, retriever, reindex worker |
| `migration` | `alembic/versions/` |
| `scripts/dev` | `scripts/dev/` — entrypoints de demo e seed |
| `prompts/<tier>` | `prompts/architect/`, `prompts/dev/`, `prompts/reviewer/`, etc. |
| `db` | `src/dev_autonomo/db/` — models, migrations, session |
| `mcp` | `src/dev_autonomo/mcp_clients/` (github_client, jira_client) |
| `enforcement` | Manifest enforcer, auth, defesa em camadas |

Quando uma mudança toca **2+ escopos**, escolha o **principal**; ou crie tarefa
separada por escopo (preferido — escopo único facilita revisão).

## Regras do `<verbo + o que>`

- **Verbo no presente do indicativo** ("adicionar", "corrigir", "centralizar").
- **Sem ponto final.**
- **Máximo 72 caracteres** no total (linha do title) — fica legível na lista do
  Jira/GitHub sem truncar.
- **PT-BR** no conteúdo da descrição/title (este é um projeto bilíngue: code
  em inglês, prosa em português).

## Exemplos válidos

```
feat(admin): adicionar tela de runs paginada com drill-down
fix(runner): recusar signal_complete com commits unpushed
refactor(scripts/dev): centralizar lógica em _runner_lib
docs(prompts/architect): documentar critérios de decomposição v1
test(api): cobertura para list_agent_runs
chore(migration): renomear enum reviewer para REVIEWER
perf(knowledge): cache de embeddings do retriever
```

## Exemplos INVÁLIDOS (e como corrigir)

| ❌ Errado | ✅ Correto | Por quê |
|---|---|---|
| `Tela de runs no admin` | `feat(admin): adicionar tela de runs no admin` | Falta tipo+escopo |
| `feat: nova feature` | `feat(admin): adicionar tela de runs` | Sem escopo, descrição vaga |
| `feat(admin): tela de runs.` | `feat(admin): adicionar tela de runs` | Verbo + sem ponto final |
| `feat(admin): Adicionar tela de runs no admin` | `feat(admin): adicionar tela de runs` | Capitalização + redundância |
| `feat(admin/api/db): mudanças variadas` | dividir em 2-3 issues por escopo | Múltiplos escopos = decompor |

## Decomposição por Architect

Quando o Architect Agent decompõe uma demanda grande em sub-tarefas, **cada
sub-tarefa segue a convenção integral**. Sub-tarefas em geral usam escopos
distintos (uma toca schema, outra service, outra router), e isso é desejável —
cada PR fica focado.

## Validação

Hoje a convenção é **soft** — aplicada via prompt nos agentes. No futuro vamos
adicionar validação no tool `jira_create_subtask` e `github_create_pr` (regex
no title) e rejeitar fora do padrão.

## Onde os agentes consultam isto

Este arquivo é indexado no Knowledge Hub na partição `conventions:{squad}`.
Architect, Dev e Reviewer consultam via:

```python
retrieve_knowledge(query="convenção de nomes", partition="conventions")
```

Mantenha este arquivo como **fonte única da verdade**. Toda mudança na
convenção entra aqui primeiro, depois reflete nos prompts.
