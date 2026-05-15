"""Scan de filesystem pos-clone — classifica arquivos elegiveis pra RAG ingest.

Roda apos local_repo_clone.clone_repo() terminar. Caminha pelo filesystem
do clone, aplica exclusoes (gitignore + blocklist + tamanho max), classifica
cada arquivo em chunk_kind (code/test/docs/config), calcula hash. Resultado
alimenta a etapa de RAG ingest do onboarding_analyzer v2.

NAO chama Claude / Voyage / DB. Pura operacao de filesystem. Determinstica
e barata.
"""

from __future__ import annotations

import fnmatch
import hashlib
import logging
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tipos publicos
# ---------------------------------------------------------------------------


class ChunkKind(StrEnum):
    """Classificacao funcional do arquivo (vai pro metadata de cada chunk).

    Permite retrieval da RAG filtrar/ponderar tipos diferentes — agente Dev
    busca primariamente em CODE; BA pondera DOCS; etc.
    """
    CODE = "code"
    TEST = "test"
    DOCS = "docs"
    CONFIG = "config"


@dataclass(slots=True, frozen=True)
class ScannedFile:
    """Arquivo elegivel identificado pelo scanner."""

    absolute_path: Path
    relative_path: str          # relativo ao clone root, com forward slashes
    chunk_kind: ChunkKind
    language: str | None        # detectada por extensao; None quando indefinida
    size_bytes: int
    file_hash: str              # SHA-256 hex


@dataclass(slots=True)
class ScanResult:
    """Resultado agregado do scan."""

    clone_root: Path
    files: list[ScannedFile]
    total_eligible: int
    total_excluded: int
    total_bytes_eligible: int
    excluded_by_reason: dict[str, int]      # ex: {"gitignore": 47, "too_large": 3}


# ---------------------------------------------------------------------------
# Regras de exclusao
# ---------------------------------------------------------------------------


# Diretorios que NUNCA viram RAG. Match por nome de pasta em qualquer profundidade.
_EXCLUDED_DIRS: frozenset[str] = frozenset({
    ".git",
    ".github",
    "node_modules",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    ".cache",
    "dist",
    "build",
    "target",
    "out",
    "bin",
    "obj",
    "vendor",
    "coverage",
    ".coverage",
    ".next",
    ".nuxt",
    ".svelte-kit",
    ".idea",
    ".vscode",
    ".vs",
    "site-packages",
})

# Extensoes binarias / nao indexaveis.
_EXCLUDED_EXTENSIONS: frozenset[str] = frozenset({
    # imagens
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".svg", ".webp", ".tiff",
    # video / audio
    ".mp4", ".mp3", ".wav", ".webm", ".mov", ".avi",
    # archives
    ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z", ".rar",
    # binarios
    ".so", ".dll", ".dylib", ".exe", ".o", ".a", ".class", ".jar", ".war",
    # fontes
    ".woff", ".woff2", ".ttf", ".eot", ".otf",
    # PDFs / docs
    ".pdf", ".docx", ".xlsx", ".pptx",
    # pyc
    ".pyc", ".pyo",
    # databases
    ".db", ".sqlite", ".sqlite3",
    # outros
    ".log", ".tmp", ".bak", ".swp", ".lock",
})

# Patterns de arquivo (glob) ignorados independente de extensao.
_EXCLUDED_PATTERNS: tuple[str, ...] = (
    "*.min.js", "*.min.css",
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "poetry.lock", "Pipfile.lock", "Cargo.lock",
    "*.snap",                                  # jest snapshots
    "*.generated.*",                           # marca de codigo gerado
)

# Tamanho maximo de arquivo (em bytes). Corta lock files monstros, snapshots,
# arquivos gerados gigantescos. 100KB cobre 95%+ de codigo humano normal.
MAX_FILE_SIZE_BYTES = 100 * 1024


# ---------------------------------------------------------------------------
# Classificacao de chunk_kind
# ---------------------------------------------------------------------------


_TEST_PATH_FRAGMENTS: tuple[str, ...] = (
    "/tests/", "/test/", "/__tests__/", "/spec/", "/specs/",
)
_TEST_FILE_SUFFIXES: tuple[str, ...] = (
    "_test.py", "_test.go", "_spec.rb",
    ".test.ts", ".test.tsx", ".test.js", ".test.jsx",
    ".spec.ts", ".spec.tsx", ".spec.js", ".spec.jsx",
    "test_*.py",                               # pytest discovery default
)
_TEST_FILENAMES: tuple[str, ...] = ("conftest.py",)


_DOC_NAMES: tuple[str, ...] = (
    "readme", "changelog", "contributing", "architecture", "conventions",
    "license", "code_of_conduct", "security", "authors", "history", "notes",
)
_DOC_EXTENSIONS: tuple[str, ...] = (".md", ".mdx", ".rst", ".txt", ".adoc")


_CONFIG_FILENAMES: frozenset[str] = frozenset({
    "pyproject.toml", "setup.py", "setup.cfg", "requirements.txt",
    "pipfile", "pipfile.lock", "poetry.lock",
    "package.json",
    "cargo.toml", "go.mod", "go.sum",
    "pom.xml", "build.gradle", "build.gradle.kts", "settings.gradle",
    "gemfile", "rakefile",
    "composer.json",
    "pubspec.yaml",
    "package.swift", "podfile",
    "dockerfile", "docker-compose.yml", "docker-compose.yaml",
    ".dev-autonomo.yml", ".dev-autonomo.yaml",
    "makefile", "justfile",
    ".env.example",
    "tsconfig.json", "vite.config.ts", "vite.config.js",
    "next.config.js", "next.config.mjs",
    "tailwind.config.js", "tailwind.config.ts",
    "alembic.ini",
})
_CONFIG_EXTENSIONS: tuple[str, ...] = (".toml", ".ini", ".cfg")


# Extensoes que viram CODE quando nao classificadas como TEST/DOCS/CONFIG.
_CODE_LANGUAGE_BY_EXT: dict[str, str] = {
    ".py": "python",
    ".ts": "typescript", ".tsx": "typescript",
    ".js": "javascript", ".jsx": "javascript",
    ".mjs": "javascript",
    ".go": "go",
    ".java": "java",
    ".kt": "kotlin", ".kts": "kotlin",
    ".rs": "rust",
    ".rb": "ruby",
    ".php": "php",
    ".cs": "csharp",
    ".swift": "swift",
    ".dart": "dart",
    ".scala": "scala",
    ".c": "c", ".h": "c",
    ".cpp": "cpp", ".cc": "cpp", ".hpp": "cpp",
    ".ex": "elixir", ".exs": "elixir",
    ".erl": "erlang",
    ".clj": "clojure",
    ".sql": "sql",
    ".sh": "shell", ".bash": "shell", ".zsh": "shell",
    ".yaml": "yaml", ".yml": "yaml",
    ".json": "json",
    ".html": "html", ".htm": "html",
    ".css": "css", ".scss": "scss", ".sass": "sass",
    ".vue": "vue",
    ".svelte": "svelte",
}


# ---------------------------------------------------------------------------
# API publica
# ---------------------------------------------------------------------------


def scan_filesystem(clone_root: Path) -> ScanResult:
    """Faz scan completo do filesystem do clone, retorna arquivos elegiveis.

    Args:
        clone_root: caminho do clone (output de clone_repo).

    Returns:
        ScanResult com files elegiveis + estatisticas de exclusao.

    Caracteristicas:
    - Determinstica (mesma entrada = mesma saida)
    - Nao faz I/O alem do filesystem
    - Respeita _EXCLUDED_DIRS, _EXCLUDED_EXTENSIONS, _EXCLUDED_PATTERNS,
      MAX_FILE_SIZE_BYTES, e .gitignore se existir na raiz
    - Classifica chunk_kind por path/extensao/nome com regras estaveis
    - Calcula SHA-256 de cada arquivo (8KB chunks pra evitar carga em mem)
    """
    if not clone_root.exists() or not clone_root.is_dir():
        raise ValueError(f"clone_root invalido: {clone_root}")

    gitignore_patterns = _load_gitignore_patterns(clone_root)
    files: list[ScannedFile] = []
    excluded_counts: dict[str, int] = {
        "excluded_dir": 0,
        "excluded_ext": 0,
        "excluded_pattern": 0,
        "gitignore": 0,
        "too_large": 0,
        "symlink": 0,
        "read_error": 0,
    }
    total_eligible_bytes = 0

    for path in clone_root.rglob("*"):
        if not path.is_file():
            continue
        if path.is_symlink():
            excluded_counts["symlink"] += 1
            continue

        # Path relativo com forward slashes pra metadata (Linux + Mac + Windows)
        try:
            rel = path.relative_to(clone_root).as_posix()
        except ValueError:
            # path nao eh descendente de clone_root (improvavel mas seguro)
            continue

        # Filtro por pasta excluida em qualquer profundidade
        if any(part in _EXCLUDED_DIRS for part in path.parts):
            excluded_counts["excluded_dir"] += 1
            continue

        # Filtro por extensao binaria/nao-indexavel
        ext = path.suffix.lower()
        if ext in _EXCLUDED_EXTENSIONS:
            excluded_counts["excluded_ext"] += 1
            continue

        # Filtro por glob pattern
        name = path.name.lower()
        if any(fnmatch.fnmatch(name, pat) for pat in _EXCLUDED_PATTERNS):
            excluded_counts["excluded_pattern"] += 1
            continue

        # .gitignore (best-effort, glob match)
        if _matches_gitignore(rel, gitignore_patterns):
            excluded_counts["gitignore"] += 1
            continue

        # Filtro por tamanho
        try:
            size = path.stat().st_size
        except OSError:
            excluded_counts["read_error"] += 1
            continue
        if size > MAX_FILE_SIZE_BYTES:
            excluded_counts["too_large"] += 1
            continue
        if size == 0:
            # arquivo vazio nao agrega contexto pra RAG
            continue

        # Classifica
        kind = classify_chunk_kind(rel, path.name)
        language = _CODE_LANGUAGE_BY_EXT.get(ext)

        # Hash (8KB chunks)
        try:
            file_hash = _sha256_file(path)
        except OSError:
            excluded_counts["read_error"] += 1
            continue

        files.append(ScannedFile(
            absolute_path=path,
            relative_path=rel,
            chunk_kind=kind,
            language=language,
            size_bytes=size,
            file_hash=file_hash,
        ))
        total_eligible_bytes += size

    # Ordem estavel pra reprodutibilidade
    files.sort(key=lambda f: f.relative_path)

    logger.info(
        "scan_filesystem: clone=%s eligible=%d excluded=%d bytes=%.1f MB",
        clone_root, len(files),
        sum(excluded_counts.values()),
        total_eligible_bytes / (1024 * 1024),
    )

    return ScanResult(
        clone_root=clone_root,
        files=files,
        total_eligible=len(files),
        total_excluded=sum(excluded_counts.values()),
        total_bytes_eligible=total_eligible_bytes,
        excluded_by_reason=excluded_counts,
    )


def classify_chunk_kind(relative_path: str, filename: str) -> ChunkKind:
    """Classifica um arquivo em CODE/TEST/DOCS/CONFIG.

    Ordem das regras (1a que bate vence):
    1. TEST: path contem pasta de teste OU arquivo bate sufixo de teste
    2. CONFIG: nome do arquivo em _CONFIG_FILENAMES OU extensao toml/ini/cfg
    3. DOCS: extensao md/rst/txt/adoc OU nome em _DOC_NAMES
    4. CODE: default — qualquer outro arquivo que passou nos filtros

    Decisao deliberada: tests/ ganha precedencia sobre docs/ porque eh
    comum ter docs DENTRO de tests/ (ex: tests/README.md descrevendo
    como rodar). Esses arquivos sao mais uteis classificados como TEST
    pra agente Dev procurar "como testar" achar.
    """
    rel_lower = relative_path.lower()
    name_lower = filename.lower()
    rel_with_slashes = "/" + rel_lower + "/"

    # 1. TEST
    if any(frag in rel_with_slashes for frag in _TEST_PATH_FRAGMENTS):
        return ChunkKind.TEST
    if any(name_lower.endswith(suf) for suf in _TEST_FILE_SUFFIXES if not suf.startswith("test_")):
        return ChunkKind.TEST
    if name_lower.startswith("test_") and name_lower.endswith(".py"):
        return ChunkKind.TEST
    if name_lower in _TEST_FILENAMES:
        return ChunkKind.TEST

    # 2. CONFIG
    if name_lower in _CONFIG_FILENAMES:
        return ChunkKind.CONFIG
    ext = "." + name_lower.rsplit(".", 1)[-1] if "." in name_lower else ""
    if ext in _CONFIG_EXTENSIONS:
        return ChunkKind.CONFIG
    if rel_lower.startswith(".github/workflows/"):
        return ChunkKind.CONFIG
    if "dockerfile" in name_lower:
        return ChunkKind.CONFIG

    # 3. DOCS
    if ext in _DOC_EXTENSIONS:
        return ChunkKind.DOCS
    name_no_ext = name_lower.rsplit(".", 1)[0] if "." in name_lower else name_lower
    if name_no_ext in _DOC_NAMES:
        return ChunkKind.DOCS

    # 4. CODE
    return ChunkKind.CODE


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _sha256_file(path: Path) -> str:
    """SHA-256 hex de um arquivo em chunks de 8KB."""
    hasher = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            block = fh.read(8192)
            if not block:
                break
            hasher.update(block)
    return hasher.hexdigest()


def _load_gitignore_patterns(clone_root: Path) -> list[str]:
    """Le .gitignore da raiz. Best-effort, ignora sintaxe avancada.

    Limitacoes deliberadas: nao recursa em .gitignores aninhados (rara em
    repos normais), nao trata `!` negation, nao trata `dir/` distincao
    (qualquer match conta). Pra cliente que precisa precisao gitignore-
    perfeita, _EXCLUDED_DIRS + blocklist cobre 95% dos casos.
    """
    gitignore = clone_root / ".gitignore"
    if not gitignore.exists():
        return []
    try:
        lines = gitignore.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    patterns: list[str] = []
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("!"):
            # negation nao suportada — pular pra nao incluir errado
            continue
        # remove leading / e trailing /
        patterns.append(line.lstrip("/").rstrip("/"))
    return patterns


def _matches_gitignore(rel_path: str, patterns: list[str]) -> bool:
    """Match best-effort de rel_path contra lista de patterns gitignore."""
    if not patterns:
        return False
    rel_lower = rel_path.lower()
    parts = rel_lower.split("/")
    for pat in patterns:
        pat_lower = pat.lower()
        # match contra path inteiro
        if fnmatch.fnmatch(rel_lower, pat_lower):
            return True
        # match contra qualquer segmento
        if any(fnmatch.fnmatch(part, pat_lower) for part in parts):
            return True
        # pattern com / explicito vs path completo
        if "/" in pat_lower and fnmatch.fnmatch(rel_lower, f"*{pat_lower}*"):
            return True
    return False
