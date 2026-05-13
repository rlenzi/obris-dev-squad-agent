"""Indexer de codigo: walk repo -> chunks -> embeddings -> Qdrant."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

from qdrant_client.models import PointStruct

from dev_autonomo.knowledge.chunker import CodeChunk, CodeChunker
from dev_autonomo.knowledge.qdrant_client import (
    KnowledgePartition,
    QdrantKnowledgeStore,
)
from dev_autonomo.knowledge.voyage_client import VoyageEmbeddingClient


@dataclass(slots=True)
class IndexingResult:
    files_processed: int
    files_skipped: int
    chunks_created: int
    embedding_tokens: int
    embedding_cost_usd: Decimal
    duration_seconds: float
    errors: list[str] = field(default_factory=list)


class CodeIndexer:
    """Orquestra chunker + voyage + qdrant para indexar um repo local."""

    IGNORE_DIRS: set[str] = {
        ".git",
        "node_modules",
        ".venv",
        "venv",
        "__pycache__",
        "dist",
        "build",
        ".next",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".cache",
        "coverage",
    }

    # Voyage code-3 input pricing (USD/1M tokens) -- ajustar se mudar
    VOYAGE_CODE_3_USD_PER_MTOKEN = Decimal("0.18")

    # Limite por chunk para nao explodir tokens (voyage suporta 16k, mas chunks grandes
    # diluem retrieval; corto chunks acima de ~8000 chars para evitar perda de qualidade)
    MAX_CHUNK_CHARS = 8000

    def __init__(
        self,
        chunker: CodeChunker | None = None,
        voyage: VoyageEmbeddingClient | None = None,
        qdrant: QdrantKnowledgeStore | None = None,
    ) -> None:
        self._chunker = chunker or CodeChunker()
        self._voyage = voyage or VoyageEmbeddingClient()
        self._qdrant = qdrant or QdrantKnowledgeStore()

    async def index_repo(
        self,
        *,
        client_id: UUID,
        squad_id: UUID,
        repo_path: Path,
        repo_label: str,
        commit_hash: str | None = None,
    ) -> IndexingResult:
        """Indexa um diretorio local na partition CODE da squad.

        repo_label e a chave usada no payload para identificar o repo (ex: "backend").
        commit_hash, se passado, e gravado no payload para invalidacao futura.
        """
        started = time.monotonic()
        errors: list[str] = []
        files_processed = 0
        files_skipped = 0
        all_chunks: list[CodeChunk] = []

        if not repo_path.is_dir():
            raise ValueError(f"repo_path nao e diretorio: {repo_path}")

        # 1) Walk + chunk
        for file_path in self._walk_files(repo_path):
            language = self._chunker.language_for(file_path)
            if language is None:
                files_skipped += 1
                continue
            try:
                chunks = self._chunker.chunk_file(file_path)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"chunk_file({file_path}): {exc}")
                continue
            if not chunks:
                files_skipped += 1
                continue
            files_processed += 1
            all_chunks.extend(chunks)

        if not all_chunks:
            duration = time.monotonic() - started
            return IndexingResult(
                files_processed=files_processed,
                files_skipped=files_skipped,
                chunks_created=0,
                embedding_tokens=0,
                embedding_cost_usd=Decimal("0"),
                duration_seconds=duration,
                errors=errors,
            )

        # 2) Embedding texts (truncar se muito grandes)
        embed_texts = [self._chunk_to_embedding_text(c, repo_path) for c in all_chunks]

        # 3) Voyage embed
        embed_result = await self._voyage.embed_documents(embed_texts)

        # 4) Ensure collection
        await self._qdrant.ensure_collection(KnowledgePartition.CODE, squad_id)

        # 5) Upsert pontos
        points: list[PointStruct] = []
        for chunk, vector in zip(all_chunks, embed_result.vectors, strict=True):
            rel_path = self._rel_path(chunk.file_path, repo_path)
            points.append(
                PointStruct(
                    id=str(uuid4()),
                    vector=vector,
                    payload={
                        "client_id": str(client_id),
                        "squad_id": str(squad_id),
                        "repo": repo_label,
                        "commit_hash": commit_hash,
                        "file_path": rel_path,
                        "language": chunk.language,
                        "kind": chunk.kind.value,
                        "name": chunk.name,
                        "parent": chunk.parent,
                        "signature": chunk.signature,
                        "start_line": chunk.start_line,
                        "end_line": chunk.end_line,
                        # content limitado a 4k para nao explodir o storage
                        "content": chunk.content[:4000],
                    },
                )
            )
        await self._qdrant.upsert_points(KnowledgePartition.CODE, squad_id, points)

        # 6) Custo
        cost = (
            Decimal(embed_result.total_tokens) / Decimal("1000000")
            * self.VOYAGE_CODE_3_USD_PER_MTOKEN
        )
        duration = time.monotonic() - started

        return IndexingResult(
            files_processed=files_processed,
            files_skipped=files_skipped,
            chunks_created=len(all_chunks),
            embedding_tokens=embed_result.total_tokens,
            embedding_cost_usd=cost,
            duration_seconds=duration,
            errors=errors,
        )

    async def reindex_files(
        self,
        *,
        client_id: UUID,
        squad_id: UUID,
        repo_path: Path,
        repo_label: str,
        files: list[Path],
        commit_hash: str | None = None,
    ) -> IndexingResult:
        """Reindex incremental: apaga chunks dos arquivos especificados e reindexa."""
        started = time.monotonic()
        errors: list[str] = []
        files_processed = 0
        files_skipped = 0
        all_chunks: list[CodeChunk] = []

        await self._qdrant.ensure_collection(KnowledgePartition.CODE, squad_id)

        for file_path in files:
            rel_path = self._rel_path(str(file_path), repo_path)
            # Apaga pontos antigos do arquivo
            await self._qdrant.delete_by_file(KnowledgePartition.CODE, squad_id, rel_path)

            language = self._chunker.language_for(file_path)
            if language is None or not file_path.exists():
                files_skipped += 1
                continue
            try:
                chunks = self._chunker.chunk_file(file_path)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"chunk_file({file_path}): {exc}")
                continue
            if not chunks:
                files_skipped += 1
                continue
            files_processed += 1
            all_chunks.extend(chunks)

        if not all_chunks:
            duration = time.monotonic() - started
            return IndexingResult(
                files_processed=files_processed,
                files_skipped=files_skipped,
                chunks_created=0,
                embedding_tokens=0,
                embedding_cost_usd=Decimal("0"),
                duration_seconds=duration,
                errors=errors,
            )

        embed_texts = [self._chunk_to_embedding_text(c, repo_path) for c in all_chunks]
        embed_result = await self._voyage.embed_documents(embed_texts)

        points: list[PointStruct] = []
        for chunk, vector in zip(all_chunks, embed_result.vectors, strict=True):
            rel_path = self._rel_path(chunk.file_path, repo_path)
            points.append(
                PointStruct(
                    id=str(uuid4()),
                    vector=vector,
                    payload={
                        "client_id": str(client_id),
                        "squad_id": str(squad_id),
                        "repo": repo_label,
                        "commit_hash": commit_hash,
                        "file_path": rel_path,
                        "language": chunk.language,
                        "kind": chunk.kind.value,
                        "name": chunk.name,
                        "parent": chunk.parent,
                        "signature": chunk.signature,
                        "start_line": chunk.start_line,
                        "end_line": chunk.end_line,
                        "content": chunk.content[:4000],
                    },
                )
            )
        await self._qdrant.upsert_points(KnowledgePartition.CODE, squad_id, points)

        cost = (
            Decimal(embed_result.total_tokens) / Decimal("1000000")
            * self.VOYAGE_CODE_3_USD_PER_MTOKEN
        )
        duration = time.monotonic() - started

        return IndexingResult(
            files_processed=files_processed,
            files_skipped=files_skipped,
            chunks_created=len(all_chunks),
            embedding_tokens=embed_result.total_tokens,
            embedding_cost_usd=cost,
            duration_seconds=duration,
            errors=errors,
        )

    # ------- helpers -------

    def _walk_files(self, root: Path):
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            # pula se algum ancestral esta em IGNORE_DIRS
            if any(part in self.IGNORE_DIRS for part in path.relative_to(root).parts):
                continue
            yield path

    def _rel_path(self, abs_or_str_path: str, repo_root: Path) -> str:
        p = Path(abs_or_str_path)
        try:
            return str(p.relative_to(repo_root))
        except ValueError:
            return str(p)

    def _chunk_to_embedding_text(self, chunk: CodeChunk, repo_root: Path) -> str:
        """Monta o texto a ser embeddado: contexto (path/kind/name) + codigo (truncado)."""
        rel_path = self._rel_path(chunk.file_path, repo_root)
        header_parts = [f"file: {rel_path}", f"kind: {chunk.kind.value}", f"name: {chunk.name}"]
        if chunk.parent:
            header_parts.append(f"parent: {chunk.parent}")
        if chunk.signature:
            header_parts.append(f"signature: {chunk.signature}")
        header = "\n".join(header_parts)
        body = chunk.content[: self.MAX_CHUNK_CHARS]
        return f"{header}\n\n{body}"
