"""Testes das tools de escrita + enforce.

Validamos:
- edit_file (replace + rewrite) com path autorizado funciona
- create_file/delete_file funcionam
- enforce bloqueia quando repo nao esta no manifest
- enforce bloqueia path tentando escapar do workspace
"""

from __future__ import annotations

import uuid as uuid_lib
from pathlib import Path

import pytest

from dev_autonomo.agent_runtime.context import AgentRunContext
from dev_autonomo.agent_runtime.enforcement import ManifestEnforcer
from dev_autonomo.agent_runtime.toolset.files import (
    CreateFileTool,
    DeleteFileTool,
    EditFileTool,
)
from dev_autonomo.common.enums import SquadStatus
from dev_autonomo.db.models import Client, Manifest, Squad
from dev_autonomo.db.session import AsyncSessionLocal


@pytest.fixture
async def fixture_squad_with_repo():
    """Squad cujo manifest possui 'workspace-repo' (label generico do teste)."""
    suffix = uuid_lib.uuid4().hex[:8]
    async with AsyncSessionLocal() as session:
        client = Client(slug=f"ftools-{suffix}", name="FTools")
        session.add(client)
        await session.flush()
        squad = Squad(
            client_id=client.id, slug=f"sq-{suffix}", name="SQ", status=SquadStatus.ACTIVE
        )
        session.add(squad)
        await session.flush()
        manifest = Manifest(
            client_id=client.id,
            squad_id=squad.id,
            version=1,
            content={
                "owns": {
                    "repos": ["https://github.com/test/workspace-repo.git"],
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
            s = await session.get(Squad, squad_id)
            if s:
                s.current_manifest_id = None
                await session.commit()
            await session.delete(c)
            await session.commit()


def _make_ctx(session, client_id, squad_id, workspace: Path, repo: str):
    return AgentRunContext(
        client_id=client_id,
        squad_id=squad_id,
        agent_instance_id=None,
        task_id=None,
        session=session,
        claude=None,  # type: ignore[arg-type]
        voyage=None,  # type: ignore[arg-type]
        qdrant=None,  # type: ignore[arg-type]
        retriever=None,  # type: ignore[arg-type]
        enforcer=ManifestEnforcer(session=session, client_id=client_id, squad_id=squad_id),
        workspace_root=workspace,
        workspace_repo=repo,
    )


@pytest.mark.asyncio
async def test_edit_file_replace_in_owned_repo(fixture_squad_with_repo, tmp_path: Path):
    client_id, squad_id = fixture_squad_with_repo
    (tmp_path / "src").mkdir()
    f = tmp_path / "src" / "demo.py"
    f.write_text("def greet():\n    return 'hello'\n")

    async with AsyncSessionLocal() as session:
        ctx = _make_ctx(
            session, client_id, squad_id, tmp_path,
            "https://github.com/test/workspace-repo",
        )
        tool = EditFileTool()
        result = await tool.execute(
            ctx,
            {
                "path": "src/demo.py",
                "mode": "replace",
                "search": "return 'hello'",
                "replacement": "return 'hi there'",
            },
        )
        assert not result.is_error
        assert "'hi there'" in (tmp_path / "src" / "demo.py").read_text()


@pytest.mark.asyncio
async def test_edit_file_blocked_when_repo_not_owned(fixture_squad_with_repo, tmp_path: Path):
    client_id, squad_id = fixture_squad_with_repo
    f = tmp_path / "x.py"
    f.write_text("# nothing\n")

    async with AsyncSessionLocal() as session:
        ctx = _make_ctx(
            session, client_id, squad_id, tmp_path,
            "https://github.com/outsider/other-repo",  # NAO esta no manifest
        )
        tool = EditFileTool()
        result = await tool.execute(
            ctx,
            {"path": "x.py", "mode": "rewrite", "new_content": "# hacked\n"},
        )
        assert result.is_error
        assert "out_of_scope" in result.content or "out_of_scope" in (result.metadata or {})


@pytest.mark.asyncio
async def test_create_and_delete_file(fixture_squad_with_repo, tmp_path: Path):
    client_id, squad_id = fixture_squad_with_repo

    async with AsyncSessionLocal() as session:
        ctx = _make_ctx(
            session, client_id, squad_id, tmp_path,
            "https://github.com/test/workspace-repo",
        )
        # create
        create = CreateFileTool()
        r1 = await create.execute(
            ctx, {"path": "new.txt", "content": "hello"}
        )
        assert not r1.is_error
        assert (tmp_path / "new.txt").exists()

        # delete
        delete = DeleteFileTool()
        r2 = await delete.execute(ctx, {"path": "new.txt"})
        assert not r2.is_error
        assert not (tmp_path / "new.txt").exists()


@pytest.mark.asyncio
async def test_path_escape_blocked(fixture_squad_with_repo, tmp_path: Path):
    client_id, squad_id = fixture_squad_with_repo

    async with AsyncSessionLocal() as session:
        ctx = _make_ctx(
            session, client_id, squad_id, tmp_path,
            "https://github.com/test/workspace-repo",
        )
        tool = CreateFileTool()
        result = await tool.execute(
            ctx, {"path": "../../etc/passwd", "content": "x"}
        )
        assert result.is_error
        # ja barra antes do enforce checar (o resolve detecta escape)
        # ou o enforcer barra primeiro (depende de qual roda primeiro) — qualquer um eh OK
