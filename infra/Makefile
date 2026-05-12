# dev-autonomo - comandos da infra local
# Uso: make up | make down | make logs | make ps | make psql | make redis-cli

ENV_FILE := ../../secrets/.env
COMPOSE := docker compose --env-file $(ENV_FILE) -f docker-compose.yml

.PHONY: up down logs ps restart psql redis-cli rabbitmq-ui qdrant-info clean status

up:
	@$(COMPOSE) up -d
	@echo ""
	@echo "Aguardando services subirem..."
	@sleep 5
	@$(COMPOSE) ps

down:
	@$(COMPOSE) down

logs:
	@$(COMPOSE) logs -f

ps status:
	@$(COMPOSE) ps

restart:
	@$(COMPOSE) restart

psql:
	@$(COMPOSE) exec postgres psql -U dev_autonomo -d dev_autonomo

redis-cli:
	@$(COMPOSE) exec redis redis-cli

rabbitmq-ui:
	@echo "Acesse: http://localhost:15672 (user: dev_autonomo, senha no .env)"

qdrant-info:
	@curl -s http://localhost:6333/ | head -c 500 ; echo ""
	@curl -s http://localhost:6333/collections | head -c 200 ; echo ""

clean:
	@$(COMPOSE) down -v
	@echo "Containers e volumes destruidos"
