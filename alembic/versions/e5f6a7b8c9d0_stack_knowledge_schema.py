"""stack knowledge schema — stack_profiles, rag_sources, skill paramétrico

Bloco A do roadmap stack-knowledge:
- Tabela stack_profiles (catalogo de stacks que a plataforma conhece)
- Tabela rag_sources (referencias a conteudo ingestado na RAG)
- MemoryStoreKind ganha STACK_PATTERNS
- skill_templates ganha 3 colunas: system_prompt_template, template_variables,
  parent_stack_profile_id

Notas tecnicas (licao da T5):
- Usa op.execute('CREATE TYPE ...') direto pra evitar bug de
  before_create do sa.Enum dispatcher.
- Modelos declaram Enum(create_type=False, values_callable=...) pra
  bater valores lowercase.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-05-14 18:50:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from alembic import op

revision: str = "e5f6a7b8c9d0"
down_revision: str | Sequence[str] | None = "d4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- 1. Enums novos ---
    # Drop IF EXISTS pra idempotencia em re-runs (caso migration tenha
    # falhado parcialmente antes).

    # MemoryStoreKind ganha STACK_PATTERNS — ALTER TYPE ADD VALUE
    # (Postgres permite adicionar value sem dropar).
    op.execute(
        "ALTER TYPE memory_store_kind_enum ADD VALUE IF NOT EXISTS 'stack_patterns'"
    )

    for type_name in (
        "rag_source_kind_enum",
        "rag_source_scope_enum",
        "rag_source_license_enum",
        "rag_source_quality_enum",
        "rag_source_status_enum",
    ):
        op.execute(f"DROP TYPE IF EXISTS {type_name} CASCADE")

    op.execute(
        "CREATE TYPE rag_source_kind_enum AS ENUM "
        "('file_upload', 'url_fetch', 'pasted_text', 'feedback_loop', 'dreaming')"
    )
    op.execute(
        "CREATE TYPE rag_source_scope_enum AS ENUM "
        "('cross_tenant', 'client_private')"
    )
    op.execute(
        "CREATE TYPE rag_source_license_enum AS ENUM "
        "('redistributable', 'partner_only', 'client_internal', 'internal_derived', 'unknown')"
    )
    op.execute(
        "CREATE TYPE rag_source_quality_enum AS ENUM "
        "('official', 'orbis_curated', 'partner', 'field_proven', 'community', 'internal')"
    )
    op.execute(
        "CREATE TYPE rag_source_status_enum AS ENUM "
        "('pending', 'extracting', 'embedding', 'indexed', 'failed')"
    )

    # --- 2. Tabela stack_profiles ---
    op.create_table(
        "stack_profiles",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.String(length=1024), nullable=True),
        sa.Column("base_prompt_template", sa.Text(), nullable=False),
        sa.Column("default_tools", JSONB(), nullable=False, server_default="[]"),
        sa.Column("default_model_alias", sa.String(length=64), nullable=False),
        sa.Column("conventions_seed", JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "active", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False,
        ),
        sa.UniqueConstraint("slug", name="uq_stack_profile_slug"),
    )
    op.create_index(
        "ix_stack_profiles_slug", "stack_profiles", ["slug"], unique=False,
    )

    # --- 3. Tabela rag_sources ---
    op.create_table(
        "rag_sources",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("collection_slug", sa.String(length=128), nullable=False),
        sa.Column(
            "kind",
            PG_ENUM(
                "file_upload", "url_fetch", "pasted_text", "feedback_loop", "dreaming",
                name="rag_source_kind_enum",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("source_uri", sa.String(length=1024), nullable=True),
        sa.Column("source_hash", sa.String(length=128), nullable=False),
        sa.Column(
            "scope",
            PG_ENUM(
                "cross_tenant", "client_private",
                name="rag_source_scope_enum",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "client_id", PG_UUID(as_uuid=True),
            sa.ForeignKey("clients.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "license",
            PG_ENUM(
                "redistributable", "partner_only", "client_internal",
                "internal_derived", "unknown",
                name="rag_source_license_enum",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "source_quality",
            PG_ENUM(
                "official", "orbis_curated", "partner",
                "field_proven", "community", "internal",
                name="rag_source_quality_enum",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("stack_version", sa.String(length=64), nullable=True),
        sa.Column(
            "uploaded_by_user_id", PG_UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "indexed_chunks", sa.Integer(), nullable=False, server_default="0",
        ),
        sa.Column(
            "status",
            PG_ENUM(
                "pending", "extracting", "embedding", "indexed", "failed",
                name="rag_source_status_enum",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("tags", JSONB(), nullable=False, server_default="[]"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False,
        ),
        sa.UniqueConstraint(
            "collection_slug", "source_hash",
            name="uq_rag_source_per_collection",
        ),
    )
    op.create_index(
        "ix_rag_sources_collection_slug", "rag_sources", ["collection_slug"],
    )
    op.create_index(
        "ix_rag_sources_client_id", "rag_sources", ["client_id"],
    )

    # --- 4. skill_templates ganha 3 colunas ---
    op.add_column(
        "skill_templates",
        sa.Column("system_prompt_template", sa.Text(), nullable=True),
    )
    op.add_column(
        "skill_templates",
        sa.Column("template_variables", JSONB(), nullable=True),
    )
    op.add_column(
        "skill_templates",
        sa.Column(
            "parent_stack_profile_id", PG_UUID(as_uuid=True),
            sa.ForeignKey("stack_profiles.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_skill_templates_parent_stack_profile_id",
        "skill_templates", ["parent_stack_profile_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_skill_templates_parent_stack_profile_id", table_name="skill_templates",
    )
    op.drop_column("skill_templates", "parent_stack_profile_id")
    op.drop_column("skill_templates", "template_variables")
    op.drop_column("skill_templates", "system_prompt_template")

    op.drop_table("rag_sources")
    op.drop_table("stack_profiles")

    op.execute("DROP TYPE IF EXISTS rag_source_status_enum CASCADE")
    op.execute("DROP TYPE IF EXISTS rag_source_quality_enum CASCADE")
    op.execute("DROP TYPE IF EXISTS rag_source_license_enum CASCADE")
    op.execute("DROP TYPE IF EXISTS rag_source_scope_enum CASCADE")
    op.execute("DROP TYPE IF EXISTS rag_source_kind_enum CASCADE")

    # NOTA: ALTER TYPE memory_store_kind_enum ADD VALUE NAO tem
    # contrapartida elegante em PG. Pra rollback completo precisaria
    # recriar o type sem 'stack_patterns' e fazer ALTER COLUMN USING
    # cast. Decisao: nao revertemos esse value (e idempotente no upgrade
    # via IF NOT EXISTS, entao seguro de aplicar varias vezes).
