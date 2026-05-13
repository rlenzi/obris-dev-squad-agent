"""Wrapper async do RabbitMQ via aio-pika.

Padroniza nomes de exchange/queue e oferece API simples de publish/consume.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

import aio_pika
from aio_pika.abc import AbstractIncomingMessage, AbstractRobustConnection

from dev_autonomo.config import get_settings

logger = logging.getLogger(__name__)

# Padrao de nomes de queue do sistema
EXCHANGE_NAME = "devauto"

# Queues conhecidas
QUEUE_PLAYBOOK_MINER = "devauto.playbook_miner"
QUEUE_GITHUB_PUSH_REINDEX = "devauto.github.push_reindex"
QUEUE_AGENT_RUN = "devauto.agent_run"  # futuro: agente executa task


@asynccontextmanager
async def rabbitmq_connection() -> AbstractRobustConnection:
    """Connection async robusta (reconecta automaticamente)."""
    settings = get_settings()
    conn = await aio_pika.connect_robust(settings.rabbitmq_url)
    try:
        yield conn
    finally:
        await conn.close()


async def publish(
    queue_name: str,
    payload: dict[str, Any],
    *,
    connection: AbstractRobustConnection | None = None,
    persistent: bool = True,
) -> None:
    """Publica uma mensagem JSON em uma queue (declara queue se nao existir)."""

    async def _publish(conn: AbstractRobustConnection) -> None:
        channel = await conn.channel()
        try:
            queue = await channel.declare_queue(queue_name, durable=True)
            body = json.dumps(payload, default=str).encode("utf-8")
            await channel.default_exchange.publish(
                aio_pika.Message(
                    body=body,
                    delivery_mode=(
                        aio_pika.DeliveryMode.PERSISTENT
                        if persistent
                        else aio_pika.DeliveryMode.NOT_PERSISTENT
                    ),
                    content_type="application/json",
                ),
                routing_key=queue.name,
            )
        finally:
            await channel.close()

    if connection is not None:
        await _publish(connection)
    else:
        async with rabbitmq_connection() as conn:
            await _publish(conn)


ConsumerCallback = Callable[[dict[str, Any], AbstractIncomingMessage], Awaitable[None]]


async def consume_forever(
    queue_name: str,
    callback: ConsumerCallback,
    *,
    prefetch: int = 8,
    requeue_on_error: bool = True,
) -> None:
    """Consume mensagens da queue para sempre. Acks apos callback OK; nack em erro.

    `callback` recebe (payload_dict, raw_message).
    """
    async with rabbitmq_connection() as conn:
        channel = await conn.channel()
        await channel.set_qos(prefetch_count=prefetch)
        queue = await channel.declare_queue(queue_name, durable=True)

        async with queue.iterator() as q_it:
            async for message in q_it:
                try:
                    payload = json.loads(message.body.decode("utf-8"))
                except Exception as exc:  # noqa: BLE001
                    logger.error("Falha ao decodificar mensagem %s: %s", message.message_id, exc)
                    await message.nack(requeue=False)
                    continue
                try:
                    await callback(payload, message)
                    await message.ack()
                except Exception as exc:  # noqa: BLE001
                    logger.exception("Callback falhou em %s: %s", queue_name, exc)
                    await message.nack(requeue=requeue_on_error)
                    if not requeue_on_error:
                        # Aguarda um instante para evitar busy-loop em erros sistemicos
                        await asyncio.sleep(0.5)


async def queue_depth(queue_name: str) -> int:
    """Retorna o numero de mensagens na queue (uso operacional)."""
    async with rabbitmq_connection() as conn:
        channel = await conn.channel()
        try:
            queue = await channel.declare_queue(queue_name, durable=True, passive=True)
            return queue.declaration_result.message_count
        finally:
            await channel.close()
