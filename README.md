# dev-autonomo

Plataforma de agentes autonomos de desenvolvimento.

## Setup

Veja `infra/docker-compose.yml` para subir Postgres+pgvector, Redis, RabbitMQ e Qdrant localmente.

```bash
cd infra
docker compose --env-file ../../secrets/.env up -d
```

## Comandos `make` (pasta `infra/`)

| Comando           | Descrição                                                        |
|-------------------|------------------------------------------------------------------|
| `make up`         | Sobe todos os serviços em background                             |
| `make down`       | Para e remove os containers                                      |
| `make logs`       | Exibe logs dos serviços (follow)                                 |
| `make ps`         | Lista o status dos containers                                    |
| `make restart`    | Reinicia os serviços                                             |
| `make psql`       | Abre o shell do PostgreSQL                                       |
| `make redis-cli`  | Abre o shell do Redis                                            |
| `make rabbitmq-ui`| Exibe a URL do painel do RabbitMQ                                |
| `make qdrant-info`| Exibe informações do Qdrant via curl                             |
| `make clean`      | Para containers e destrói volumes                                |
| `make seed`       | Popula o banco com dados de dev (client/user/squad/skill_templates) |

## Estrutura

- `src/dev_autonomo/control_plane` - API FastAPI + Painel
- `src/dev_autonomo/knowledge` - Knowledge Hub (indexer, retriever, playbook miner)
- `src/dev_autonomo/agent_runtime` - Workers que executam tasks
- `src/dev_autonomo/mcp_clients` - Wrappers de MCP (Jira, GitHub)
- `src/dev_autonomo/workflow` - Orquestracao BA -> Architect -> Devs
- `src/dev_autonomo/db` - Models SQLAlchemy + sessoes
- `src/dev_autonomo/common` - Utilitarios compartilhados
