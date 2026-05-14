"""add dream_jobs table

Bloco H do roadmap stack-knowledge. Tabela que registra jobs de
consolidacao Dreaming (research preview Anthropic). Enquanto o access
nao chega, jobs nascem como CANDIDATE pra dar visibilidade do que
seria consolidado pos-task; quando DREAMING_ENABLED=true e a API
estiver acessivel, os jobs viram RUNNING -> COMPLETED/FAILED.

Revision ID: h8a9b0c1d2e3
Revises: g7a8b9c0d1e2
Create Date: 2026-05-14 23:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from alembic import op

revision: str = "h8a9b0c1d2e3"
down_revision: str | Sequence[str] | None = "g7a8b9c0d1e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("DROP TYPE IF EXISTS dream_job_status_enum CASCADE")
    op.execute(
        "CREATE TYPE dream_job_status_enum AS ENUM "
        "('candidate', 'running', 'completed', 'failed', 'skipped_unavailable')"
    )

    op.create_table(
        "dream_jobs",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "client_id", PG_UUID(as_uuid=True),
            sa.ForeignKey("clients.id", ondelete="CASCADE"),
            nullable=False, index=True,
        ),
        sa.Column(
            "squad_id", PG_UUID(as_uuid=True),
            sa.ForeignKey("squads.id", ondelete="CASCADE"),
            nullable=False, index=True,
        ),
        sa.Column(
            "task_id", PG_UUID(as_uuid=True),
            sa.ForeignKey("tasks.id", ondelete="SET NULL"),
            nullable=True, index=True,
        ),
        sa.Column("memory_store_id", sa.String(length=128), nullable=False),
        sa.Column("session_ids", JSONB(), nullable=False, server_default="[]"),
        sa.Column("model", sa.String(length=64), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=True),
        sa.Column(
            "status",
            PG_ENUM(
                "candidate", "running", "completed", "failed", "skipped_unavailable",
                name="dream_job_status_enum",
                create_type=False,
            ),
            nullable=False,
            server_default="candidate",
        ),
        sa.Column("dream_id", sa.String(length=128), nullable=True),
        sa.Column("output_memory_store_id", sa.String(length=128), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "cost_usd", sa.Numeric(12, 6),
            nullable=False, server_default="0",
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
    )
    op.create_index(
        "ix_dream_jobs_status",
        "dream_jobs", ["status"],
    )
    op.create_index(
        "ix_dream_jobs_created_at",
        "dream_jobs", ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_dream_jobs_created_at", table_name="dream_jobs")
    op.drop_index("ix_dream_jobs_status", table_name="dream_jobs")
    op.drop_table("dream_jobs")
    op.execute("DROP TYPE IF EXISTS dream_job_status_enum CASCADE")
