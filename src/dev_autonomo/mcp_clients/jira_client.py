"""Cliente HTTP do Jira Cloud REST API v3.

Autenticacao Basic com email + API token. Documentation root:
https://developer.atlassian.com/cloud/jira/platform/rest/v3/
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Any

import httpx

DEFAULT_TIMEOUT = 30.0


@dataclass(slots=True)
class JiraIssue:
    key: str
    summary: str
    status: str
    issue_type: str
    description_text: str
    assignee: str | None
    raw: dict[str, Any]


@dataclass(slots=True)
class JiraTransition:
    id: str
    name: str
    target_status: str


@dataclass(slots=True)
class JiraComment:
    id: str
    author: str
    body_text: str
    created: str


class JiraClient:
    """Cliente fino do Jira Cloud REST API v3."""

    def __init__(self, *, base_url: str, email: str, api_token: str) -> None:
        self._base_url = base_url.rstrip("/")
        auth_bytes = f"{email}:{api_token}".encode()
        self._auth_header = "Basic " + base64.b64encode(auth_bytes).decode("ascii")
        self._headers = {
            "Authorization": self._auth_header,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    # ---- Issues ----

    async def get_issue(self, key: str) -> JiraIssue:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            resp = await client.get(
                f"{self._base_url}/rest/api/3/issue/{key}",
                headers=self._headers,
                params={"fields": "summary,status,issuetype,description,assignee"},
            )
            resp.raise_for_status()
            data = resp.json()
            fields = data.get("fields", {}) or {}
            return JiraIssue(
                key=data["key"],
                summary=fields.get("summary", ""),
                status=(fields.get("status") or {}).get("name", "Unknown"),
                issue_type=(fields.get("issuetype") or {}).get("name", "Unknown"),
                description_text=_adf_to_text(fields.get("description")),
                assignee=((fields.get("assignee") or {}) or {}).get("displayName"),
                raw=data,
            )

    # ---- Comments ----

    async def add_comment(self, key: str, body_text: str) -> JiraComment:
        payload = {"body": _text_to_adf(body_text)}
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            resp = await client.post(
                f"{self._base_url}/rest/api/3/issue/{key}/comment",
                headers=self._headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            return JiraComment(
                id=data["id"],
                author=(data.get("author") or {}).get("displayName", "?"),
                body_text=body_text,
                created=data.get("created", ""),
            )

    # ---- Transitions ----

    async def list_transitions(self, key: str) -> list[JiraTransition]:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            resp = await client.get(
                f"{self._base_url}/rest/api/3/issue/{key}/transitions",
                headers=self._headers,
            )
            resp.raise_for_status()
            data = resp.json()
            out: list[JiraTransition] = []
            for t in data.get("transitions", []):
                out.append(
                    JiraTransition(
                        id=t["id"],
                        name=t["name"],
                        target_status=(t.get("to") or {}).get("name", "?"),
                    )
                )
            return out

    async def execute_transition(self, key: str, transition_id: str) -> None:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            resp = await client.post(
                f"{self._base_url}/rest/api/3/issue/{key}/transitions",
                headers=self._headers,
                json={"transition": {"id": transition_id}},
            )
            resp.raise_for_status()

    async def transition_to_status(self, key: str, target_status: str) -> str | None:
        """Procura transition cujo target status bate (case-insensitive) e executa.

        Retorna o nome da transition executada ou None se nenhuma achou.
        """
        wanted = target_status.lower().strip()
        transitions = await self.list_transitions(key)
        match = next(
            (
                t
                for t in transitions
                if t.target_status.lower() == wanted or t.name.lower() == wanted
            ),
            None,
        )
        if match is None:
            return None
        await self.execute_transition(key, match.id)
        return match.name

    # ---- Subtask ----

    async def create_subtask(
        self,
        *,
        parent_key: str,
        project_key: str,
        summary: str,
        description_text: str | None = None,
    ) -> JiraIssue:
        payload: dict[str, Any] = {
            "fields": {
                "project": {"key": project_key},
                "summary": summary,
                "issuetype": {"name": "Subtarefa"},
                "parent": {"key": parent_key},
            }
        }
        if description_text:
            payload["fields"]["description"] = _text_to_adf(description_text)

        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            resp = await client.post(
                f"{self._base_url}/rest/api/3/issue",
                headers=self._headers,
                json=payload,
            )
            if resp.status_code >= 400:
                raise httpx.HTTPStatusError(
                    f"Jira create subtask falhou ({resp.status_code}): {resp.text[:500]}",
                    request=resp.request,
                    response=resp,
                )
            data = resp.json()
            # Retorna versão completa
            return await self.get_issue(data["key"])


# ---- Helpers de ADF (Atlassian Document Format) ----


def _text_to_adf(text: str) -> dict[str, Any]:
    """Converte texto simples (com quebra de linhas) para ADF minimo."""
    paragraphs = text.split("\n\n")
    content = []
    for para in paragraphs:
        if not para.strip():
            continue
        content.append(
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": para}],
            }
        )
    return {"type": "doc", "version": 1, "content": content}


def _adf_to_text(adf: dict[str, Any] | None) -> str:
    """Extrai texto plano de um ADF. Best-effort para campos description."""
    if not adf:
        return ""
    if isinstance(adf, str):
        return adf
    out: list[str] = []
    for block in adf.get("content", []) or []:
        text = _adf_block_to_text(block)
        if text:
            out.append(text)
    return "\n\n".join(out).strip()


def _adf_block_to_text(block: dict[str, Any]) -> str:
    btype = block.get("type")
    if btype == "text":
        return block.get("text", "")
    if btype in ("paragraph", "heading", "blockquote"):
        return "".join(_adf_block_to_text(c) for c in block.get("content", []) or [])
    if btype == "bulletList":
        items = [
            "- " + _adf_block_to_text(li) for li in block.get("content", []) or []
        ]
        return "\n".join(items)
    if btype == "listItem":
        return "".join(_adf_block_to_text(c) for c in block.get("content", []) or [])
    if btype == "hardBreak":
        return "\n"
    # Outros tipos (codeBlock, table, etc): tenta recursivo
    if "content" in block:
        return "".join(_adf_block_to_text(c) for c in block.get("content", []) or [])
    return ""
