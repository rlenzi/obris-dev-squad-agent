"""Wrapper async do Voyage AI para gerar embeddings, com cost tracking."""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal
from uuid import UUID

import voyageai
from sqlalchemy.ext.asyncio import AsyncSession

from dev_autonomo.common.claude_pricing import get_pricing
from dev_autonomo.common.enums import ApiCallKind, ApiProvider
from dev_autonomo.config import get_settings
from dev_autonomo.db.models.cost import ExternalApiCall

InputType = Literal["document", "query"]


@dataclass(slots=True)
class EmbeddingsResult:
    vectors: list[list[float]]
    total_tokens: int
    model: str
    cost_usd: Decimal
    latency_ms: int


class VoyageEmbeddingClient:
    """Cliente para gerar embeddings com Voyage AI.

    Se inicializado com `session` E `client_id` for passado nos calls, grava
    em external_api_calls com provider=VOYAGE, kind=EMBEDDING.
    """

    DEFAULT_MODEL = "voyage-code-3"
    DEFAULT_BATCH_SIZE = 128
    DEFAULT_MAX_RETRIES = 6
    DEFAULT_RATE_LIMIT_WAIT_SECONDS = 30.0

    def __init__(
        self,
        client: voyageai.AsyncClient | None = None,
        model: str = DEFAULT_MODEL,
        batch_size: int = DEFAULT_BATCH_SIZE,
        max_retries: int = DEFAULT_MAX_RETRIES,
        rate_limit_wait_seconds: float = DEFAULT_RATE_LIMIT_WAIT_SECONDS,
        session: AsyncSession | None = None,
    ) -> None:
        if client is None:
            settings = get_settings()
            client = voyageai.AsyncClient(api_key=settings.VOYAGE_API_KEY.get_secret_value())
        self._client = client
        self._model = model
        self._batch_size = batch_size
        self._max_retries = max_retries
        self._rate_limit_wait = rate_limit_wait_seconds
        self._session = session

    async def embed_documents(
        self,
        texts: list[str],
        *,
        client_id: UUID | None = None,
        task_id: UUID | None = None,
        agent_instance_id: UUID | None = None,
    ) -> EmbeddingsResult:
        """Embeddings de documentos. Grava custo em external_api_calls se session disponivel."""
        return await self._embed(
            texts,
            input_type="document",
            client_id=client_id,
            task_id=task_id,
            agent_instance_id=agent_instance_id,
        )

    async def embed_query(
        self,
        text: str,
        *,
        client_id: UUID | None = None,
        task_id: UUID | None = None,
        agent_instance_id: UUID | None = None,
    ) -> list[float]:
        result = await self._embed(
            [text],
            input_type="query",
            client_id=client_id,
            task_id=task_id,
            agent_instance_id=agent_instance_id,
        )
        return result.vectors[0]

    async def _embed(
        self,
        texts: list[str],
        input_type: InputType,
        *,
        client_id: UUID | None = None,
        task_id: UUID | None = None,
        agent_instance_id: UUID | None = None,
    ) -> EmbeddingsResult:
        if not texts:
            return EmbeddingsResult(
                vectors=[], total_tokens=0, model=self._model,
                cost_usd=Decimal("0"), latency_ms=0,
            )

        all_vectors: list[list[float]] = []
        total_tokens = 0
        start = time.monotonic()

        for batch_start in range(0, len(texts), self._batch_size):
            batch = texts[batch_start : batch_start + self._batch_size]
            result = await self._embed_batch_with_retry(batch, input_type)
            all_vectors.extend(result.embeddings)
            total_tokens += result.total_tokens

        latency_ms = int((time.monotonic() - start) * 1000)
        pricing = get_pricing(self._model, provider="voyage")
        cost = pricing.cost_usd(input_tokens=total_tokens)

        # Persiste custo se session disponivel
        if self._session is not None and client_id is not None and total_tokens > 0:
            call = ExternalApiCall(
                client_id=client_id,
                task_id=task_id,
                agent_instance_id=agent_instance_id,
                provider=ApiProvider.VOYAGE,
                kind=ApiCallKind.EMBEDDING,
                model=self._model,
                input_tokens=total_tokens,
                output_tokens=0,
                cost_usd=cost,
                latency_ms=latency_ms,
            )
            self._session.add(call)
            await self._session.flush()

        return EmbeddingsResult(
            vectors=all_vectors,
            total_tokens=total_tokens,
            model=self._model,
            cost_usd=cost,
            latency_ms=latency_ms,
        )

    async def _embed_batch_with_retry(
        self, batch: list[str], input_type: InputType
    ) -> voyageai.object.EmbeddingsObject:
        attempt = 0
        last_exc: Exception | None = None
        while attempt < self._max_retries:
            try:
                return await self._client.embed(batch, model=self._model, input_type=input_type)
            except Exception as exc:
                last_exc = exc
                attempt += 1
                if attempt >= self._max_retries:
                    break
                wait = self._compute_wait(exc, attempt)
                await asyncio.sleep(wait)
        raise RuntimeError(
            f"Voyage embed falhou apos {self._max_retries} tentativas: {last_exc}"
        ) from last_exc

    def _compute_wait(self, exc: Exception, attempt: int) -> float:
        msg = str(exc).lower()
        is_rate_limit = "rate" in msg or "limit" in msg or "429" in msg or "too many" in msg
        if is_rate_limit:
            match = re.search(r"retry.*?(\d+)\s*(?:s|sec)", msg)
            if match:
                return float(match.group(1)) + 2.0
            return self._rate_limit_wait * attempt
        return min(2.0 ** attempt, 16.0)
