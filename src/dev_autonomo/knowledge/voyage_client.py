"""Wrapper async do Voyage AI para gerar embeddings de codigo."""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import Literal

import voyageai

from dev_autonomo.config import get_settings

InputType = Literal["document", "query"]


@dataclass(slots=True)
class EmbeddingsResult:
    vectors: list[list[float]]
    total_tokens: int
    model: str


class VoyageEmbeddingClient:
    """Cliente para gerar embeddings com Voyage AI (voyage-code-3 por padrao).

    Lida com batching automatico e retry inteligente em rate limits.
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
    ) -> None:
        if client is None:
            settings = get_settings()
            client = voyageai.AsyncClient(api_key=settings.VOYAGE_API_KEY.get_secret_value())
        self._client = client
        self._model = model
        self._batch_size = batch_size
        self._max_retries = max_retries
        self._rate_limit_wait = rate_limit_wait_seconds

    async def embed_documents(self, texts: list[str]) -> EmbeddingsResult:
        """Gera embeddings de documentos (codigo a indexar). Batcheia automaticamente."""
        return await self._embed(texts, input_type="document")

    async def embed_query(self, text: str) -> list[float]:
        """Gera embedding de uma query de busca."""
        result = await self._embed([text], input_type="query")
        return result.vectors[0]

    async def _embed(self, texts: list[str], input_type: InputType) -> EmbeddingsResult:
        if not texts:
            return EmbeddingsResult(vectors=[], total_tokens=0, model=self._model)

        all_vectors: list[list[float]] = []
        total_tokens = 0

        for batch_start in range(0, len(texts), self._batch_size):
            batch = texts[batch_start : batch_start + self._batch_size]
            result = await self._embed_batch_with_retry(batch, input_type)
            all_vectors.extend(result.embeddings)
            total_tokens += result.total_tokens

        return EmbeddingsResult(vectors=all_vectors, total_tokens=total_tokens, model=self._model)

    async def _embed_batch_with_retry(
        self, batch: list[str], input_type: InputType
    ) -> voyageai.object.EmbeddingsObject:
        """Retry inteligente: backoff longo em rate limit, curto em outros."""
        attempt = 0
        last_exc: Exception | None = None
        while attempt < self._max_retries:
            try:
                return await self._client.embed(
                    batch, model=self._model, input_type=input_type
                )
            except Exception as exc:  # noqa: BLE001
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
        """Rate limit: espera longa (>= rate_limit_wait). Outros: backoff exponencial curto."""
        msg = str(exc).lower()
        is_rate_limit = "rate" in msg or "limit" in msg or "429" in msg or "too many" in msg

        if is_rate_limit:
            # Tenta extrair "retry after Xs" da mensagem, senao usa default
            match = re.search(r"retry.*?(\d+)\s*(?:s|sec)", msg)
            if match:
                return float(match.group(1)) + 2.0
            return self._rate_limit_wait * attempt  # 30s, 60s, 90s ...
        return min(2.0 ** attempt, 16.0)  # 2, 4, 8, 16s
