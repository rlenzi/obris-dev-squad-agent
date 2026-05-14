# dev-autonomo (obris)

Plataforma multi-tenant de **agentes autônomos de desenvolvimento** —
Claude API + RAG + manifest enforcement + worktree manager. Cada cliente
tem squads com agentes (BA, Architect, Dev, Reviewer, Onboarding Analyst)
que cooperam pra entregar features completas a partir de demandas no
Jira do cliente.

> Status: Fase 1 fechada (agentes codando + painéis admin/cliente).
> Próximo: Fase 2 (notebook pessoal por agente + orquestração cloud).

---

## Visão de 30 segundos

```
Jira (issue)               GitHub (PR)
   │                            ▲
   ▼                            │
[BA] → [Architect] → [Dev] → [Reviewer] ⟳ [Dev (address-review)]
                       │
                  Knowledge Hub
                  (Qdrant + Voyage embeddings)
                       │
                Manifest Enforcement
                  (5 checks por tool call)
                       │
                Cost tracking + billing
                  (token cost + markup por cliente)
```

Cada agente é um *skill template* (prompt + model + tools + knowledge
partitions). Cada tenant pode customizar templates por squad. Custos são
medidos por run (tokens × preço Anthropic × markup do plano) e
faturados via billing plan.

---

## Setup local (primeira vez)

Pré-requisitos: Docker, `uv`, Node 20+.

```bash
# 1. Sobe infra
cd infra && docker compose up -d && cd ..

# 2. Roda migrations
uv run alembic upgrade head

# 3. Seed (cria client `dev-autonomo`, user admin, squad Plataforma, skill_templates)
uv run python -m scripts.dev.seed_dev_data

# 4. Sobe API
uv run uvicorn dev_autonomo.control_plane.app:app --reload

# 5. Sobe painéis
cd web/admin && npm install && npm run dev   # localhost:5173
cd web/client && npm install && npm run dev  # localhost:5174
```

Login default (após `seed_dev_data`): ver `scripts/dev/seed_dev_data.py`.

### Variáveis de ambiente

Mínimas (vault encrypted ou env):

| Variável | Para que serve |
|---|---|
| `ANTHROPIC_API_KEY` | Chamadas Claude (agentes) |
| `VOYAGE_API_KEY` | Embeddings (knowledge hub) |
| `JIRA_TOKEN` por client | Tool jira_* — gravado no vault |
| `GITHUB_TOKEN` por client | Tool github_* — gravado no vault |
| `FERNET_KEY` | Cripta vault + JWT (gere com `openssl rand -base64 32`) |
| `JWT_SECRET` | Assina sessões do painel |

Em dev, todas exceto as duas primeiras são gravadas via `seed_dev_data`
ou pelo painel admin (rota Credentials).

---

## Rodando agentes

Cada tier tem um runner em `scripts/dev/`. Todos usam o cliente
`dev-autonomo` e squad `plataforma` por default (dogfooding).

### BA — refina demanda em ACs
```bash
uv run python -m scripts.dev.run_ba_task LEO-53
```
Saída: comentário no Jira com persona/Como/Quero/Para-que/ACs/dúvidas.
Custo típico: US$ 0,10–0,20 / 4–7 turnos.

### Architect — decompõe em sub-tasks (com Pre-flight Skeleton)
```bash
uv run python -m scripts.dev.run_architect_task LEO-53
```
Saída: 3–8 sub-tarefas Jira (`LEO-53.x`) com `## Pre-flight Skeleton`
listando arquivos a tocar. Custo típico: US$ 0,30–0,80 / 7–12 turnos.

### Dev — implementa, valida, abre PR
```bash
uv run python -m scripts.dev.run_platform_task LEO-53.1
```
Saída: branch + commits + PR draft. Chama `run_repo_check` (lint/test) e
`pre_flight_check` (drift vs skeleton) antes do commit. `signal_complete`
recusa se faltou `git_push` ou `github_create_pr`. Custo típico: US$ 1–3
/ 15–25 turnos.

### Reviewer — revisa PR
```bash
uv run python -m scripts.dev.run_reviewer_task <PR_NUMBER>
```
Saída: review APPROVE ou REQUEST_CHANGES com comentários inline. Custo
típico: US$ 0,15–0,40 / 5–10 turnos.

### Dev address-review — atende REQUEST_CHANGES
```bash
uv run python -m scripts.dev.run_dev_address_review <PR_NUMBER>
```
Lê comentários inline via `github_get_review_comments`, aplica fix na
**mesma branch** (sem PR novo), valida e empurra novos commits.

### Onboarding Analyst — analisa repo de cliente novo
```bash
uv run python -m scripts.dev.run_onboarding_analyst /caminho/do/repo
```
Saída: proposta de `.dev-autonomo.yml` + manifesto de squad + skill
templates recomendados. Não modifica o repo.

---

## Painéis web

### Admin (porta 5173)
- `/clients` — wizard de novo cliente (4 steps), lista com custo por tenant
- `/skills` — catálogo de skill templates filtráveis por tier
- `/cost` — ranking de custo + breakdown por cliente
- Squads/Agentes/Runs drill-down até timeline de chamadas Claude

### Cliente (porta 5174)
- `/dashboard` — visão consolidada da squad
- `/squads/:id` — agentes + manifest editável
- `/squads/:id/agents/:aid` — detalhe do agente + **botão "Rodar agente"**
  dispara run pelo painel (`POST /clients/:cid/agents/:aid/runs`)
- `/cost` — custo do tenant com period selector

---

## Arquitetura

```
src/dev_autonomo/
├── agent_runtime/      # Loop tool_use Claude + enforcement + worktree
│   ├── worker.py            AgentRunner (loop principal)
│   ├── enforcement.py       Manifest checks (5 dimensões)
│   ├── worktree.py          GitWorktreeManager (isolamento por run)
│   └── toolset/             basic, files, git, github, jira, repo_checks,
│                             pre_flight, repo_analyzer
├── control_plane/      # FastAPI + JWT + RBAC
│   ├── routers/             admin_*, client_*, auth, cost, skill_templates
│   ├── services/            agent_run_*, ...
│   └── schemas/             pydantic models
├── knowledge/          # RAG
│   ├── indexer.py           Indexa repos (chunks → Qdrant)
│   ├── retriever.py         Boundary filter por squad
│   └── voyage_client.py     Embeddings
├── mcp_clients/        # github_client, jira_client (puros httpx)
├── db/                 # SQLAlchemy models + Alembic
└── common/             # claude_client, credentials_store, billing, ...
```

7 dimensões de concorrência (1 agente ≠ outro): schema PG, prefix Qdrant,
prefix Redis, vhost RabbitMQ, filesystem (worktree por task), portas,
git branches. Detalhes em `docs/SANDBOX_MODES.md`.

---

## Convenções

| Tipo | Padrão |
|---|---|
| Commits / PR titles | `<tipo>(<escopo>): <verbo no presente> <o que>` (LEO-N) |
| Tipos permitidos | feat, fix, chore, docs, refactor, test, perf |
| Escopos válidos | runner, toolset, admin, client, api, knowledge, migration, scripts/dev, prompts/<tier>, db, mcp, enforcement |
| Linguagem do conteúdo | PT-BR |

Mais em `docs/CONVENTIONS.md`.

---

## Documentação

- `docs/SANDBOX_MODES.md` — 7 dimensões de concorrência + modos ephemeral/shared/external
- `docs/CONVENTIONS.md` — convenção de nomes (LEO-N)
- `docs/WEBHOOKS.md` — webhooks de reindex + Jira
- `prompts/<tier>/generic.md` — system prompts dos agentes
- `scripts/dev/README.md` — guia detalhado dos runners

---

## Status atual

- ✅ Fase 1: agentes codando + painel cliente + tudo bonito
- 🚧 Fase 2: notebook Docker por agente + orquestração cloud (AWS Fargate / GCP Cloud Run / Azure CI / SSH Docker)
- 📋 Backlog: BA→Architect→Dev→Reviewer→Dev cycle E2E validado, A2A protocol entre tiers, replay validation de onboarding
