"""Cliente HTTP do GitHub API. Token vem do vault do cliente."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

GITHUB_API = "https://api.github.com"
DEFAULT_TIMEOUT = 30.0


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
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            resp = await client.get(
                f"{GITHUB_API}/repos/{owner}/{repo}", headers=self._headers
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
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            resp = await client.post(
                f"{GITHUB_API}/repos/{owner}/{repo}/pulls",
                headers=self._headers,
                json=payload,
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

    async def close_pull_request(
        self, owner: str, repo: str, number: int
    ) -> dict[str, Any]:
        """Fecha PR sem mergeai (util pra testes/cleanup)."""
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            resp = await client.patch(
                f"{GITHUB_API}/repos/{owner}/{repo}/pulls/{number}",
                headers=self._headers,
                json={"state": "closed"},
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

        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            resp = await client.post(
                f"{GITHUB_API}/repos/{owner}/{repo}/pulls/{number}/reviews",
                headers=self._headers,
                json=payload,
            )
            if resp.status_code >= 400:
                raise httpx.HTTPStatusError(
                    f"GitHub API erro {resp.status_code}: {resp.text[:500]}",
                    request=resp.request,
                    response=resp,
                )
            return resp.json()
