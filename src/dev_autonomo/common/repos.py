"""Normalizacao canonica de identificadores de repo.

Manifesto guarda URLs (https://github.com/owner/repo[.git]).
Indexer grava `repo` no payload do Qdrant.
Retriever filtra por `repo` baseado em owns do manifesto.

Pra esses 3 baterem, todos passam pelo `normalize_repo_id` antes.
"""

from __future__ import annotations


def normalize_repo_id(value: str) -> str:
    """Reduz uma URL/label/path de repo a um identificador canonico.

    Examples:
        >>> normalize_repo_id("https://github.com/rlenzi/reco.orbis.ai.api.git")
        'reco.orbis.ai.api'
        >>> normalize_repo_id("Reco.Orbis.AI.API")
        'reco.orbis.ai.api'
        >>> normalize_repo_id("owner/repo")
        'repo'
        >>> normalize_repo_id("git@github.com:owner/repo.git")
        'repo'
    """
    s = value.strip().rstrip("/")
    if s.endswith(".git"):
        s = s[:-4]
    # SSH form: git@host:owner/repo
    if ":" in s and "/" in s.split(":", 1)[1]:
        s = s.split(":", 1)[1]
    # HTTPS/SSH/path: pega ultimo segmento
    if "/" in s:
        s = s.split("/")[-1]
    return s.lower()


def normalize_repo_ids(values: list[str]) -> set[str]:
    """Normaliza uma lista de repo URLs/labels para um set canonico (dedup)."""
    return {normalize_repo_id(v) for v in values}


def normalize_github_https_url(value: str) -> str | None:
    """Converte URL de repo GitHub na forma canonica https://github.com/{owner}/{repo}.

    A Anthropic Managed Agents API rejeita ``github_repository`` resources
    com sufixo ``.git`` ou trailing slash — esta normalizacao garante o
    formato esperado pela API.

    Aceita:
        https://github.com/owner/repo[.git][/]
        http://github.com/owner/repo  (https forced)
        git@github.com:owner/repo[.git]
        owner/repo

    Retorna ``None`` quando o valor nao se parece com um repo GitHub.

    Examples:
        >>> normalize_github_https_url("https://github.com/rlenzi/foo.git")
        'https://github.com/rlenzi/foo'
        >>> normalize_github_https_url("https://github.com/rlenzi/foo/")
        'https://github.com/rlenzi/foo'
        >>> normalize_github_https_url("git@github.com:rlenzi/foo.git")
        'https://github.com/rlenzi/foo'
        >>> normalize_github_https_url("rlenzi/foo")
        'https://github.com/rlenzi/foo'
        >>> normalize_github_https_url("não-é-repo") is None
        True
    """
    s = value.strip().rstrip("/")
    if s.endswith(".git"):
        s = s[:-4]

    if s.startswith("git@github.com:"):
        return f"https://github.com/{s[len('git@github.com:'):]}"

    if s.startswith(("https://github.com/", "http://github.com/")):
        path = s.split("github.com/", 1)[1]
        if path and "/" in path:
            return f"https://github.com/{path}"
        return None

    if "/" in s and "://" not in s and "github.com" not in s:
        owner_repo = s.lstrip("/")
        if owner_repo.count("/") == 1 and all(owner_repo.split("/")):
            return f"https://github.com/{owner_repo}"

    return None
