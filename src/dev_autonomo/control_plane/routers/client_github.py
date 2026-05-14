"""Router /client/github/* — utilidades GitHub para o frontend cliente.

Endpoint principal: ``GET /client/github/repo-status`` — recebe URL de
repo e devolve metadata útil pra tela 1 do wizard novo decidir se mostra
input de token (caso privado) e que slug sugerir.

NAO grava nada no banco. Tudo runtime.
"""

from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, Depends, Header, Query
from pydantic import BaseModel

from dev_autonomo.common.enums import UserRole
from dev_autonomo.common.repos import normalize_github_https_url
from dev_autonomo.control_plane.dependencies import require_client_context
from dev_autonomo.db.models import Client
from dev_autonomo.mcp_clients.github_client import _request_with_fallback

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/client/github", tags=["client-github"])


class RepoStatusResponse(BaseModel):
    """Resposta do endpoint repo-status.

    Casos:
    - URL invalida (nao reconhecida como repo GitHub) → ``valid=False``,
      restante dos campos a None.
    - URL valida, repo publico (200 sem token) → ``is_public=True``,
      ``accessible=True``, default_branch preenchido.
    - URL valida mas 404/403 sem token → ``is_public=False``,
      ``accessible=False``. Pode ser privado e existir, ou inexistente.
      Front mostra input de token pra retentar.
    - URL valida com Authorization header valido e 200 → ``is_public=False``
      (ou True), ``accessible=True``, default_branch preenchido. Cliente
      tem permissao confirmada.
    - URL valida com Authorization invalido → ``accessible=False`` +
      ``error_detail`` explicando.
    """

    url: str
    valid: bool
    owner: str | None = None
    repo: str | None = None
    is_public: bool | None = None
    accessible: bool | None = None
    default_branch: str | None = None
    suggested_slug: str | None = None
    error: str | None = None


@router.get("/repo-status", response_model=RepoStatusResponse)
async def repo_status(
    url: str = Query(..., description="URL do repositorio GitHub"),
    authorization: str | None = Header(  # noqa: B008
        None,
        description=(
            "Token GitHub opcional. Quando presente, valida acesso ao repo "
            "com a permissao do token. Formato: 'Bearer ghp_...' ou raw token."
        ),
        alias="X-GitHub-Token",
    ),
    ctx: tuple[Client, UserRole] = Depends(require_client_context),
) -> RepoStatusResponse:
    """Verifica o status de acesso a um repositorio GitHub.

    Sempre 200 (mesmo quando repo nao existe ou esta inacessivel) —
    o cliente toma decisao com base nos campos da resposta. Erros de
    rede caem em accessible=False com error_detail.
    """
    canonical = normalize_github_https_url(url)
    if canonical is None:
        return RepoStatusResponse(
            url=url, valid=False,
            error="URL nao reconhecida como repositorio GitHub.",
        )

    # extrai owner/repo do canonical (https://github.com/<owner>/<repo>)
    parts = canonical.removeprefix("https://github.com/").split("/")
    if len(parts) != 2 or not all(parts):
        return RepoStatusResponse(
            url=url, valid=False,
            error="URL invalida: precisa ser https://github.com/<owner>/<repo>.",
        )
    owner, repo = parts
    suggested_slug = repo.lower().replace(".", "-").replace("_", "-")

    # Monta headers — bearer opcional
    headers: dict[str, str] = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "obris-dev-squad-agent",
    }
    if authorization:
        token = authorization.removeprefix("Bearer ").strip()
        if token:
            headers["Authorization"] = f"Bearer {token}"

    try:
        resp = await _request_with_fallback(
            "GET", f"/repos/{owner}/{repo}",
            headers=headers, timeout=10.0,
        )
    except httpx.HTTPError as exc:
        logger.warning(
            "repo-status: erro de rede pra %s/%s: %s", owner, repo, exc,
        )
        return RepoStatusResponse(
            url=canonical, valid=True, owner=owner, repo=repo,
            suggested_slug=suggested_slug,
            accessible=False,
            error=f"Erro de rede falando com GitHub: {type(exc).__name__}",
        )

    if resp.status_code == 200:
        data = resp.json()
        return RepoStatusResponse(
            url=canonical, valid=True, owner=owner, repo=repo,
            is_public=not data.get("private", True),
            accessible=True,
            default_branch=data.get("default_branch"),
            suggested_slug=suggested_slug,
        )

    if resp.status_code in (401, 403):
        return RepoStatusResponse(
            url=canonical, valid=True, owner=owner, repo=repo,
            is_public=False, accessible=False,
            suggested_slug=suggested_slug,
            error=(
                "Token recusado pelo GitHub (401/403). Verifique se tem "
                "permissao 'repo' e nao expirou."
                if authorization else
                "Repositorio privado ou inexistente. Preciso de um token "
                "do GitHub com permissao 'repo' pra confirmar."
            ),
        )

    if resp.status_code == 404:
        return RepoStatusResponse(
            url=canonical, valid=True, owner=owner, repo=repo,
            is_public=False, accessible=False,
            suggested_slug=suggested_slug,
            error=(
                "Repositorio nao encontrado com seu token. Pode estar "
                "errada a URL, ou voce nao tem acesso a esse repo."
                if authorization else
                "Repositorio privado ou inexistente. Preciso de um token "
                "do GitHub com permissao 'repo' pra confirmar."
            ),
        )

    logger.warning(
        "repo-status: GitHub respondeu inesperado %s pra %s/%s",
        resp.status_code, owner, repo,
    )
    return RepoStatusResponse(
        url=canonical, valid=True, owner=owner, repo=repo,
        suggested_slug=suggested_slug,
        accessible=False,
        error=f"GitHub respondeu com status {resp.status_code}.",
    )
