"""Cliente HTTP do GitHub API. Token vem do vault do cliente.

Inclui fallback de IPs quando a rota normal para ``api.github.com`` está
quebrada (caso visto em produção: blackhole BGP entre ISP brasileiro e
um IP específico do Azure que GitHub usa). Quando primary route falha
com timeout/connect error, itera por IPs alternativos do GitHub
(``140.82.x.x``) usando ``Host: api.github.com`` no header. O cache do
último IP que funcionou é mantido durante a vida do client pra evitar
fazer o probe a cada chamada.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"
GITHUB_API_HOST = "api.github.com"
DEFAULT_TIMEOUT = 30.0

# IPs alternativos conhecidos do GitHub API. Quando o DNS resolve
# ``api.github.com`` pra um IP com rota quebrada (ex: blackhole BGP),
# o cliente tenta esses em sequência com Host header preservado.
# Lista deliberadamente curta — basta 1 funcionar.
GITHUB_API_FALLBACK_IPS: tuple[str, ...] = (
    "140.82.114.6",
    "140.82.121.6",
    "140.82.112.6",
    "140.82.113.5",
)

# Cache global do IP de fallback que funcionou na última chamada bem-sucedida.
# Evita probe repetido durante uma sessão longa do agente.
_CACHED_FALLBACK_IP: str | None = None


async def _request_with_fallback(
    method: str,
    path: str,
    *,
    headers: dict[str, str],
    timeout: float = DEFAULT_TIMEOUT,
    **kwargs: Any,
) -> httpx.Response:
    """Faz request HTTP com fallback de IPs quando a rota primária falha.

    ``path`` é o caminho depois de ``api.github.com`` (com leading slash).
    Em ConnectError/ConnectTimeout/ReadTimeout, itera por
    ``GITHUB_API_FALLBACK_IPS`` usando ``Host`` header preservado.
    """
    global _CACHED_FALLBACK_IP

    # 1. Se já temos IP de fallback cached, tenta ele primeiro
    if _CACHED_FALLBACK_IP is not None:
        try:
            return await _do_request_via_ip(
                method, path, _CACHED_FALLBACK_IP,
                headers=headers, timeout=timeout, **kwargs,
            )
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout):
            logger.info("github_client: IP cacheado %s falhou, voltando ao DNS", _CACHED_FALLBACK_IP)
            _CACHED_FALLBACK_IP = None

    # 2. Tenta DNS normal
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            return await client.request(
                method, f"{GITHUB_API}{path}", headers=headers, **kwargs,
            )
    except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout) as primary_err:
        logger.warning(
            "github_client: rota primária pra %s falhou (%s). Tentando fallback IPs.",
            path, type(primary_err).__name__,
        )

    # 3. Itera por IPs alternativos
    last_err: Exception | None = None
    for ip in GITHUB_API_FALLBACK_IPS:
        try:
            resp = await _do_request_via_ip(
                method, path, ip, headers=headers, timeout=timeout, **kwargs,
            )
            logger.info("github_client: fallback IP %s funcionou", ip)
            _CACHED_FALLBACK_IP = ip
            return resp
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout) as exc:
            last_err = exc
            continue

    # 4. Todos falharam — re-raise o último erro
    if last_err is not None:
        raise last_err
    raise httpx.ConnectError("github_client: todos os IPs candidatos falharam")


async def _do_request_via_ip(
    method: str,
    path: str,
    ip: str,
    *,
    headers: dict[str, str],
    timeout: float,
    **kwargs: Any,
) -> httpx.Response:
    """Faz request HTTPS diretamente em um IP, com Host header preservado.

    SSL verify desabilitado porque o cert é válido para ``api.github.com``
    e não para o IP literal. O token bearer no header autentica e protege
    contra MITM trivial — esse fallback só ativa quando a rota DNS normal
    está quebrada, situação onde o trade-off é aceitável.
    """
    fallback_headers = {**headers, "Host": GITHUB_API_HOST}
    async with httpx.AsyncClient(timeout=timeout, verify=False) as client:
        return await client.request(
            method, f"https://{ip}{path}", headers=fallback_headers, **kwargs,
        )


@dataclass(slots=True)
class GitHubPR:
    number: int
    html_url: str
    state: str
    title: str
    head_ref: str
    base_ref: str
    raw: dict[str, Any]


class GitHubClient:
    """Cliente fino do GitHub API, autenticado por token bearer."""

    def __init__(self, token: str) -> None:
        self._token = token
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "obris-dev-squad-agent",
        }

    async def get_repo(self, owner: str, repo: str) -> dict[str, Any]:
        resp = await _request_with_fallback(
            "GET", f"/repos/{owner}/{repo}", headers=self._headers,
        )
        resp.raise_for_status()
        return resp.json()

    async def create_pull_request(
        self,
        *,
        owner: str,
        repo: str,
        title: str,
        head: str,
        base: str,
        body: str | None = None,
        draft: bool = False,
    ) -> GitHubPR:
        payload: dict[str, Any] = {
            "title": title,
            "head": head,
            "base": base,
            "draft": draft,
        }
        if body:
            payload["body"] = body
        resp = await _request_with_fallback(
            "POST", f"/repos/{owner}/{repo}/pulls",
            headers=self._headers, json=payload,
        )
        if resp.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"GitHub API erro {resp.status_code}: {resp.text[:500]}",
                request=resp.request,
                response=resp,
            )
        data = resp.json()
        return GitHubPR(
            number=data["number"],
            html_url=data["html_url"],
            state=data["state"],
            title=data["title"],
            head_ref=data["head"]["ref"],
            base_ref=data["base"]["ref"],
            raw=data,
        )

    async def get_pull_request_checks(
        self, owner: str, repo: str, number: int
    ) -> dict[str, Any]:
        """Retorna status agregado dos checks do PR (GitHub Actions + status checks).

        Resposta combina dois endpoints da GitHub API:
        - GET /repos/{owner}/{repo}/commits/{sha}/check-runs (Actions)
        - GET /repos/{owner}/{repo}/commits/{sha}/status (legacy status API)

        Returns:
            Dict com:
              state: 'success' | 'failure' | 'pending' | 'neutral'
              total_count: int
              checks: list of {name, status, conclusion, html_url, started_at, completed_at}
        """
        # 1. Busca o SHA do head do PR
        pr_resp = await _request_with_fallback(
            "GET", f"/repos/{owner}/{repo}/pulls/{number}", headers=self._headers,
        )
        pr_resp.raise_for_status()
        head_sha = pr_resp.json()["head"]["sha"]

        # 2. Check runs (GitHub Actions)
        cr_resp = await _request_with_fallback(
            "GET", f"/repos/{owner}/{repo}/commits/{head_sha}/check-runs",
            headers=self._headers,
        )
        cr_resp.raise_for_status()
        check_runs = cr_resp.json().get("check_runs", [])

        # 3. Status (legacy / external CI integrations)
        st_resp = await _request_with_fallback(
            "GET", f"/repos/{owner}/{repo}/commits/{head_sha}/status",
            headers=self._headers,
        )
        st_resp.raise_for_status()
        status_data = st_resp.json()

        checks_compact = [
            {
                "name": cr.get("name"),
                "status": cr.get("status"),  # queued | in_progress | completed
                "conclusion": cr.get("conclusion"),  # success | failure | etc
                "html_url": cr.get("html_url"),
                "started_at": cr.get("started_at"),
                "completed_at": cr.get("completed_at"),
            }
            for cr in check_runs
        ]

        # Calcula estado agregado
        if not check_runs and not status_data.get("statuses"):
            state = "neutral"  # sem CI configurado
        elif any(c["conclusion"] == "failure" for c in checks_compact):
            state = "failure"
        elif any(
            c["status"] in ("queued", "in_progress") for c in checks_compact
        ):
            state = "pending"
        elif all(
            c["conclusion"] in ("success", "skipped", "neutral")
            for c in checks_compact
        ):
            state = "success"
        else:
            state = status_data.get("state", "neutral")

        return {
            "head_sha": head_sha,
            "state": state,
            "total_count": len(check_runs),
            "checks": checks_compact,
            "legacy_status": status_data.get("state"),
        }

    async def merge_pull_request(
        self,
        owner: str,
        repo: str,
        number: int,
        merge_method: str = "squash",
        commit_title: str | None = None,
    ) -> dict[str, Any]:
        """Faz merge de um PR via PUT /repos/{owner}/{repo}/pulls/{number}/merge.

        Args:
            owner: Dono do repositório (usuário ou org).
            repo: Nome do repositório.
            number: Número do PR a ser mergeado.
            merge_method: Estratégia de merge — 'squash', 'merge' ou 'rebase'.
                          Default: 'squash'.
            commit_title: Título opcional do commit de merge.

        Returns:
            Dict com a resposta da GitHub API (sha, merged, message).

        Raises:
            httpx.HTTPStatusError: Se a API retornar status >= 400.
        """
        payload: dict[str, Any] = {"merge_method": merge_method}
        if commit_title is not None:
            payload["commit_title"] = commit_title
        resp = await _request_with_fallback(
            "PUT", f"/repos/{owner}/{repo}/pulls/{number}/merge",
            headers=self._headers, json=payload,
        )
        if resp.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"GitHub API erro {resp.status_code}: {resp.text[:500]}",
                request=resp.request,
                response=resp,
            )
        return resp.json()
    async def get_pull_request(
        self, owner: str, repo: str, number: int
    ) -> dict[str, Any]:
        """Retorna metadados de um PR: title, body, state, draft, head_ref,
        base_ref, mergeable, additions, deletions, changed_files."""
        resp = await _request_with_fallback(
            "GET", f"/repos/{owner}/{repo}/pulls/{number}", headers=self._headers,
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "title": data.get("title"),
            "body": data.get("body"),
            "state": data.get("state"),
            "draft": data.get("draft", False),
            "head_ref": data["head"]["ref"],
            "base_ref": data["base"]["ref"],
            "mergeable": data.get("mergeable"),
            "additions": data.get("additions"),
            "deletions": data.get("deletions"),
            "changed_files": data.get("changed_files"),
        }

    async def list_pull_request_files(
        self, owner: str, repo: str, number: int
    ) -> list[dict[str, Any]]:
        """Retorna lista de arquivos alterados no PR.

        Cada item contém: filename, status, additions, deletions e patch
        truncado em 8 KB por arquivo (para evitar payloads gigantes).
        Pagina automaticamente até 300 arquivos (3 páginas de 100).
        """
        patch_limit = 8 * 1024  # 8 KB por arquivo
        max_pages = 3
        files: list[dict[str, Any]] = []
        for page in range(1, max_pages + 1):
            resp = await _request_with_fallback(
                "GET", f"/repos/{owner}/{repo}/pulls/{number}/files",
                headers=self._headers,
                params={"per_page": 100, "page": page},
            )
            resp.raise_for_status()
            batch = resp.json()
            for item in batch:
                patch = item.get("patch", "") or ""
                if len(patch) > patch_limit:
                    patch = patch[:patch_limit] + "\n... [patch truncado em 8 KB]"
                files.append(
                    {
                        "filename": item.get("filename"),
                        "status": item.get("status"),
                        "additions": item.get("additions"),
                        "deletions": item.get("deletions"),
                        "patch": patch,
                    }
                )
            if len(batch) < 100:
                break
        return files

    async def list_pull_request_reviews(
        self, owner: str, repo: str, number: int
    ) -> list[dict[str, Any]]:
        """Lista reviews submetidas no PR (APPROVE, REQUEST_CHANGES, COMMENT).

        Retorna lista ordenada cronologicamente. Cada item contém:
        ``id``, ``user_login``, ``state``, ``body``, ``submitted_at``.
        """
        resp = await _request_with_fallback(
            "GET", f"/repos/{owner}/{repo}/pulls/{number}/reviews",
            headers=self._headers, params={"per_page": 100},
        )
        resp.raise_for_status()
        data = resp.json()
        return [
            {
                "id": item.get("id"),
                "user_login": (item.get("user") or {}).get("login"),
                "state": item.get("state"),
                "body": item.get("body", "") or "",
                "submitted_at": item.get("submitted_at"),
            }
            for item in data
        ]

    async def list_pull_request_review_comments(
        self, owner: str, repo: str, number: int
    ) -> list[dict[str, Any]]:
        """Lista comentários *inline* de review (com path + linha).

        Diferente dos comentários gerais da issue, são os comentários presos
        a linhas específicas do diff. Retorna ``path``, ``line``, ``body``,
        ``user_login``, ``in_reply_to_id`` (None se thread root), ``side``.
        Pagina automaticamente até 300 comentários (3 páginas de 100).
        """
        max_pages = 3
        body_limit = 4 * 1024  # 4 KB por comentário
        comments: list[dict[str, Any]] = []
        for page in range(1, max_pages + 1):
            resp = await _request_with_fallback(
                "GET", f"/repos/{owner}/{repo}/pulls/{number}/comments",
                headers=self._headers,
                params={"per_page": 100, "page": page},
            )
            resp.raise_for_status()
            batch = resp.json()
            for item in batch:
                body = item.get("body", "") or ""
                if len(body) > body_limit:
                    body = body[:body_limit] + "\n... [body truncado em 4 KB]"
                comments.append(
                    {
                        "id": item.get("id"),
                        "user_login": (item.get("user") or {}).get("login"),
                        "path": item.get("path"),
                        "line": item.get("line") or item.get("original_line"),
                        "side": item.get("side"),
                        "body": body,
                        "in_reply_to_id": item.get("in_reply_to_id"),
                    }
                )
            if len(batch) < 100:
                break
        return comments

    async def close_pull_request(
        self, owner: str, repo: str, number: int
    ) -> dict[str, Any]:
        """Fecha PR sem mergeai (util pra testes/cleanup)."""
        resp = await _request_with_fallback(
            "PATCH", f"/repos/{owner}/{repo}/pulls/{number}",
            headers=self._headers, json={"state": "closed"},
        )
        resp.raise_for_status()
        return resp.json()

    async def create_pull_request_review(
        self,
        owner: str,
        repo: str,
        number: int,
        event: str,
        body: str,
        comments: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Submete uma review num PR via POST /repos/{owner}/{repo}/pulls/{number}/reviews.

        Args:
            owner:    Dono do repositório (usuário ou organização).
            repo:     Nome do repositório.
            number:   Número do Pull Request.
            event:    Ação da review — um de 'APPROVE', 'REQUEST_CHANGES' ou 'COMMENT'.
            body:     Comentário geral da review.
            comments: Lista opcional de comentários inline. Cada item deve conter
                      pelo menos ``path``, ``position`` (ou ``line``) e ``body``.

        Returns:
            dict com o payload JSON retornado pela API do GitHub.

        Raises:
            ValueError: se ``event`` não for um valor permitido.
            httpx.HTTPStatusError: se a API retornar status >= 400.
        """
        allowed_events = {"APPROVE", "REQUEST_CHANGES", "COMMENT"}
        if event not in allowed_events:
            raise ValueError(
                f"event invalido: '{event}'. Deve ser um de {sorted(allowed_events)}."
            )

        payload: dict[str, Any] = {"event": event, "body": body}
        if comments:
            payload["comments"] = comments

        resp = await _request_with_fallback(
            "POST", f"/repos/{owner}/{repo}/pulls/{number}/reviews",
            headers=self._headers, json=payload,
        )
        if resp.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"GitHub API erro {resp.status_code}: {resp.text[:500]}",
                request=resp.request,
                response=resp,
            )
        return resp.json()
