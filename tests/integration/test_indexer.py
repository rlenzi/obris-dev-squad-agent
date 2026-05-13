"""Teste de integracao end-to-end do Indexer.

Requer infra rodando (docker compose up). Consome tokens da Voyage API
(volume minimo: ~100 tokens por execucao do teste).
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from dev_autonomo.knowledge.indexer import CodeIndexer
from dev_autonomo.knowledge.qdrant_client import KnowledgePartition, QdrantKnowledgeStore
from dev_autonomo.knowledge.voyage_client import VoyageEmbeddingClient

FIXTURE_PY = '''
def add(a: int, b: int) -> int:
    """Soma dois numeros inteiros."""
    return a + b


def multiply(a: int, b: int) -> int:
    """Multiplica dois numeros inteiros."""
    return a * b


class Calculator:
    """Calculadora simples com operacoes basicas."""

    def power(self, base: int, exp: int) -> int:
        """Calcula base elevado a exp."""
        return base ** exp

    def divide(self, a: int, b: int) -> float:
        """Divide a por b."""
        return a / b
'''


FIXTURE_TS = '''
export function greet(name: string): string {
  return `Hello, ${name}!`;
}

export class UserService {
  async fetchUser(id: number): Promise<User> {
    return await db.users.findOne(id);
  }
}

interface User {
  id: number;
  name: string;
}
'''


@pytest.fixture
def repo_fixture(tmp_path: Path) -> Path:
    """Cria um repo fake pequeno com 1 .py + 1 .ts."""
    (tmp_path / "calc.py").write_text(FIXTURE_PY)
    (tmp_path / "user.ts").write_text(FIXTURE_TS)
    return tmp_path


@pytest.mark.asyncio
async def test_indexer_end_to_end(repo_fixture: Path) -> None:
    """Indexa repo fake, valida chunks no Qdrant, faz retrieval semantico."""
    client_id = uuid4()
    squad_id = uuid4()

    indexer = CodeIndexer()
    result = await indexer.index_repo(
        client_id=client_id,
        squad_id=squad_id,
        repo_path=repo_fixture,
        repo_label="test-fixture",
    )

    store = QdrantKnowledgeStore()
    try:
        # Validacoes de indexacao
        assert result.files_processed == 2
        # Python: 2 funcoes + 1 classe + 2 metodos = 5
        # TypeScript: 1 funcao + 1 classe + 1 metodo + 1 interface = 4
        assert result.chunks_created == 9
        assert result.embedding_tokens > 0
        assert not result.errors

        # Validar contagem no Qdrant
        total = await store.count(KnowledgePartition.CODE, squad_id)
        assert total == 9

        # Retrieval semantico
        voyage = VoyageEmbeddingClient()

        qv = await voyage.embed_query("function that multiplies two numbers")
        results = await store.search(KnowledgePartition.CODE, squad_id, qv, limit=1)
        assert results, "esperado pelo menos 1 resultado"
        assert results[0].payload["name"] == "multiply"

        qv = await voyage.embed_query("interface defining a user with id and name")
        results = await store.search(KnowledgePartition.CODE, squad_id, qv, limit=1)
        assert results
        assert results[0].payload["name"] == "User"
        assert results[0].payload["kind"] == "interface"

    finally:
        try:
            await store.drop_collection(KnowledgePartition.CODE, squad_id)
        except Exception:
            pass
        await store.close()


@pytest.mark.asyncio
async def test_indexer_skips_unsupported_files(tmp_path: Path) -> None:
    """Arquivos sem extensao suportada nao geram chunks."""
    (tmp_path / "README.md").write_text("# Hello")
    (tmp_path / "data.csv").write_text("a,b,c\n1,2,3")

    indexer = CodeIndexer()
    result = await indexer.index_repo(
        client_id=uuid4(),
        squad_id=uuid4(),
        repo_path=tmp_path,
        repo_label="test-unsupported",
    )
    assert result.chunks_created == 0
    assert result.files_processed == 0
    assert result.files_skipped == 2
    assert result.embedding_tokens == 0


@pytest.mark.asyncio
async def test_indexer_handles_empty_repo(tmp_path: Path) -> None:
    """Repo vazio nao gera erros."""
    indexer = CodeIndexer()
    result = await indexer.index_repo(
        client_id=uuid4(),
        squad_id=uuid4(),
        repo_path=tmp_path,
        repo_label="test-empty",
    )
    assert result.chunks_created == 0
    assert result.files_processed == 0
    assert not result.errors
