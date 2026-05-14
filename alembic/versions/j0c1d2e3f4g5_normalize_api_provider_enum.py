"""normalize api_provider_enum values to lowercase

Mesmo problema do api_call_kind_enum (migration i9b0c1d2e3f4): valores
em UPPERCASE no PG, codigo passou a usar values_callable na coluna
provider. Renomeia atomic via ALTER TYPE RENAME VALUE.

Revision ID: j0c1d2e3f4g5
Revises: i9b0c1d2e3f4
Create Date: 2026-05-14 19:55:00.000000

"""
from collections.abc import Sequence

from alembic import op

revision: str = "j0c1d2e3f4g5"
down_revision: str | Sequence[str] | None = "i9b0c1d2e3f4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE api_provider_enum RENAME VALUE 'ANTHROPIC' TO 'anthropic'")
    op.execute("ALTER TYPE api_provider_enum RENAME VALUE 'VOYAGE' TO 'voyage'")
    op.execute("ALTER TYPE api_provider_enum RENAME VALUE 'OPENAI' TO 'openai'")
    op.execute("ALTER TYPE api_provider_enum RENAME VALUE 'GITHUB' TO 'github'")
    op.execute("ALTER TYPE api_provider_enum RENAME VALUE 'JIRA' TO 'jira'")
    op.execute("ALTER TYPE api_provider_enum RENAME VALUE 'OTHER' TO 'other'")


def downgrade() -> None:
    op.execute("ALTER TYPE api_provider_enum RENAME VALUE 'anthropic' TO 'ANTHROPIC'")
    op.execute("ALTER TYPE api_provider_enum RENAME VALUE 'voyage' TO 'VOYAGE'")
    op.execute("ALTER TYPE api_provider_enum RENAME VALUE 'openai' TO 'OPENAI'")
    op.execute("ALTER TYPE api_provider_enum RENAME VALUE 'github' TO 'GITHUB'")
    op.execute("ALTER TYPE api_provider_enum RENAME VALUE 'jira' TO 'JIRA'")
    op.execute("ALTER TYPE api_provider_enum RENAME VALUE 'other' TO 'OTHER'")
