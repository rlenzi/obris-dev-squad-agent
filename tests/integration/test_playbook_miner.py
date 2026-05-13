"""Testes do Playbook miner.

A maioria usa Claude mockado (resposta JSON ja pronta) para nao consumir token.
Um teste end-to-end real fica disponivel via marker pytest.mark.live.
"""

from __future__ import annotations

import uuid as uuid_lib
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from dev_autonomo.common.claude_client import ClaudeClient, ClaudeResponse
from dev_autonomo.db.models import Client, PlaybookEntry, Squad
from dev_autonomo.db.session import AsyncSessionLocal
from dev_autonomo.knowledge.playbook_miner import (
    PRReviewCommentEvent,
    mine_pr_review_comment,
)
from dev_autonomo.knowledge.qdrant_client import KnowledgePartition, QdrantKnowledgeStore

# ---- Fixtures ----


@pytest.fixture
async def fixture_client_squad():
    """Cria Client+Squad temporarios; cleanup ao final."""
    suffix = uuid_lib.uuid4().hex[:8]
    async with AsyncSessionLocal() as session:
        client = Client(slug=f"miner-test-{suffix}", name="Miner Test")
        session.add(client)
        await session.flush()
        squad = Squad(client_id=client.id, slug=f"miner-squad-{suffix}", name="Miner Squad")
        session.add(squad)
        await session.commit()
        client_id, squad_id = client.id, squad.id
    yield client_id, squad_id
    async with AsyncSessionLocal() as session:
        c = await session.get(Client, client_id)
        if c:
            await session.delete(c)
            await session.commit()


def _make_mock_claude(json_response: str) -> ClaudeClient:
    """Constroi um ClaudeClient com `.complete()` mockado para retornar texto fixo."""
    claude = ClaudeClient(session=None, anthropic_client=AsyncMock())
    mock_response = ClaudeResponse(
        text=json_response,
        model="claude-haiku-4-5-mock",
        raw=AsyncMock(),
        input_tokens=100,
        output_tokens=50,
        cache_creation_input_tokens=0,
        cache_read_input_tokens=0,
        cost_usd=Decimal("0.0001"),
        latency_ms=500,
        request_id="mock_msg",
    )
    claude.complete = AsyncMock(return_value=mock_response)  # type: ignore[method-assign]
    return claude


# ---- Tests ----


@pytest.mark.asyncio
async def test_classifies_reusable_rule_and_persists(fixture_client_squad):
    """Comment classificado como regra deve gerar PlaybookEntry + Qdrant point."""
    client_id, squad_id = fixture_client_squad
    json_text = (
        '{"is_reusable_rule": true,'
        ' "rationale": "padrao do time",'
        ' "rule_text": "Sempre validar idempotencia em endpoints de pagamento.",'
        ' "scope_glob": "payments/**",'
        ' "severity": "high",'
        ' "example_code": "if PaymentIntent.exists(idempotency_key): return existing"}'
    )
    mock_claude = _make_mock_claude(json_text)

    event = PRReviewCommentEvent(
        client_id=client_id,
        squad_id=squad_id,
        pr_number=42,
        comment_id=7001,
        comment_body="endpoint precisa de idempotencia",
        file_path="payments/charge.py",
    )

    async with AsyncSessionLocal() as session:
        result = await mine_pr_review_comment(event, session=session, claude=mock_claude)
        await session.commit()

    try:
        assert result.is_reusable_rule
        assert result.entry_id is not None

        async with AsyncSessionLocal() as session:
            entry = (
                await session.execute(
                    select(PlaybookEntry).where(PlaybookEntry.id == result.entry_id)
                )
            ).scalar_one()
            assert entry.scope_glob == "payments/**"
            assert entry.severity == "high"
            assert "idempotencia" in entry.rule_text.lower()
            assert entry.origin == "pr_review:PR#42#comment:7001"
            assert entry.embedding_vector_id is not None
    finally:
        store = QdrantKnowledgeStore()
        try:
            await store.drop_collection(KnowledgePartition.PLAYBOOK, squad_id)
        except Exception:
            pass
        await store.close()


@pytest.mark.asyncio
async def test_classifies_pontual_and_does_not_persist(fixture_client_squad):
    """Comment pontual nao gera PlaybookEntry."""
    client_id, squad_id = fixture_client_squad
    json_text = (
        '{"is_reusable_rule": false,'
        ' "rationale": "so um typo deste PR"}'
    )
    mock_claude = _make_mock_claude(json_text)

    event = PRReviewCommentEvent(
        client_id=client_id,
        squad_id=squad_id,
        pr_number=43,
        comment_id=7002,
        comment_body="typo: 'recieve' deveria ser 'receive'",
    )

    async with AsyncSessionLocal() as session:
        result = await mine_pr_review_comment(event, session=session, claude=mock_claude)
        await session.commit()

        assert not result.is_reusable_rule
        assert result.entry_id is None
        count_after = (
            await session.execute(
                select(PlaybookEntry).where(PlaybookEntry.squad_id == squad_id)
            )
        ).scalars().all()
        assert len(count_after) == 0


@pytest.mark.asyncio
async def test_handles_invalid_json_gracefully(fixture_client_squad):
    """Resposta sem JSON nao deve quebrar; retorna error sem persistir."""
    client_id, squad_id = fixture_client_squad
    mock_claude = _make_mock_claude("texto livre sem JSON nenhum")

    event = PRReviewCommentEvent(
        client_id=client_id,
        squad_id=squad_id,
        pr_number=44,
        comment_id=7003,
        comment_body="qualquer coisa",
    )

    async with AsyncSessionLocal() as session:
        result = await mine_pr_review_comment(event, session=session, claude=mock_claude)
        await session.commit()

        assert not result.is_reusable_rule
        assert result.entry_id is None
        assert result.error is not None
