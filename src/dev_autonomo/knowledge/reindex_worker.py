"""Worker de reindexação incremental: consome fila ``knowledge.reindex``.

Fluxo
-----
1. ``run_worker()`` inicia o loop de consumo via ``consume_forever``.
2. Para cada mensagem, ``handle_reindex()`` é invocado com o payload JSON.
3. O handler desserializa o payload em ``ReindexMessage``, valida o diretório
   do repositório e aciona ``CodeIndexer.reindex_files()`` com os arquivos
   alterados no push.
4. Em caso de diretório inexistente, loga o erro e retorna sem nack
   (evita re-enfileiramento infinito de mensagens irrecuperáveis).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from dev_autonomo.common.queue import consume_forever
from dev_autonomo.knowledge.indexer import CodeIndexer
from dev_autonomo.knowledge.qdrant_client import QdrantKnowledgeStore
from dev_autonomo.knowledge.reindex_schema import REINDEX_QUEUE, ReindexMessage
from dev_autonomo.knowledge.voyage_client import VoyageEmbeddingClient

logger = logging.getLogger(__name__)


async def handle_reindex(payload: dict[str, Any], message: Any) -> None:
    """Callback invocado pelo ``consume_forever`` para cada mensagem recebida.

    Parâmetros
    ----------
    payload:
        Dicionário desserializado do corpo JSON da mensagem RabbitMQ.
    message:
        Mensagem bruta do aio-pika (gerenciamento de ack/nack feito pelo caller).
    """
    # 1. Desserializa o payload
    msg = ReindexMessage.from_dict(payload)

    # 2. Valida que o diretório do repositório existe
    repo_path = Path(msg.repo_path)
    if not repo_path.is_dir():
        logger.error(
            "Diretório do repositório não encontrado, ignorando mensagem: %s "
            "(client_id=%s, squad_id=%s)",
            repo_path,
            msg.client_id,
            msg.squad_id,
        )
        # Retorna sem levantar exceção para evitar nack e re-enfileiramento infinito
        return

    # 3. Instancia dependências e executa o reindex
    voyage = VoyageEmbeddingClient()
    qdrant = QdrantKnowledgeStore()
    indexer = CodeIndexer(voyage=voyage, qdrant=qdrant)

    logger.info(
        "Iniciando reindex: %d arquivo(s) em '%s' (commit=%s, squad_id=%s)",
        len(msg.files),
        repo_path,
        msg.commit_hash or "n/a",
        msg.squad_id,
    )

    result = await indexer.reindex_files(
        client_id=msg.client_id,
        squad_id=msg.squad_id,
        repo_path=repo_path,
        repo_label=msg.repo_label,
        files=[Path(f) for f in msg.files],
        commit_hash=msg.commit_hash,
    )

    # 4. Loga o resultado
    logger.info(
        "Reindex concluido: %s arquivos, %s chunks",
        result.files_processed,
        result.chunks_created,
    )

    if result.errors:
        logger.warning(
            "Reindex finalizado com %d erro(s): %s",
            len(result.errors),
            result.errors,
        )


async def run_worker() -> None:
    """Inicia o loop de consumo da fila ``knowledge.reindex``.

    Bloqueia indefinidamente (até cancelamento externo via ``asyncio``).
    Mensagens com erro no callback são recolocadas na fila (``requeue_on_error=True``).
    """
    logger.info("ReindexWorker iniciando consumo da fila '%s' (prefetch=4)", REINDEX_QUEUE)
    await consume_forever(
        REINDEX_QUEUE,
        handle_reindex,
        prefetch=4,
        requeue_on_error=True,
    )
