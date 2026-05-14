"""phase 2 preparatory fields

Adiciona campos que serão usados pela Fase 2 (notebook pessoal por agente +
cloud provider por cliente) + Task.pr_url para mapping persistente Task→PR.

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-05-14 11:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: str | Sequence[str] | None = 'a1b2c3d4e5f6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Adiciona campos preparatórios para Fase 2."""

    # agent_instances.has_personal_notebook
    # Flag que indica se este agente terá um notebook pessoal Docker (Fase 2).
    # False por padrão — agente continua operando como hoje (sem container isolado).
    op.add_column(
        "agent_instances",
        sa.Column(
            "has_personal_notebook",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    # clients.cloud_provider
    # Provider escolhido pelo cliente para provisionar notebooks dos agentes.
    # Valores válidos: 'aws', 'gcp', 'azure', 'ssh' (on-prem), null (não configurado).
    op.add_column(
        "clients",
        sa.Column(
            "cloud_provider",
            sa.String(32),
            nullable=True,
        ),
    )

    # clients.cloud_credentials_id
    # FK para encrypted_secrets onde ficam as credenciais do cloud provider.
    # Vazio enquanto cliente não cadastrou.
    op.add_column(
        "clients",
        sa.Column(
            "cloud_credentials_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_clients_cloud_credentials_id_encrypted_secrets",
        "clients",
        "encrypted_secrets",
        ["cloud_credentials_id"],
        ["id"],
        ondelete="SET NULL",
        use_alter=True,
    )

    # tasks.pr_url
    # URL do PR no GitHub gerado a partir desta task (preenchido pelo agente
    # quando chama github_create_pr — link direto em vez de busca).
    op.add_column(
        "tasks",
        sa.Column(
            "pr_url",
            sa.String(512),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("tasks", "pr_url")
    op.drop_constraint(
        "fk_clients_cloud_credentials_id_encrypted_secrets",
        "clients",
        type_="foreignkey",
    )
    op.drop_column("clients", "cloud_credentials_id")
    op.drop_column("clients", "cloud_provider")
    op.drop_column("agent_instances", "has_personal_notebook")
