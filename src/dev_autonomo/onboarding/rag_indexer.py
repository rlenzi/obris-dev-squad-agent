"""RAG indexer da squad — alimenta playbook:{squad_id} com chunks do clone.

Roda DEPOIS do repo_scanner classificar arquivos elegiveis. Pra cada arquivo:
  1. Le conteudo
  2. Chunkeia (sliding window 800/100 tokens via chunk_text existente)
  3. Adiciona header contextual ([repo: X, path: Y, lang: Z, kind: K])
  4. Embedda via VoyageEmbeddingClient (batches automaticos)
  5. Upsert em playbook:{squad_id} no Qdrant

Cost: registra UM ExternalApiCall agregado por execucao com tokens totais
de embedding e cost_usd. Visivel na cost page do cliente.

NAO usa AST chunker — sliding window cobre qualquer linguagem com saida
deterministica. AST chunking eh melhoria futura quando expandirmos suporte
de linguagens (atual AST chunker so cobre Python/TS).

Mapeia ScannedFile.relative_path → stack_slug via prefix match com
stacks[*].paths do OA output. Files sem match (ex: README na raiz) ficam
com stack_slug=None.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any
from uuid import UUID

from qdrant_client.models import PointStruct
from sqlalchemy.ext.asyncio import AsyncSession

from dev_autonomo.knowledge.qdrant_client import KnowledgePartition, QdrantKnowledgeStore
from dev_autonomo.knowledge.voyage_client import VoyageEmbeddingClient
from dev_autonomo.onboarding.repo_scanner import ChunkKind, ScannedFile
from dev_autonomo.onboarding.schemas import StackDetected
from dev_autonomo.services.rag_ingest import chunk_text

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tipos publicos
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class IndexResult:
    files_indexed: int = 0
    files_skipped_empty: int = 0
    files_skipped_error: int = 0
    chunks_indexed: int = 0
    embedding_tokens: int = 0
    cost_usd: Decimal = field(default_factory=lambda: Decimal("0"))


# Callback recebe (chunks_indexed, chunks_total). Pode ser sync ou async.
ProgressCallback = Callable[[int, int], None | Coroutine[Any, Any, None]]


# ---------------------------------------------------------------------------
# Helpers de mapeamento file → stack_slug
# ---------------------------------------------------------------------------


def map_file_to_stack(
    relative_path: str,
    stacks: list[StackDetected],
) -> str | None:
    """Decide a qual stack o arquivo pertence baseado em prefix match com paths.

    Estrategia:
    - Pra cada stack em ordem, checa se algum path da stack eh prefixo do
      relative_path. Primeiro match vence.
    - Stacks com paths mais especificos (mais longos) tem prioridade se
      o caller ordenou. Aqui mantemos ordem original — chamador pode
      pre-ordenar se quiser determinismo.
    - Files sem match ficam com stack_slug=None (ex: README na raiz).

    Args:
        relative_path: path com forward slashes relativo ao clone root.
        stacks: lista de stacks do OA output.

    Returns:
        slug da stack que matchou, ou None.
    """
    # Ordena por especificidade descendente (path mais longo primeiro) pra
    # garantir que "src/api/v2/" vence sobre "src/" quando ambos existem.
    sorted_stacks = sorted(
        stacks,
        key=lambda s: max(len(p) for p in s.paths) if s.paths else 0,
        reverse=True,
    )
    rel_norm = relative_path.lstrip("./")
    for stack in sorted_stacks:
        for stack_path in stack.paths:
            normalized = stack_path.strip("./").rstrip("/") + "/"
            if normalized == "/" or normalized == "":
                # Stack que reivindica raiz inteira — match qualquer coisa
                return stack.slug
            if rel_norm.startswith(normalized) or rel_norm == normalized.rstrip("/"):
                return stack.slug
    return None


def build_chunk_header(
    *,
    repo: str,
    relative_path: str,
    language: str | None,
    chunk_kind: ChunkKind,
    stack_slug: str | None,
) -> str:
    """Header contextual prepended a cada chunk antes do embedding.

    Aumenta recall do retrieval semantico: query que mencione repo, path,
    linguagem ou kind achara chunks mesmo sem match exato no codigo.
    Custo: ~30 tokens por chunk.
    """
    parts = [f"repo: {repo}", f"path: {relative_path}", f"kind: {chunk_kind.value}"]
    if language:
        parts.append(f"lang: {language}")
    if stack_slug:
        parts.append(f"stack: {stack_slug}")
    return "[" + ", ".join(parts) + "]"


# ---------------------------------------------------------------------------
# API publica
# ---------------------------------------------------------------------------


async def index_scanned_files(
    *,
    client_id: UUID,
    squad_id: UUID,
    task_id: UUID,
    repo_canonical: str,
    files: list[ScannedFile],
    stacks: list[StackDetected],
    session: AsyncSession,
    qdrant: QdrantKnowledgeStore | None = None,
    voyage: VoyageEmbeddingClient | None = None,
    progress_cb: ProgressCallback | None = None,
    batch_chunks: int = 128,
) -> IndexResult:
    """Indexa todos os ScannedFile na coleção playbook:{squad_id}.

    Args:
        client_id: cliente (vira metadata + ExternalApiCall).
        squad_id: squad alvo (define coleção Qdrant).
        task_id: task de onboarding (vincula ExternalApiCall).
        repo_canonical: URL canonical (ex: rlenzi/obris-dev-squad-agent).
        files: arquivos elegiveis do repo_scanner.
        stacks: stacks detectadas pelo OA (mapeia path → stack_slug).
        session: pra ExternalApiCall via voyage_client cost tracking.
        qdrant: opcional, default constroi.
        voyage: opcional, default constroi com session injetada.
        progress_cb: callback opcional pra reportar progresso.
        batch_chunks: tamanho do batch passado pro Voyage. Default 128.

    Returns:
        IndexResult com contagens e custo agregado.
    """
    if not files:
        return IndexResult()

    qdrant = qdrant or QdrantKnowledgeStore()
    voyage = voyage or VoyageEmbeddingClient(session=session)

    # Garante coleção criada
    await qdrant.ensure_collection(KnowledgePartition.PLAYBOOK, squad_id)

    # Etapa 1: gera todos os chunks (texto + metadata) com headers contextuais
    chunks_metadata: list[dict[str, Any]] = []
    chunks_text_for_embed: list[str] = []

    for file in files:
        try:
            content = file.absolute_path.read_text(
                encoding="utf-8", errors="replace",
            )
        except OSError as exc:
            logger.warning(
                "rag_indexer: falha lendo %s: %s — pulando",
                file.relative_path, exc,
            )
            continue
        if not content.strip():
            continue

        stack_slug = map_file_to_stack(file.relative_path, stacks)
        header = build_chunk_header(
            repo=repo_canonical,
            relative_path=file.relative_path,
            language=file.language,
            chunk_kind=file.chunk_kind,
            stack_slug=stack_slug,
        )

        raw_chunks = chunk_text(content)
        for idx, raw in enumerate(raw_chunks):
            full = f"{header}\n{raw}"
            chunks_text_for_embed.append(full)
            chunks_metadata.append({
                "file_path": file.relative_path,
                "file_hash": file.file_hash,
                "language": file.language,
                "chunk_kind": file.chunk_kind.value,
                "chunk_index": idx,
                "stack_slug": stack_slug,
                "repo": repo_canonical,
                "client_id": str(client_id),
                "squad_id": str(squad_id),
                "size_bytes": file.size_bytes,
                "preview": raw[:200],
            })

    total_chunks = len(chunks_text_for_embed)
    if total_chunks == 0:
        logger.info("rag_indexer: 0 chunks gerados (files=%d)", len(files))
        return IndexResult(files_skipped_empty=len(files))

    logger.info(
        "rag_indexer: %d files → %d chunks pra embedar/indexar",
        len(files), total_chunks,
    )

    # Etapa 2: embedda em batches via VoyageEmbeddingClient (que ja faz
    # batching interno + retry + cost tracking via session/client_id).
    embed_result = await voyage.embed_documents(
        chunks_text_for_embed,
        client_id=client_id,
        task_id=task_id,
    )

    # Etapa 3: monta PointStructs com metadata e vetores
    points: list[PointStruct] = []
    for vector, meta, text in zip(
        embed_result.vectors, chunks_metadata, chunks_text_for_embed,
    ):
        point_id = str(uuid.uuid4())
        # payload inclui texto completo (com header) pra retrieval mostrar
        # algo significativo. preview era ja calculado sem header.
        points.append(PointStruct(
            id=point_id,
            vector=vector,
            payload={**meta, "text": text},
        ))

    # Etapa 4: upsert em batches (qdrant client interno bate em 64)
    await qdrant.upsert_points(KnowledgePartition.PLAYBOOK, squad_id, points)

    # Progress callback final
    await _maybe_call(progress_cb, total_chunks, total_chunks)

    files_indexed = len({m["file_path"] for m in chunks_metadata})
    result = IndexResult(
        files_indexed=files_indexed,
        files_skipped_empty=len(files) - files_indexed,
        chunks_indexed=total_chunks,
        embedding_tokens=embed_result.total_tokens,
        cost_usd=embed_result.cost_usd,
    )
    logger.info(
        "rag_indexer: indexado %d files (%d chunks) custo=$%s tokens=%d",
        result.files_indexed, result.chunks_indexed,
        result.cost_usd, result.embedding_tokens,
    )
    return result


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


async def _maybe_call(
    cb: ProgressCallback | None, current: int, total: int,
) -> None:
    """Chama callback se for fornecido. Aceita sync ou async."""
    if cb is None:
        return
    res = cb(current, total)
    if asyncio.iscoroutine(res):
        await res
