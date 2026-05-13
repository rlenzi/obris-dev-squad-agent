# Troubleshooting — dev-autonomo

Lista de problemas conhecidos e como resolver.

## Postgres não conecta

Verifique que o container `devauto-postgres` está rodando:

```bash
docker ps | grep devauto-postgres
```

Se não estiver, suba com:

```bash
cd infra && docker compose --env-file ../../secrets/.env up -d
```

## Qdrant retorna 404 ao buscar partition

Causa: a partition pode não existir ainda (squad nunca indexou nada nela).
Solução: tratado em LEO-2 — retriever retorna lista vazia ao invés de levantar.

## Migration falha com "type already exists"

Aconteceu em algum branch antigo? Faça:

```bash
uv run alembic downgrade -1 && uv run alembic upgrade head
```

## Cost tracking não está gravando

Verifique se o `agent_instance_id` está sendo passado no `AgentRunContext`. Se for
None, os custos vão pra `external_api_calls` sem agent_instance_id linkado.
