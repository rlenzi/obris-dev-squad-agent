# dev-autonomo

Plataforma de agentes autonomos de desenvolvimento.

## Setup

Veja `infra/docker-compose.yml` para subir Postgres+pgvector, Redis, RabbitMQ e Qdrant localmente.

```bash
cd infra
docker compose --env-file ../../secrets/.env up -d
```

## Estrutura

- `src/dev_autonomo/control_plane` - API FastAPI + Painel
- `src/dev_autonomo/knowledge` - Knowledge Hub (indexer, retriever, playbook miner)
- `src/dev_autonomo/agent_runtime` - Workers que executam tasks
- `src/dev_autonomo/mcp_clients` - Wrappers de MCP (Jira, GitHub)
- `src/dev_autonomo/workflow` - Orquestracao BA -> Architect -> Devs
- `src/dev_autonomo/db` - Models SQLAlchemy + sessoes
- `src/dev_autonomo/common` - Utilitarios compartilhados
