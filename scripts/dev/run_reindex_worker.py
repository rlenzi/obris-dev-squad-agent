"""Entrypoint para inicializar e manter o ReindexWorker rodando como processo independente.

Uso:
    uv run python -m scripts.dev.run_reindex_worker
"""

from __future__ import annotations

import asyncio
import logging

from dev_autonomo.knowledge.reindex_worker import run_worker


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    print("[reindex-worker] Aguardando mensagens na fila 'knowledge.reindex' ...")
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        print("[reindex-worker] Encerrado.")


if __name__ == "__main__":
    main()
