"""Smoke E2E: clone repo publico pequeno + scan + asserts."""
import asyncio
from uuid import uuid4
from pathlib import Path
import tempfile
import os

# Override CLONE_BASE_DIR pra usar tempdir, nao poluir o real
os.environ["CLONE_BASE_DIR"] = tempfile.mkdtemp(prefix="smoke-clone-")

from dev_autonomo.onboarding.local_repo_clone import (
    clone_repo, cleanup_clone, get_clone_path, CloneError,
)
from dev_autonomo.onboarding.repo_scanner import (
    scan_filesystem, classify_chunk_kind, ChunkKind,
)


async def test_clone_public_repo():
    """Clone repo publico bem pequeno, verifica metadata."""
    client_id = uuid4()
    task_id = uuid4()
    target = get_clone_path(client_id, task_id)
    print(f"\n[test_clone_public_repo] target={target}")
    assert str(client_id) in str(target), "tenant isolation por client_id"
    assert str(task_id) in str(target), "isolation por task_id"

    try:
        result = await clone_repo(
            repo_url="https://github.com/octocat/Hello-World",
            target_path=target,
            depth=1,
            timeout_seconds=60,
        )
        print(f"  commit={result.commit_hash[:10]} branch={result.default_branch}")
        print(f"  size={result.size_bytes} bytes")
        assert result.path.exists()
        assert (result.path / ".git").exists()
        assert len(result.commit_hash) == 40
        print("  OK clone")

        # Cleanup
        cleanup_clone(result.path)
        assert not result.path.exists()
        print("  OK cleanup")
    except CloneError as exc:
        cleanup_clone(target)
        raise
    except Exception:
        cleanup_clone(target)
        raise


def test_classify_chunk_kind():
    """Regras de classificacao."""
    cases = [
        # TEST
        ("tests/test_foo.py", "test_foo.py", ChunkKind.TEST),
        ("src/__tests__/foo.test.tsx", "foo.test.tsx", ChunkKind.TEST),
        ("spec/api_spec.rb", "api_spec.rb", ChunkKind.TEST),
        ("backend/conftest.py", "conftest.py", ChunkKind.TEST),
        ("backend/tests/utils.py", "utils.py", ChunkKind.TEST),
        # CONFIG
        ("pyproject.toml", "pyproject.toml", ChunkKind.CONFIG),
        ("frontend/package.json", "package.json", ChunkKind.CONFIG),
        (".github/workflows/ci.yml", "ci.yml", ChunkKind.CONFIG),
        ("Dockerfile", "Dockerfile", ChunkKind.CONFIG),
        ("backend/Dockerfile.dev", "Dockerfile.dev", ChunkKind.CONFIG),
        ("setup.cfg", "setup.cfg", ChunkKind.CONFIG),
        # DOCS
        ("README.md", "README.md", ChunkKind.DOCS),
        ("docs/architecture.md", "architecture.md", ChunkKind.DOCS),
        ("CHANGELOG", "CHANGELOG", ChunkKind.DOCS),
        # CODE
        ("src/foo.py", "foo.py", ChunkKind.CODE),
        ("web/client/src/components/Button.tsx", "Button.tsx", ChunkKind.CODE),
        ("internal/handler.go", "handler.go", ChunkKind.CODE),
    ]
    print("\n[test_classify_chunk_kind]")
    failed = 0
    for rel, name, expected in cases:
        got = classify_chunk_kind(rel, name)
        status = "OK" if got == expected else "FAIL"
        if got != expected:
            failed += 1
        print(f"  {status} {rel!r}: got={got.value} expected={expected.value}")
    assert failed == 0, f"{failed} falhas na classificacao"


async def test_scan_after_clone():
    """Clone real + scan, verifica que scan retorna files com chunk_kind."""
    client_id = uuid4()
    task_id = uuid4()
    target = get_clone_path(client_id, task_id)
    print(f"\n[test_scan_after_clone]")

    try:
        result = await clone_repo(
            repo_url="https://github.com/octocat/Hello-World",
            target_path=target,
            depth=1,
            timeout_seconds=60,
        )
        scan = scan_filesystem(result.path)
        print(f"  eligible={scan.total_eligible} excluded={scan.total_excluded}")
        print(f"  bytes eligible={scan.total_bytes_eligible}")
        print(f"  excluded_by_reason={scan.excluded_by_reason}")
        # Hello-World tem README, 1 README é doc
        assert scan.total_eligible >= 1
        kinds = {f.chunk_kind for f in scan.files}
        print(f"  chunk_kinds vistos: {[k.value for k in kinds]}")
        # README.md classificado como DOCS
        readme = next(
            (f for f in scan.files if f.relative_path.lower() == "readme"),
            None,
        )
        # Hello-World tem README (sem extensao). Classificado como DOCS pelo _DOC_NAMES.
        assert readme is None or readme.chunk_kind == ChunkKind.DOCS
        # Cada arquivo tem hash
        for f in scan.files:
            assert len(f.file_hash) == 64, f"hash inválido em {f.relative_path}"
            assert f.size_bytes > 0
        print("  OK scan")
    finally:
        cleanup_clone(target)


def test_invalid_clone_path():
    """clone_path retorna path canonical com client_id e task_id."""
    cid = uuid4()
    tid = uuid4()
    p = get_clone_path(cid, tid)
    print(f"\n[test_invalid_clone_path]")
    print(f"  path={p}")
    assert str(cid) in str(p)
    assert str(tid) in str(p)
    # Caminho absoluto, expandido
    assert p.is_absolute()
    print("  OK")


async def main():
    test_invalid_clone_path()
    test_classify_chunk_kind()
    await test_clone_public_repo()
    await test_scan_after_clone()
    print("\n=== TODOS OS SMOKES PASSARAM ===")


asyncio.run(main())
