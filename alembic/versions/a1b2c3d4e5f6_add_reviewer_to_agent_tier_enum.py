"""add reviewer to agent_tier_enum

Revision ID: a1b2c3d4e5f6
Revises: 0e3c98acf69d
Create Date: 2026-05-14 10:00:00.000000

"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: str | Sequence[str] | None = '0e3c98acf69d'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Adiciona 'REVIEWER' ao enum nativo agent_tier_enum no Postgres.

    O enum nativo usa os NAMEs do Python enum (uppercase): BA, ARCHITECT, DEV,
    ONBOARDING_ANALYST. Esta migração adiciona REVIEWER no mesmo padrão.

    LEO-19: a versão original desta migração usava 'reviewer' lowercase, o que
    causava inconsistência com os demais valores do enum. Esta versão:
      - Renomeia 'reviewer' (lowercase) para 'REVIEWER' caso o ambiente já
        tenha aplicado a versão antiga (RENAME VALUE requer PG 10+).
      - Adiciona 'REVIEWER' caso ainda não exista (IF NOT EXISTS — PG 12+).

    Nota: ALTER TYPE ... ADD VALUE não pode ser executado dentro de um bloco
    de transação explícita em versões antigas do Postgres (< 12). A partir
    do PG 12 é permitido. Usamos IF NOT EXISTS para idempotência.
    """
    # Etapa 1: corrige ambientes que pegaram a versão lowercase
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_enum
                WHERE enumlabel = 'reviewer'
                  AND enumtypid = 'agent_tier_enum'::regtype
            ) THEN
                ALTER TYPE agent_tier_enum RENAME VALUE 'reviewer' TO 'REVIEWER';
            END IF;
        END
        $$;
        """
    )
    # Etapa 2: adiciona REVIEWER se ainda não existe (idempotente)
    op.execute("ALTER TYPE agent_tier_enum ADD VALUE IF NOT EXISTS 'REVIEWER'")


def downgrade() -> None:
    """Remoção de valor de enum nativo não é suportada diretamente pelo Postgres.

    Para reverter manualmente seria necessário:
      1. Remover todas as linhas com tier='REVIEWER' da tabela skill_templates.
      2. Recriar o tipo sem o valor 'REVIEWER' e recriar a coluna.
    Esta migração de downgrade é deliberadamente um no-op — remoção deve ser
    feita manualmente se necessário.
    """
    pass
