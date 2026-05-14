"""Tool para o Onboarding Analyst inspecionar a estrutura de um repo cliente.

O Onboarding Analyst recebe um repo recém-clonado e precisa entender:
- Qual stack/framework
- Que linguagens
- Test framework
- CI configurado
- Tamanho aproximado

Esta tool faz a inspeção estática (sem rodar nada) e retorna um dict
estruturado. Não usa LLM — é puramente determinística, para o agente
montar o manifesto inicial em cima de fatos concretos.

Segurança: restringe leitura ao diretório passado e abaixo. Não segue
symlinks pra fora. Não lê arquivos > 1MB pra evitar explosão de payload.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dev_autonomo.agent_runtime.context import AgentRunContext
from dev_autonomo.agent_runtime.toolset.base import ToolResult

MAX_FILE_BYTES_READ = 256 * 1024  # 256 KB
MAX_FILES_WALK = 50_000

# Indicadores de stack/framework
STACK_INDICATORS = {
    "package.json": "node",
    "pyproject.toml": "python",
    "requirements.txt": "python",
    "Pipfile": "python",
    "setup.py": "python",
    "Cargo.toml": "rust",
    "go.mod": "go",
    "pom.xml": "java",
    "build.gradle": "java",
    "build.gradle.kts": "java",
    "Gemfile": "ruby",
    "composer.json": "php",
    "Dockerfile": "container",
    "docker-compose.yml": "container",
    "docker-compose.yaml": "container",
}

# CI files detectados
CI_INDICATORS = {
    ".github/workflows": "github_actions",
    ".gitlab-ci.yml": "gitlab_ci",
    ".circleci/config.yml": "circleci",
    "Jenkinsfile": "jenkins",
    "azure-pipelines.yml": "azure_pipelines",
    "bitbucket-pipelines.yml": "bitbucket",
}

# Extensões → linguagem
LANG_BY_EXT = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".kt": "kotlin",
    ".rb": "ruby",
    ".php": "php",
    ".cs": "csharp",
    ".swift": "swift",
    ".scala": "scala",
    ".sh": "shell",
    ".yml": "yaml",
    ".yaml": "yaml",
    ".sql": "sql",
    ".md": "markdown",
    ".vue": "vue",
    ".svelte": "svelte",
}

IGNORE_DIRS = {
    "node_modules", ".git", ".venv", "venv", "__pycache__", "dist",
    "build", "target", ".next", ".nuxt", "coverage", ".tox",
    ".pytest_cache", ".ruff_cache", ".mypy_cache", "vendor",
}


@dataclass
class AnalyzeRepoTool:
    name: str = "analyze_repo"
    description: str = (
        "Inspeciona estaticamente um repositorio clonado localmente e retorna "
        "estrutura detectada: stack, framework, linguagens, test framework, "
        "CI configurado. Use no comeco do onboarding pra montar o manifesto "
        "em cima de fatos do codebase. Nao executa nada — apenas le arquivos "
        "indicadores (package.json, pyproject.toml, etc) e conta extensoes."
    )
    input_schema: dict[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.input_schema = {
            "type": "object",
            "properties": {
                "repo_path": {
                    "type": "string",
                    "description": (
                        "Caminho absoluto do repo no filesystem local. "
                        "Deve estar previamente clonado/baixado."
                    ),
                },
                "max_depth": {
                    "type": "integer",
                    "default": 6,
                    "minimum": 1,
                    "maximum": 10,
                    "description": "Profundidade max de walk (default 6).",
                },
            },
            "required": ["repo_path"],
        }

    async def execute(self, ctx: AgentRunContext, inputs: dict[str, Any]) -> ToolResult:
        raw_path = str(inputs.get("repo_path", "")).strip()
        if not raw_path:
            return ToolResult.error("repo_path obrigatorio", code="bad_input")

        repo = Path(raw_path).resolve()
        if not repo.exists():
            return ToolResult.error(f"repo_path nao existe: {repo}", code="not_found")
        if not repo.is_dir():
            return ToolResult.error(f"repo_path nao e diretorio: {repo}", code="not_dir")

        max_depth = max(1, min(int(inputs.get("max_depth", 6) or 6), 10))

        summary = _analyze(repo, max_depth=max_depth)
        return ToolResult.ok(summary)


def _analyze(repo: Path, *, max_depth: int) -> dict[str, Any]:
    found_indicators: dict[str, str] = {}
    ext_counts: Counter[str] = Counter()
    file_count = 0
    ci: list[str] = []

    # Walk recursivo manual pra respeitar IGNORE_DIRS e max_depth
    def walk(d: Path, depth: int) -> None:
        nonlocal file_count
        if depth > max_depth or file_count >= MAX_FILES_WALK:
            return
        try:
            for entry in d.iterdir():
                if entry.is_symlink():
                    continue
                if entry.is_dir():
                    if entry.name in IGNORE_DIRS or entry.name.startswith("."):
                        # Mas .github/workflows é relevante pra CI
                        if entry.name == ".github":
                            wf = entry / "workflows"
                            if wf.exists() and wf.is_dir():
                                ci.append("github_actions")
                        continue
                    walk(entry, depth + 1)
                else:
                    file_count += 1
                    name = entry.name
                    if name in STACK_INDICATORS:
                        rel = str(entry.relative_to(repo))
                        found_indicators[rel] = STACK_INDICATORS[name]
                    ext = entry.suffix.lower()
                    if ext in LANG_BY_EXT:
                        ext_counts[ext] += 1
                    # CI files no top-level
                    for ci_file, ci_kind in CI_INDICATORS.items():
                        if not ci_file.endswith("/workflows") and rel_path_match(repo, entry, ci_file):
                            if ci_kind not in ci:
                                ci.append(ci_kind)
        except PermissionError:
            return

    walk(repo, depth=1)

    languages = _languages_from_exts(ext_counts)
    stacks_detected = sorted(set(found_indicators.values()))

    # Lê arquivos-chave pra detectar framework
    framework = _detect_framework(repo, found_indicators)
    test_framework = _detect_test_framework(repo, found_indicators, languages)

    return {
        "repo_path": str(repo),
        "stacks_detected": stacks_detected,
        "framework": framework,
        "languages": languages,
        "test_framework": test_framework,
        "ci": sorted(set(ci)),
        "stack_indicators_found": found_indicators,
        "file_count_walked": file_count,
        "files_by_language": {
            LANG_BY_EXT[ext]: count for ext, count in ext_counts.most_common()
        },
        "top_level_entries": sorted(
            [e.name for e in repo.iterdir() if not e.is_symlink()]
        )[:50],
    }


def rel_path_match(root: Path, entry: Path, suffix: str) -> bool:
    """Verifica se o arquivo entry corresponde ao suffix relativo a root."""
    try:
        rel = entry.relative_to(root)
    except ValueError:
        return False
    return str(rel).replace("\\", "/") == suffix


def _languages_from_exts(ext_counts: Counter[str]) -> list[str]:
    langs: dict[str, int] = {}
    for ext, count in ext_counts.items():
        lang = LANG_BY_EXT.get(ext)
        if lang:
            langs[lang] = langs.get(lang, 0) + count
    # Top 5 por count, excluindo yaml/markdown/sql (não são "linguagens primárias")
    primary = {k: v for k, v in langs.items() if k not in ("yaml", "markdown", "sql")}
    return sorted(primary.keys(), key=lambda k: -primary[k])[:5]


def _detect_framework(repo: Path, indicators: dict[str, str]) -> str | None:
    """Detecta framework primário lendo arquivos-chave (com tamanho limitado)."""
    # Python: ler pyproject.toml ou requirements.txt
    for ind_path, stack in indicators.items():
        full = repo / ind_path
        if not full.is_file():
            continue
        if stack != "python" and stack != "node":
            continue
        try:
            content = full.read_text(encoding="utf-8", errors="replace")[:MAX_FILE_BYTES_READ].lower()
        except OSError:
            continue

        if stack == "python":
            if "fastapi" in content:
                return "fastapi"
            if "django" in content:
                return "django"
            if "flask" in content:
                return "flask"
            if "starlette" in content:
                return "starlette"
        elif stack == "node":
            try:
                pkg = json.loads(full.read_text(encoding="utf-8"))
                deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
            except (json.JSONDecodeError, OSError):
                deps = {}
            if "react" in deps and "vite" in deps:
                return "react+vite"
            if "next" in deps:
                return "nextjs"
            if "react" in deps:
                return "react"
            if "vue" in deps:
                return "vue"
            if "@nestjs/core" in deps:
                return "nestjs"
            if "express" in deps:
                return "express"
            if "svelte" in deps:
                return "svelte"
    return None


def _detect_test_framework(
    repo: Path, indicators: dict[str, str], languages: list[str]
) -> str | None:
    """Detecta test framework via package files."""
    for ind_path, stack in indicators.items():
        full = repo / ind_path
        if not full.is_file():
            continue
        try:
            content = full.read_text(encoding="utf-8", errors="replace")[:MAX_FILE_BYTES_READ].lower()
        except OSError:
            continue
        if stack == "python":
            if "pytest" in content:
                return "pytest"
            if "unittest" in content:
                return "unittest"
        elif stack == "node":
            if "vitest" in content:
                return "vitest"
            if "jest" in content:
                return "jest"
            if "mocha" in content:
                return "mocha"
            if "playwright" in content:
                return "playwright"
    return None
