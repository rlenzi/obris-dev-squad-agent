"""Smoke unit do rag_indexer (sem Qdrant/Voyage real)."""
from dev_autonomo.onboarding.rag_indexer import (
    map_file_to_stack, build_chunk_header, index_scanned_files, IndexResult,
)
from dev_autonomo.onboarding.repo_scanner import ChunkKind
from dev_autonomo.onboarding.schemas import StackDetected, StackConventions


def _conv5():
    return {f"k{i}": f"valor {i}" for i in range(5)}


def _stack(slug, paths):
    return StackDetected(
        slug=slug, name=slug, paths=paths,
        framework=None, framework_version=None,
        conventions=StackConventions(
            observed_patterns=_conv5(), recommended_for_agents=_conv5(),
        ),
    )


def test_map_simple_match():
    stacks = [_stack("python-fastapi", ["src/dev_autonomo/"])]
    assert map_file_to_stack("src/dev_autonomo/routers/foo.py", stacks) == "python-fastapi"
    assert map_file_to_stack("web/client/index.tsx", stacks) is None
    print("[simple_match] OK")


def test_map_multi_stack_picks_most_specific():
    """Stack mais especifica (path mais longo) vence quando ha overlap."""
    stacks = [
        _stack("everything", ["src/"]),
        _stack("nested", ["src/dev_autonomo/web/"]),
    ]
    # src/dev_autonomo/web/foo deve bater nested, nao everything
    assert map_file_to_stack("src/dev_autonomo/web/foo.py", stacks) == "nested"
    # src/api/foo.py so bate everything
    assert map_file_to_stack("src/api/foo.py", stacks) == "everything"
    print("[multi_stack] OK")


def test_map_multiple_paths_in_one_stack():
    stacks = [_stack("react", ["web/client/", "web/admin/"])]
    assert map_file_to_stack("web/client/src/foo.tsx", stacks) == "react"
    assert map_file_to_stack("web/admin/src/foo.tsx", stacks) == "react"
    assert map_file_to_stack("backend/foo.py", stacks) is None
    print("[multi_paths_one_stack] OK")


def test_map_no_stacks():
    """Lista vazia retorna None."""
    assert map_file_to_stack("src/foo.py", []) is None
    print("[no_stacks] OK")


def test_map_path_normalization():
    """Path com ou sem trailing slash deve dar mesmo resultado."""
    stacks = [_stack("backend", ["src/api"])]
    assert map_file_to_stack("src/api/foo.py", stacks) == "backend"
    # Stack path com trailing slash tambem funciona
    stacks2 = [_stack("backend", ["src/api/"])]
    assert map_file_to_stack("src/api/foo.py", stacks2) == "backend"
    print("[normalization] OK")


def test_build_chunk_header():
    h = build_chunk_header(
        repo="rlenzi/foo",
        relative_path="src/main.py",
        language="python",
        chunk_kind=ChunkKind.CODE,
        stack_slug="python-fastapi",
    )
    assert "repo: rlenzi/foo" in h
    assert "path: src/main.py" in h
    assert "kind: code" in h
    assert "lang: python" in h
    assert "stack: python-fastapi" in h
    assert h.startswith("[") and h.endswith("]")
    print(f"[header] OK: {h}")


def test_build_chunk_header_no_optional():
    """Lang None e stack_slug None omitidos do header."""
    h = build_chunk_header(
        repo="rlenzi/foo",
        relative_path="README.md",
        language=None,
        chunk_kind=ChunkKind.DOCS,
        stack_slug=None,
    )
    assert "lang:" not in h
    assert "stack:" not in h
    print(f"[header no optional] OK: {h}")


def test_index_empty_files():
    """Lista vazia retorna result vazio sem chamar nada."""
    import asyncio
    from uuid import uuid4
    from unittest.mock import MagicMock
    r = asyncio.run(index_scanned_files(
        client_id=uuid4(), squad_id=uuid4(), task_id=uuid4(),
        repo_canonical="x/y", files=[], stacks=[],
        session=MagicMock(),
    ))
    assert isinstance(r, IndexResult)
    assert r.files_indexed == 0
    assert r.chunks_indexed == 0
    print("[empty_files] OK")


test_map_simple_match()
test_map_multi_stack_picks_most_specific()
test_map_multiple_paths_in_one_stack()
test_map_no_stacks()
test_map_path_normalization()
test_build_chunk_header()
test_build_chunk_header_no_optional()
test_index_empty_files()
print("\n=== SMOKE RAG_INDEXER OK ===")
