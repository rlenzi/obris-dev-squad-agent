"""add managed agents session fields + secrets file ids + squad memory stores

NOTA sobre Enums: usamos sa.dialects.postgresql.ENUM com create_type=False
porque sa.Enum genérico tem dispatch que tenta criar o type durante
before_create, mesmo com create_type=False (bug observado). O create
real e via op.execute('CREATE TYPE ...').



Schema adicional pra suportar trigger via managed_runner no painel:

  clients:
    + jira_secrets_file_id    : str(64) — file_id retornado por
                                c.beta.files.upload do .env Jira.
    + github_secrets_file_id  : str(64) — idem para GitHub (legacy;
                                novo caminho usa github_repository
                                resource direto com authorization_token).

  tasks:
    + anthropic_session_id    : str(64) — session.id criado por
                                managed_runner; promovido de
                                demand_payload.json pra coluna queryable.
    + outcome_status          : enum(pending|satisfied|failed|skipped)
    + outcome_iterations      : int — quantas iteracoes o grader pediu.
    + outcome_rubric_ref      : str(255) — file path no repo OU hash
                                identificando a rubric usada.

  squad_memory_stores (nova tabela):
    id (UUID PK)
    squad_id (UUID FK squads.id ON DELETE CASCADE)
    anthropic_store_id (String 64) — memstore_xxx
    kind (enum: insights|playbook|conventions|onboarding)
    description (String 1024 nullable)
    last_dream_id (String 64 nullable) — dream que gerou esse store atual
    UNIQUE (squad_id, kind)
    created_at, updated_at (TimestampMixin via DateTime defaults).

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-05-14 14:30:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: str | Sequence[str] | None = "c3d4e5f6a7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. clients secrets file ids
    op.add_column(
        "clients",
        sa.Column("jira_secrets_file_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "clients",
        sa.Column("github_secrets_file_id", sa.String(length=64), nullable=True),
    )

    # 2. tasks: session + outcome
    op.add_column(
        "tasks",
        sa.Column("anthropic_session_id", sa.String(length=64), nullable=True),
    )

    # DROP IF EXISTS pra ser idempotente caso run anterior tenha criado.
    op.execute("DROP TYPE IF EXISTS outcome_status_enum CASCADE")
    op.execute(
        "CREATE TYPE outcome_status_enum AS ENUM "
        "('pending', 'satisfied', 'failed', 'skipped')"
    )
    op.add_column(
        "tasks",
        sa.Column(
            "outcome_status",
            PG_ENUM(
                "pending", "satisfied", "failed", "skipped",
                name="outcome_status_enum",
                create_type=False,
            ),
            nullable=False,
            server_default="skipped",
        ),
    )
    op.add_column(
        "tasks",
        sa.Column("outcome_iterations", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "tasks",
        sa.Column("outcome_rubric_ref", sa.String(length=255), nullable=True),
    )

    # 3. squad_memory_stores (nova tabela)
    op.execute("DROP TYPE IF EXISTS memory_store_kind_enum CASCADE")
    op.execute(
        "CREATE TYPE memory_store_kind_enum AS ENUM "
        "('insights', 'playbook', 'conventions', 'onboarding')"
    )

    op.create_table(
        "squad_memory_stores",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "squad_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("squads.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("anthropic_store_id", sa.String(length=64), nullable=False),
        sa.Column(
            "kind",
            PG_ENUM(
                "insights", "playbook", "conventions", "onboarding",
                name="memory_store_kind_enum",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("description", sa.String(length=1024), nullable=True),
        sa.Column("last_dream_id", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("squad_id", "kind", name="uq_squad_memory_kind"),
    )


def downgrade() -> None:
    op.drop_table("squad_memory_stores")
    sa.Enum(name="memory_store_kind_enum").drop(op.get_bind(), checkfirst=True)

    op.drop_column("tasks", "outcome_rubric_ref")
    op.drop_column("tasks", "outcome_iterations")
    op.drop_column("tasks", "outcome_status")
    sa.Enum(name="outcome_status_enum").drop(op.get_bind(), checkfirst=True)

    op.drop_column("tasks", "anthropic_session_id")

    op.drop_column("clients", "github_secrets_file_id")
    op.drop_column("clients", "jira_secrets_file_id")
