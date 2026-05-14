"""add rag_audit_log table

Bloco F do roadmap stack-knowledge. Tabela que registra cada decisao do
pipeline de feedback loop (L1 Haiku extract + L2 Sonnet validate + L3
regex). Permite ao admin auditar qualidade da automacao sem precisar
de validacao previa antes do primeiro ingest real.

Revision ID: g7a8b9c0d1e2
Revises: f6a7b8c9d0e1
Create Date: 2026-05-14 22:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from alembic import op

revision: str = "g7a8b9c0d1e2"
down_revision: str | Sequence[str] | None = "f6a7b8c9d0e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("DROP TYPE IF EXISTS audit_decision_enum CASCADE")
    op.execute(
        "CREATE TYPE audit_decision_enum AS ENUM "
        "('accepted', 'rejected_haiku', 'rejected_sonnet', 'rejected_regex', "
        "'rejected_multi')"
    )

    op.create_table(
        "rag_audit_log",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        # Source que originou o chunk avaliado (NULL se chunk foi rejeitado
        # antes de ser persistido em rag_sources).
        sa.Column(
            "rag_source_id", PG_UUID(as_uuid=True),
            sa.ForeignKey("rag_sources.id", ondelete="SET NULL"),
            nullable=True, index=True,
        ),
        # Stack target da extracao (ex: 'hybris', 'salesforce').
        sa.Column("stack_slug", sa.String(length=64), nullable=False, index=True),
        # URL do PR de origem (pra rastreabilidade — nao expor publicamente).
        sa.Column("pr_url", sa.String(length=512), nullable=True),
        # Indice do chunk dentro da extracao (0..N-1).
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        # Preview curto (~200 chars) do chunk pra auditoria visual.
        sa.Column("chunk_preview", sa.String(length=500), nullable=True),
        # Decisao final do pipeline.
        sa.Column(
            "decision",
            PG_ENUM(
                "accepted", "rejected_haiku", "rejected_sonnet",
                "rejected_regex", "rejected_multi",
                name="audit_decision_enum",
                create_type=False,
            ),
            nullable=False,
        ),
        # Razoes detalhadas (lista). Ex: ["proprietary_identifier", "potential_pii"]
        sa.Column("reasons", JSONB(), nullable=False, server_default="[]"),
        # Output cru do Sonnet validador (JSON com safe + reasons).
        sa.Column("sonnet_verdict", JSONB(), nullable=True),
        # Tokens / custo das 2 chamadas (auditavel pra cost analysis).
        sa.Column("haiku_tokens_in", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("haiku_tokens_out", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sonnet_tokens_in", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sonnet_tokens_out", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
    )
    op.create_index(
        "ix_rag_audit_log_decision",
        "rag_audit_log", ["decision"],
    )


def downgrade() -> None:
    op.drop_index("ix_rag_audit_log_decision", table_name="rag_audit_log")
    op.drop_table("rag_audit_log")
    op.execute("DROP TYPE IF EXISTS audit_decision_enum CASCADE")
