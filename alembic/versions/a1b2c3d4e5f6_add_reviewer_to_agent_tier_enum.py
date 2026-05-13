"""add reviewer to agent_tier_enum

Revision ID: a1b2c3d4e5f6
Revises: 0e3c98acf69d
Create Date: 2026-05-14 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '0e3c98acf69d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Adiciona o valor 'reviewer' ao enum nativo agent_tier_enum no Postgres.

    Nota: ALTER TYPE ... ADD VALUE nao pode ser executado dentro de um bloco
    de transacao explicita em versoes antigas do Postgres (< 12).
    A partir do PG 12 eh permitido. Aqui usamos IF NOT EXISTS para idempotencia.
    """
    op.execute("ALTER TYPE agent_tier_enum ADD VALUE IF NOT EXISTS 'reviewer'")


def downgrade() -> None:
    """Remocao de valor de enum nativo nao e suportada diretamente pelo Postgres.

    Para reverter manualmente seria necessario:
      1. Remover todas as linhas com tier='reviewer' da tabela skill_templates.
      2. Recriar o tipo sem o valor 'reviewer' e recriar a coluna.
    Esta migracao de downgrade e deliberadamente um no-op — remocao deve ser
    feita manualmente se necessario.
    """
    pass
