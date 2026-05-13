"""Alembic env.py - usa Settings + metadata dos models do projeto."""

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# Importa Base com todos os models registrados
from dev_autonomo.config import get_settings
from dev_autonomo.db.base import Base
from dev_autonomo.db.models import *  # noqa: F403 - registra metadata

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Injeta URL sync do projeto (Alembic usa sync, app usa async)
settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.database_sync_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
            include_schemas=False,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
