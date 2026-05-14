"""add skill_proposal value to api_call_kind enum

Mini-migration do Bloco D. Adiciona valor 'skill_proposal' no
api_call_kind_enum pra rastrear chamadas Claude do
propose_skill_from_stack como ExternalApiCall separadas (visivel
na cost page categoria "setup/skill creation").

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-05-14 21:00:00.000000

"""
from collections.abc import Sequence

from alembic import op

revision: str = "f6a7b8c9d0e1"
down_revision: str | Sequence[str] | None = "e5f6a7b8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TYPE api_call_kind_enum ADD VALUE IF NOT EXISTS 'skill_proposal'"
    )


def downgrade() -> None:
    # PG nao suporta DROP VALUE em enum sem recriar o type. Como o valor
    # eh idempotente via IF NOT EXISTS no upgrade, deixar como noop.
    pass
