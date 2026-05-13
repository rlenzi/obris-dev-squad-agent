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

    async def get_pull_request(
        self, owner: str, repo: str, number: int
    ) -> dict[str, Any]:
        """Retorna metadados de um PR: title, body, state, draft, head_ref,
        base_ref, mergeable, additions, deletions, changed_files."""
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            resp = await client.get(
                f"{GITHUB_API}/repos/{owner}/{repo}/pulls/{number}",
                headers=self._headers,
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
        _PATCH_LIMIT = 8 * 1024  # 8 KB por arquivo
        _MAX_PAGES = 3
        files: list[dict[str, Any]] = []
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            for page in range(1, _MAX_PAGES + 1):
                resp = await client.get(
                    f"{GITHUB_API}/repos/{owner}/{repo}/pulls/{number}/files",
                    headers=self._headers,
                    params={"per_page": 100, "page": page},
                )
                resp.raise_for_status()
                batch = resp.json()
                for item in batch:
                    patch = item.get("patch", "") or ""
                    if len(patch) > _PATCH_LIMIT:
                        patch = patch[:_PATCH_LIMIT] + "\n... [patch truncado em 8 KB]"
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
