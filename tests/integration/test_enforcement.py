"""Testes de integracao do ManifestEnforcer.

Valida a camada 3 da defesa em profundidade:
- check_repo / check_edit_file / check_db_schema / check_event_publish / check_api_publish
- Logs em tool_authorization_attempts
"""

from __future__ import annotations

import uuid as uuid_lib

import pytest
from sqlalchemy import select

from dev_autonomo.agent_runtime.enforcement import (
    ManifestEnforcer,
)
from dev_autonomo.common.enums import SquadStatus
from dev_autonomo.db.models import Client, Manifest, Squad, ToolAuthorizationAttempt
from dev_autonomo.db.session import AsyncSessionLocal


@pytest.fixture
async def fixture_squad_with_manifest():
    suffix = uuid_lib.uuid4().hex[:8]
    async with AsyncSessionLocal() as session:
        client = Client(slug=f"enf-{suffix}", name="Enf Test")
        session.add(client)
        await session.flush()

        squad = Squad(
            client_id=client.id,
            slug=f"enf-squad-{suffix}",
            name="Enf Squad",
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
                        "https://github.com/orgX/payments-api.git",
                        "https://github.com/orgX/payments-web",
                    ],
                    "modules_in_shared_repos": [
                        "shared-platform/services/billing/**",
                    ],
                    "database": {"schemas": ["payments", "billing"]},
                    "events": {
                        "publishes": ["payment.*", "refund.issued"],
                    },
                    "apis": {
                        "publishes": ["/api/payments/*", "/api/billing/*"],
                    },
                }
            },
        )
        session.add(manifest)
        await session.flush()
        squad.current_manifest_id = manifest.id
        await session.commit()
        client_id, squad_id = client.id, squad.id

    yield client_id, squad_id

    async with AsyncSessionLocal() as session:
        c = await session.get(Client, client_id)
        if c:
            squad = await session.get(Squad, squad_id)
            if squad:
                squad.current_manifest_id = None
                await session.commit()
            await session.delete(c)
            await session.commit()


@pytest.fixture
async def fixture_squad_with_wildcard_schemas():
    """Fixture com schemas usando glob patterns no manifest."""
    suffix = uuid_lib.uuid4().hex[:8]
    async with AsyncSessionLocal() as session:
        client = Client(slug=f"enf-wc-{suffix}", name="Enf WC Test")
        session.add(client)
        await session.flush()

        squad = Squad(
            client_id=client.id,
            slug=f"enf-wc-squad-{suffix}",
            name="Enf WC Squad",
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
                    "repos": [],
                    "database": {"schemas": ["pay_*", "billing"]},
                }
            },
        )
        session.add(manifest)
        await session.flush()
        squad.current_manifest_id = manifest.id
        await session.commit()
        client_id, squad_id = client.id, squad.id

    yield client_id, squad_id

    async with AsyncSessionLocal() as session:
        c = await session.get(Client, client_id)
        if c:
            sq = await session.get(Squad, squad_id)
            if sq:
                sq.current_manifest_id = None
                await session.commit()
            await session.delete(c)
            await session.commit()


@pytest.fixture
async def fixture_squad_no_manifest():
    suffix = uuid_lib.uuid4().hex[:8]
    async with AsyncSessionLocal() as session:
        client = Client(slug=f"enf-nm-{suffix}", name="Enf NM")
        session.add(client)
        await session.flush()
        squad = Squad(client_id=client.id, slug=f"sq-{suffix}", name="NM")
        session.add(squad)
        await session.commit()
        client_id, squad_id = client.id, squad.id
    yield client_id, squad_id
    async with AsyncSessionLocal() as session:
        c = await session.get(Client, client_id)
        if c:
            await session.delete(c)
            await session.commit()


# ---- Tests ----


@pytest.mark.asyncio
async def test_check_repo_owned(fixture_squad_with_manifest):
    client_id, squad_id = fixture_squad_with_manifest
    async with AsyncSessionLocal() as session:
        enf = ManifestEnforcer(session=session, client_id=client_id, squad_id=squad_id)
        r = await enf.check_repo("https://github.com/orgX/payments-api")
        assert r.allowed
        assert r.reason == "owned"
        assert "payments-api" in r.matched_rule


@pytest.mark.asyncio
async def test_check_repo_out_of_scope(fixture_squad_with_manifest):
    client_id, squad_id = fixture_squad_with_manifest
    async with AsyncSessionLocal() as session:
        enf = ManifestEnforcer(session=session, client_id=client_id, squad_id=squad_id)
        r = await enf.check_repo("https://github.com/outroorg/outrorepo")
        assert not r.allowed
        assert r.reason == "out_of_scope"
        assert "create_cross_squad_request" in r.suggestion


@pytest.mark.asyncio
async def test_check_edit_file_in_owned_repo(fixture_squad_with_manifest):
    client_id, squad_id = fixture_squad_with_manifest
    async with AsyncSessionLocal() as session:
        enf = ManifestEnforcer(session=session, client_id=client_id, squad_id=squad_id)
        r = await enf.check_edit_file(
            "https://github.com/orgX/payments-api", "app/api/charge.py"
        )
        assert r.allowed
        assert r.reason == "owned"


@pytest.mark.asyncio
async def test_check_edit_file_in_shared_repo_module(fixture_squad_with_manifest):
    client_id, squad_id = fixture_squad_with_manifest
    async with AsyncSessionLocal() as session:
        enf = ManifestEnforcer(session=session, client_id=client_id, squad_id=squad_id)
        # path em shared-platform que bate em modules_in_shared_repos
        r = await enf.check_edit_file(
            "shared-platform", "services/billing/processor.py"
        )
        assert r.allowed
        assert r.reason == "owned_module"
        assert "billing" in r.matched_rule


@pytest.mark.asyncio
async def test_check_edit_file_out_of_scope(fixture_squad_with_manifest):
    client_id, squad_id = fixture_squad_with_manifest
    async with AsyncSessionLocal() as session:
        enf = ManifestEnforcer(session=session, client_id=client_id, squad_id=squad_id)
        r = await enf.check_edit_file(
            "https://github.com/orgX/users-service", "src/auth.py"
        )
        assert not r.allowed
        assert r.reason == "out_of_scope"


@pytest.mark.asyncio
async def test_check_db_schema_owned(fixture_squad_with_manifest):
    client_id, squad_id = fixture_squad_with_manifest
    async with AsyncSessionLocal() as session:
        enf = ManifestEnforcer(session=session, client_id=client_id, squad_id=squad_id)
        r = await enf.check_db_schema("payments")
        assert r.allowed
        assert r.reason == "owned"

        r = await enf.check_db_schema("users")
        assert not r.allowed


@pytest.mark.asyncio
async def test_check_db_schema_wildcard_star(fixture_squad_with_wildcard_schemas):
    """Schema com wildcard '*' autoriza qualquer schema."""
    client_id, squad_id = fixture_squad_with_wildcard_schemas
    # Substitui manifest para usar "*" em schemas
    suffix = uuid_lib.uuid4().hex[:8]
    async with AsyncSessionLocal() as session:
        sq = await session.get(Squad, squad_id)
        manifest = Manifest(
            client_id=client_id,
            squad_id=squad_id,
            version=2,
            content={"owns": {"repos": [], "database": {"schemas": ["*"]}}},
        )
        session.add(manifest)
        await session.flush()
        sq.current_manifest_id = manifest.id
        await session.commit()

    async with AsyncSessionLocal() as session:
        enf = ManifestEnforcer(session=session, client_id=client_id, squad_id=squad_id)

        r = await enf.check_db_schema("qualquer_schema")
        assert r.allowed
        assert r.reason == "owned"
        assert r.matched_rule == "owns.database:*"

        r = await enf.check_db_schema("OUTRO_SCHEMA")
        assert r.allowed


@pytest.mark.asyncio
async def test_check_db_schema_prefix_pay_wildcard(fixture_squad_with_wildcard_schemas):
    """Schema com prefixo 'pay_*' autoriza pay_charges e pay_subscriptions."""
    client_id, squad_id = fixture_squad_with_wildcard_schemas
    async with AsyncSessionLocal() as session:
        enf = ManifestEnforcer(session=session, client_id=client_id, squad_id=squad_id)

        # Deve ser autorizado pelo pattern "pay_*"
        r = await enf.check_db_schema("pay_charges")
        assert r.allowed
        assert r.reason == "owned"
        assert "pay_*" in r.matched_rule

        r = await enf.check_db_schema("pay_subscriptions")
        assert r.allowed
        assert "pay_*" in r.matched_rule

        # Case-insensitive: maiusculas tambem devem ser autorizadas
        r = await enf.check_db_schema("PAY_REFUNDS")
        assert r.allowed

        # Schema exato declarado no manifest
        r = await enf.check_db_schema("billing")
        assert r.allowed

        # Fora do escopo: nao bate em nenhum pattern
        r = await enf.check_db_schema("users")
        assert not r.allowed
        assert r.reason == "out_of_scope"


@pytest.mark.asyncio
async def test_check_event_publish_pattern_match(fixture_squad_with_manifest):
    client_id, squad_id = fixture_squad_with_manifest
    async with AsyncSessionLocal() as session:
        enf = ManifestEnforcer(session=session, client_id=client_id, squad_id=squad_id)

        r = await enf.check_event_publish("payment.created")
        assert r.allowed
        assert "payment.*" in r.matched_rule

        r = await enf.check_event_publish("refund.issued")
        assert r.allowed

        r = await enf.check_event_publish("user.created")
        assert not r.allowed


@pytest.mark.asyncio
async def test_check_api_publish(fixture_squad_with_manifest):
    client_id, squad_id = fixture_squad_with_manifest
    async with AsyncSessionLocal() as session:
        enf = ManifestEnforcer(session=session, client_id=client_id, squad_id=squad_id)

        r = await enf.check_api_publish("/api/payments/charge")
        assert r.allowed

        r = await enf.check_api_publish("/api/users/login")
        assert not r.allowed


@pytest.mark.asyncio
async def test_no_manifest_blocks_all(fixture_squad_no_manifest):
    client_id, squad_id = fixture_squad_no_manifest
    async with AsyncSessionLocal() as session:
        enf = ManifestEnforcer(session=session, client_id=client_id, squad_id=squad_id)
        r = await enf.check_repo("https://github.com/qq/qq")
        assert not r.allowed
        assert r.reason == "no_manifest"


@pytest.mark.asyncio
async def test_authorize_logs_attempt(fixture_squad_with_manifest):
    """authorize() loga em tool_authorization_attempts."""
    client_id, squad_id = fixture_squad_with_manifest
    async with AsyncSessionLocal() as session:
        enf = ManifestEnforcer(session=session, client_id=client_id, squad_id=squad_id)
        result = await enf.check_repo("https://github.com/orgX/payments-api")
        await enf.authorize("git_push", "https://github.com/orgX/payments-api", result)

        result_bad = await enf.check_repo("https://github.com/outro/qq")
        await enf.authorize("git_push", "https://github.com/outro/qq", result_bad)
        await session.commit()

    # Le os attempts em outra session
    async with AsyncSessionLocal() as session:
        attempts = (
            await session.execute(
                select(ToolAuthorizationAttempt).where(
                    ToolAuthorizationAttempt.squad_id == squad_id
                )
            )
        ).scalars().all()
        assert len(attempts) == 2
        by_resource = {a.resource: a for a in attempts}
        ok = by_resource["https://github.com/orgX/payments-api"]
        bad = by_resource["https://github.com/outro/qq"]
        assert ok.allowed is True
        assert ok.reason == "owned"
        assert bad.allowed is False
        assert bad.reason == "out_of_scope"
        assert "create_cross_squad_request" in bad.suggestion
