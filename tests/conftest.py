"""Conftest root: configura ambiente de teste antes de qualquer import."""

import os

# IMPORTANTE: seta antes de qualquer import de dev_autonomo.db.session
# para que o engine seja criado com NullPool (sem pool entre event loops).
os.environ.setdefault("DEV_AUTONOMO_TESTING", "1")
