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
