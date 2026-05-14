"""normalize api_call_kind_enum values to lowercase

A migration original do enum criou valores em UPPERCASE (CHAT, EMBEDDING,
TOOL, WEBHOOK, OTHER). O Bloco D adicionou 'skill_proposal' em lowercase,
quebrando consistencia — e na pratica o ORM mandava member.name (upper)
em todas as inserts. O propose-skills explodiu porque 'SKILL_PROPOSAL'
nao existia no enum.

Esta migration alinha tudo pra lowercase (member.value) e o codigo
passa a usar values_callable na coluna kind. PG 12+ suporta RENAME VALUE
atomico — sem migracao de dados.

Revision ID: i9b0c1d2e3f4
Revises: h8a9b0c1d2e3
Create Date: 2026-05-14 19:50:00.000000

"""
from collections.abc import Sequence

from alembic import op

revision: str = "i9b0c1d2e3f4"
down_revision: str | Sequence[str] | None = "h8a9b0c1d2e3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE api_call_kind_enum RENAME VALUE 'CHAT' TO 'chat'")
    op.execute("ALTER TYPE api_call_kind_enum RENAME VALUE 'EMBEDDING' TO 'embedding'")
    op.execute("ALTER TYPE api_call_kind_enum RENAME VALUE 'TOOL' TO 'tool'")
    op.execute("ALTER TYPE api_call_kind_enum RENAME VALUE 'WEBHOOK' TO 'webhook'")
    op.execute("ALTER TYPE api_call_kind_enum RENAME VALUE 'OTHER' TO 'other'")
    # 'skill_proposal' ja esta lowercase (vindo da migration f6a7b8c9d0e1)


def downgrade() -> None:
    op.execute("ALTER TYPE api_call_kind_enum RENAME VALUE 'chat' TO 'CHAT'")
    op.execute("ALTER TYPE api_call_kind_enum RENAME VALUE 'embedding' TO 'EMBEDDING'")
    op.execute("ALTER TYPE api_call_kind_enum RENAME VALUE 'tool' TO 'TOOL'")
    op.execute("ALTER TYPE api_call_kind_enum RENAME VALUE 'webhook' TO 'WEBHOOK'")
    op.execute("ALTER TYPE api_call_kind_enum RENAME VALUE 'other' TO 'OTHER'")
