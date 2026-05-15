"""add onboarding progress columns to tasks

PR-3 do redesign. Adiciona colunas pra state machine granular do OA scan v2:
- current_step: nome da etapa atual (cloning, scanning, oa_scanning, indexing,
  finalizing, grading)
- step_label: mensagem em prosa primeira pessoa pra mostrar na tela 2 viva
- scan_progress: JSONB com contadores (total_files, files_processed,
  chunks_total, chunks_indexed, oa_iterations, grader_verdict, etc.)

Permite cliente fechar aba durante analise e voltar — estado fica persistido,
GET /onboarding-status devolve granular.

Revision ID: l2e3f4g5h6i7
Revises: k1d2e3f4g5h6
Create Date: 2026-05-15 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "l2e3f4g5h6i7"
down_revision: str | Sequence[str] | None = "k1d2e3f4g5h6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tasks",
        sa.Column("current_step", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "tasks",
        sa.Column("step_label", sa.Text(), nullable=True),
    )
    op.add_column(
        "tasks",
        sa.Column(
            "scan_progress", JSONB(),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("tasks", "scan_progress")
    op.drop_column("tasks", "step_label")
    op.drop_column("tasks", "current_step")
