"""Conftest root: configura ambiente de teste antes de qualquer import."""

import os

# IMPORTANTE: seta antes de qualquer import de dev_autonomo.db.session
# para que o engine seja criado com NullPool (sem pool entre event loops).
os.environ.setdefault("DEV_AUTONOMO_TESTING", "1")

# Stubs para campos obrigatórios do Settings (não há infra real em testes unitários).
os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("POSTGRES_DB", "test")
os.environ.setdefault("RABBITMQ_USER", "test")
os.environ.setdefault("RABBITMQ_PASSWORD", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("VOYAGE_API_KEY", "test")
