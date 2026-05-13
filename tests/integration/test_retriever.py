"""Teste de integracao do Retriever com boundary filter.

Valida que o retriever:
- Carrega o manifest ativo da squad
- Filtra chunks que nao pertencem aos repos do manifest
- Erra quando squad nao tem manifest (strict=True)
- Pula filtro quando strict=False
"""

from __future__ import annotations

import uuid as uuid_lib
from uuid import uuid4

import pytest
from qdrant_client.models import PointStruct
from sqlalchemy import select

from dev_autonomo.common.enums import SquadStatus
from dev_autonomo.db.models import Client, Manifest, Squad
from dev_autonomo.db.session import AsyncSessionLocal
from dev_autonomo.knowledge.qdrant_client import (
    KnowledgePartition,
    QdrantKnowledgeStore,
)
from dev_autonomo.knowledge.retriever import (
    KnowledgeRetriever,
    ManifestNotFoundError,
)
from dev_autonomo.knowledge.voyage_client import VoyageEmbeddingClient


# ---- Fixtures ----


@pytest.fixture
async def fixture_squad_with_manifest():
    """Cria temporariamente Client+Squad+Manifest no banco; cleanup ao final.

    Yields:
        (client, squad, manifest) — todos com refresh aplicado.
    """
    slug_suffix = uuid_lib.uuid4().hex[:8]
    async with AsyncSessionLocal() as session:
        client = Client(
            slug=f"test-{slug_suffix}",
            name="Test client",
        )
        session.add(client)
        await session.flush()

        squad = Squad(
            client_id=client.id,
            slug=f"test-squad-{slug_suffix}",
            name="Test Squad",
            status=SquadStatus.ACTIVE,
        )
        session.add(squad)
        await session.flush()

        manifest = Manifest(
            client_id=client.id,
            squad_id=squad.id,
            version=1,
            content={
                "owns": {
                    "repos": [
                        "https://github.com/test/allowed-repo-a.git",
                        "https://github.com/test/allowed-repo-b",
                    ],
                }
            },
        )
        session.add(manifest)
        await session.flush()

        squad.current_manifest_id = manifest.id
        await session.commit()

        client_id = client.id
        squad_id = squad.id

    yield client_id, squad_id

    # Cleanup
    async with AsyncSessionLocal() as session:
        squad = await session.get(Squad, squad_id)
        if squad:
            squad.current_manifest_id = None
            await session.commit()
        client = await session.get(Client, client_id)
        if client:
            await session.delete(client)
            await session.commit()


@pytest.fixture
async def fixture_squad_no_manifest():
    """Squad sem manifesto ativo."""
    slug_suffix = uuid_lib.uuid4().hex[:8]
    async with AsyncSessionLocal() as session:
        client = Client(
            slug=f"test-nomanif-{slug_suffix}",
            name="Test client no manifest",
        )
        session.add(client)
        await session.flush()
        squad = Squad(
            client_id=client.id,
            slug=f"test-squad-{slug_suffix}",
            name="No Manifest Squad",
            status=SquadStatus.PROVISIONING,
        )
        session.add(squad)
        await session.commit()
        client_id = client.id
        squad_id = squad.id

    yield client_id, squad_id

    async with AsyncSessionLocal() as session:
        client = await session.get(Client, client_id)
        if client:
            await session.delete(client)
            await session.commit()


async def _seed_qdrant_chunks(squad_id):
    """Insere 6 pontos fake no Qdrant: 2 em cada um de 3 repos."""
    store = QdrantKnowledgeStore()
    await store.ensure_collection(KnowledgePartition.CODE, squad_id)

    points = []
    chunk_specs = [
        # repo, file, name, content fragment
        ("allowed-repo-a", "main.py", "process_order", "calculates order total"),
        ("allowed-repo-a", "auth.py", "login", "authenticates user with credentials"),
        ("allowed-repo-b", "App.tsx", "App", "main React app component"),
        ("allowed-repo-b", "Login.tsx", "Login", "login form component"),
        ("outside-repo-z", "secret.py", "leak_secret", "do not return this"),
        ("outside-repo-z", "backdoor.py", "evil", "should never appear"),
    ]
    voyage = VoyageEmbeddingClient()
    texts = [f"{spec[2]}: {spec[3]}" for spec in chunk_specs]
    embed = await voyage.embed_documents(texts)
    for spec, vec in zip(chunk_specs, embed.vectors, strict=True):
        points.append(
            PointStruct(
                id=str(uuid4()),
                vector=vec,
                payload={
                    "client_id": str(uuid4()),
                    "squad_id": str(squad_id),
                    "repo": spec[0],
                    "file_path": spec[1],
                    "kind": "function",
                    "name": spec[2],
                    "language": "python" if spec[1].endswith(".py") else "tsx",
                    "start_line": 1,
                    "end_line": 10,
                    "content": spec[3],
                },
            )
        )
    await store.upsert_points(KnowledgePartition.CODE, squad_id, points)
    await store.close()


# ---- Tests ----


@pytest.mark.asyncio
async def test_retriever_filters_out_of_scope_repos(fixture_squad_with_manifest):
    """Retriever NUNCA retorna chunks de repos fora do manifest."""
    _, squad_id = fixture_squad_with_manifest
    await _seed_qdrant_chunks(squad_id)

    async with AsyncSessionLocal() as session:
        retriever = KnowledgeRetriever(session=session)
        result = await retriever.retrieve(
            squad_id=squad_id,
            query="authentication and login flow",
            partition=KnowledgePartition.CODE,
            limit=10,
        )

    try:
        assert result.filtered_by_manifest
        assert result.discarded_out_of_scope >= 2  # 2 chunks de outside-repo-z

        repos_returned = {hit.repo for hit in result.hits}
        assert "outside-repo-z" not in repos_returned
        assert repos_returned.issubset({"allowed-repo-a", "allowed-repo-b"})
        assert len(result.hits) >= 1
    finally:
        store = QdrantKnowledgeStore()
        try:
            await store.drop_collection(KnowledgePartition.CODE, squad_id)
        except Exception:
            pass
        await store.close()


@pytest.mark.asyncio
async def test_retriever_errors_when_no_manifest(fixture_squad_no_manifest):
    """Sem manifest e com strict=True deve erar."""
    _, squad_id = fixture_squad_no_manifest
    async with AsyncSessionLocal() as session:
        retriever = KnowledgeRetriever(session=session)
        with pytest.raises(ManifestNotFoundError):
            await retriever.retrieve(
                squad_id=squad_id,
                query="anything",
                strict_manifest=True,
            )


@pytest.mark.asyncio
async def test_retriever_non_strict_mode_skips_filter(fixture_squad_no_manifest):
    """Com strict=False e sem manifest, busca acontece sem filtro de boundary."""
    _, squad_id = fixture_squad_no_manifest
    await _seed_qdrant_chunks(squad_id)

    try:
        async with AsyncSessionLocal() as session:
            retriever = KnowledgeRetriever(session=session)
            result = await retriever.retrieve(
                squad_id=squad_id,
                query="anything",
                strict_manifest=False,
                limit=10,
            )

        assert not result.filtered_by_manifest
        assert result.discarded_out_of_scope == 0
        # Sem filtro: outside-repo-z pode aparecer
    finally:
        store = QdrantKnowledgeStore()
        try:
            await store.drop_collection(KnowledgePartition.CODE, squad_id)
        except Exception:
            pass
        await store.close()
