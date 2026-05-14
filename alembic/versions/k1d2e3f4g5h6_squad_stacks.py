"""add stacks table (entidade persistente da squad)

PR-2 do redesign do onboarding cliente. Cria entidade Stack que vive
na squad — diferente de stack_profiles (template global, ja existia).
Cada Stack representa uma stack detectada/declarada numa squad
especifica, com seus paths, framework, convencoes.

Cada agente Dev da squad fica atrelado a 1+ stacks (atrelacao em PR
futuro), determinando seu escopo.

Revision ID: k1d2e3f4g5h6
Revises: j0c1d2e3f4g5
Create Date: 2026-05-14 20:55:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from alembic import op

revision: str = "k1d2e3f4g5h6"
down_revision: str | Sequence[str] | None = "j0c1d2e3f4g5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("DROP TYPE IF EXISTS stack_status_enum CASCADE")
    op.execute(
        "CREATE TYPE stack_status_enum AS ENUM "
        "('detected', 'manual', 'archived')"
    )

    op.create_table(
        "stacks",
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
        # Link opcional com template global. SET NULL pra nao quebrar
        # a stack se o template global for removido.
        sa.Column(
            "parent_stack_profile_id", PG_UUID(as_uuid=True),
            sa.ForeignKey("stack_profiles.id", ondelete="SET NULL"),
            nullable=True, index=True,
        ),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        # Lista de paths no repo. Default '[]' permite stack manual sem
        # codigo ainda (ex: cliente declara "mobile" antes do app existir).
        sa.Column("paths", JSONB(), nullable=False, server_default="[]"),
        sa.Column("framework", sa.String(length=128), nullable=True),
        sa.Column("framework_version", sa.String(length=64), nullable=True),
        sa.Column("conventions", JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "status",
            PG_ENUM(
                "detected", "manual", "archived",
                name="stack_status_enum",
                create_type=False,
            ),
            nullable=False,
            server_default="detected",
        ),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.UniqueConstraint("squad_id", "slug", name="uq_stack_squad_slug"),
    )
    op.create_index("ix_stacks_status", "stacks", ["status"])


def downgrade() -> None:
    op.drop_index("ix_stacks_status", table_name="stacks")
    op.drop_table("stacks")
    op.execute("DROP TYPE IF EXISTS stack_status_enum CASCADE")
