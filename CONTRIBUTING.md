# Contribuindo para o dev-autonomo

Obrigado por querer contribuir! Este guia cobre tudo o que você precisa para rodar o projeto localmente e enviar alterações seguindo os padrões da plataforma.

---

## Sumário

1. [Pré-requisitos](#pré-requisitos)
2. [Subindo a infra local](#subindo-a-infra-local)
3. [Rodando o backend](#rodando-o-backend)
4. [Rodando o painel admin](#rodando-o-painel-admin)
5. [Rodando os testes](#rodando-os-testes)
6. [Estrutura do repositório](#estrutura-do-repositório)
7. [Padrão de commits](#padrão-de-commits)
8. [Abrindo um Pull Request](#abrindo-um-pull-request)

---

## Pré-requisitos

| Ferramenta | Versão mínima | Observação |
|---|---|---|
| Python | 3.11 | Gerenciado via `uv` |
| [uv](https://docs.astral.sh/uv/) | latest | Substitui pip + venv |
| Docker + Docker Compose | v2 | Para a infra local |
| Node.js | 20 LTS | Para o painel admin |
| npm | 10 | Incluído no Node.js 20 |

---

## Subindo a infra local

A infra local inclui **Postgres + pgvector**, **Redis**, **RabbitMQ** e **Qdrant**. Tudo é orquestrado pelo `docker-compose.yml` em `infra/`.

### 1. Configure as variáveis de ambiente

Crie o arquivo `secrets/.env` na raiz do repositório (dois níveis acima de `infra/`). Exemplo mínimo:

```env
POSTGRES_USER=dev_autonomo
POSTGRES_PASSWORD=dev_autonomo
POSTGRES_DB=dev_autonomo
POSTGRES_PORT=5432

REDIS_PORT=6379

RABBITMQ_USER=dev_autonomo
RABBITMQ_PASSWORD=dev_autonomo
RABBITMQ_PORT=5672

QDRANT_PORT=6333
```

### 2. Suba os containers

```bash
cd infra
make up
```

O Makefile é um atalho para `docker compose --env-file ../../secrets/.env -f docker-compose.yml`. Os comandos disponíveis são:

| Comando | Descrição |
|---|---|
| `make up` | Sobe todos os serviços em background |
| `make down` | Para e remove os containers |
| `make logs` | Acompanha os logs em tempo real |
| `make ps` | Lista os containers e seus status |
| `make restart` | Reinicia todos os serviços |
| `make psql` | Abre o cliente psql no container |
| `make redis-cli` | Abre o Redis CLI no container |
| `make rabbitmq-ui` | Informa a URL do painel do RabbitMQ (porta 15672) |
| `make clean` | Para os containers **e destrói os volumes** |

---

## Rodando o backend

O backend é uma API **FastAPI** gerenciada com **`uv`**.

### 1. Instale as dependências

```bash
uv sync
```

### 2. Configure as variáveis de ambiente do backend

Copie o exemplo de configuração e ajuste conforme necessário:

```bash
cp .env.example .env
```

> **Dica:** se o arquivo `.env.example` ainda não existir, basta criar um `.env` na raiz com as mesmas variáveis do `secrets/.env` acrescidas das chaves de API (`ANTHROPIC_API_KEY`, `VOYAGE_API_KEY`, etc.).

### 3. Aplique as migrações do banco

```bash
uv run alembic upgrade head
```

### 4. Inicie o servidor de desenvolvimento

```bash
uv run uvicorn dev_autonomo.control_plane.app:app --reload --host 0.0.0.0 --port 8000
```

A API ficará disponível em `http://localhost:8000`. A documentação interativa pode ser acessada em `http://localhost:8000/docs`.

---

## Rodando o painel admin

O painel admin é uma SPA **React + Vite** localizada em `web/admin/`.

### 1. Instale as dependências

```bash
cd web/admin
npm install
```

### 2. Inicie o servidor de desenvolvimento

```bash
npm run dev
```

O painel ficará disponível em `http://localhost:5173` (porta padrão do Vite).

---

## Rodando os testes

Os testes de integração exigem que a infra local esteja rodando (`make up`).

> **Atenção:** os testes consomem tokens das APIs externas (Voyage, Anthropic). Execute com consciência em ambientes que possuam limites de cota.

```bash
uv run pytest tests/integration
```

Para rodar um arquivo específico:

```bash
uv run pytest tests/integration/test_indexer.py -v
```

Para rodar todos os testes (unitários + integração):

```bash
uv run pytest
```

---

## Estrutura do repositório

```
obris-dev-squad-agent/
├── src/dev_autonomo/
│   ├── control_plane/     # API FastAPI multi-tenant (routers, schemas, webhooks)
│   ├── knowledge/         # Knowledge Hub (indexer, retriever, playbook miner, Qdrant/Voyage clients)
│   ├── agent_runtime/     # Workers que executam tasks dos agentes
│   ├── mcp_clients/       # Wrappers de MCP (Jira, GitHub)
│   ├── workflow/          # Orquestração BA → Architect → Devs
│   ├── db/                # Models SQLAlchemy + sessões assíncronas
│   └── common/            # Utilitários compartilhados
├── web/
│   └── admin/             # Painel admin (React + Vite + Tailwind)
├── infra/
│   ├── docker-compose.yml # Serviços de infra local
│   └── Makefile           # Atalhos para docker compose
├── tests/
│   └── integration/       # Testes de integração end-to-end
├── scripts/
│   └── dev/               # Scripts auxiliares (seed, demo, etc.)
├── pyproject.toml         # Dependências e configuração do projeto Python
└── README.md
```

---

## Padrão de commits

As mensagens de commit devem ser escritas em **inglês**, seguindo o formato:

```
<tipo>: <descrição curta em inglês> (máx. 72 chars na linha 1)

[corpo opcional, separado por linha em branco, explicando o "por quê"]
```

### Tipos aceitos

| Tipo | Quando usar |
|---|---|
| `feat` | Nova funcionalidade |
| `fix` | Correção de bug |
| `docs` | Alterações apenas em documentação |
| `refactor` | Refatoração sem mudança de comportamento |
| `test` | Adição ou correção de testes |
| `chore` | Tarefas de manutenção (deps, configs, CI) |
| `perf` | Melhoria de performance |

### Exemplos

```bash
# ✅ Correto
git commit -m "feat: add idempotency key to /payments endpoint"
git commit -m "fix: prevent duplicate squad creation on race condition"
git commit -m "docs: add contributing guide"

# ❌ Errado
git commit -m "adicionei endpoint de pagamentos"
git commit -m "WIP"
git commit -m "fix bug"
```

---

## Abrindo um Pull Request

### Nomeação de branches

Use o padrão:

```
agents/<tier>/<slug>
```

Exemplos:
- `agents/dev/add-payments-idempotency`
- `agents/architect/refactor-knowledge-indexer`
- `agents/ba/update-squad-schema`

### Fluxo

1. **Crie a branch** a partir de `main`:
   ```bash
   git checkout main && git pull
   git checkout -b agents/<tier>/<slug>
   ```

2. **Implemente** as mudanças seguindo o padrão de commits acima.

3. **Abra o PR como *draft*** enquanto a implementação ainda estiver em andamento. Isso sinaliza ao time que a branch existe e está sendo trabalhada.

4. **Preencha o corpo do PR** com:
   - **O que mudou** — descrição objetiva das alterações.
   - **Motivo** — contexto e motivação para a mudança.
   - **Como testar** — passos para reproduzir ou validar.
   - **Link para a task** — ex.: `Closes LEO-42`.

5. **Remova o draft** somente quando o PR estiver pronto para revisão.

6. **Aguarde aprovação** de pelo menos um revisor antes de fazer merge.

---

> Dúvidas? Abra uma issue ou entre em contato no canal da squad no Slack.
