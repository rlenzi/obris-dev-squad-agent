"""add anthropic managed agent + environment ids

Cache local dos IDs dos recursos criados na Anthropic Managed Agents:
  - skill_templates.anthropic_agent_id  : 1 agent por skill template
  - clients.anthropic_environment_id    : 1 environment por client

Substitui o cache in-memory do managed_runner.py (volatil entre processos).

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-05-14 09:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c3d4e5f6a7b8"
down_revision: str | Sequence[str] | None = "b2c3d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "skill_templates",
        sa.Column("anthropic_agent_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "clients",
        sa.Column("anthropic_environment_id", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("clients", "anthropic_environment_id")
    op.drop_column("skill_templates", "anthropic_agent_id")
