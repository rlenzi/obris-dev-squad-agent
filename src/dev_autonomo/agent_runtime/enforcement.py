"""ManifestEnforcer: camada 3 da defesa em profundidade.

Toda tool call do agente passa por aqui antes de executar. Compara o recurso
(file path, repo, schema, event topic) contra o manifest da squad. Resultado:
- allowed=True com regra matched, OU
- allowed=False com sugestao (geralmente: use create_cross_squad_request).

Toda tentativa eh gravada em tool_authorization_attempts (auditoria + telemetria
para tunar manifestos).
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dev_autonomo.common.repos import normalize_repo_id
from dev_autonomo.db.models import Manifest, Squad
from dev_autonomo.db.models.audit import ToolAuthorizationAttempt


@dataclass(slots=True)
class AuthorizationResult:
    allowed: bool
    reason: str  # 'owned' | 'owned_module' | 'out_of_scope' | 'no_manifest' | 'unknown_resource'
    matched_rule: str | None = None
    suggestion: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "matched_rule": self.matched_rule,
            "suggestion": self.suggestion,
        }


CROSS_SQUAD_HINT = (
    "este recurso pertence a outra squad ou nao esta declarado no manifest. "
    "Use a tool create_cross_squad_request para pedir mudanca formalmente."
)

CONFIGURE_MANIFEST_HINT = (
    "squad ainda nao tem manifest ativo. SYSTEM_ADMIN precisa criar um "
    "via PUT /client/squads/{id}/manifest antes do agente operar."
)


class ManifestNotFoundError(LookupError):
    pass


class ManifestEnforcer:
    """Aplica policy do manifest da squad em cada tool call.

    Carrega o manifest uma vez por instancia (use uma per task/run para
    pegar updates entre execucoes).
    """

    def __init__(
        self,
        *,
        session: AsyncSession,
        client_id: UUID,
        squad_id: UUID,
        agent_instance_id: UUID | None = None,
        task_id: UUID | None = None,
    ) -> None:
        self._session = session
        self.client_id = client_id
        self.squad_id = squad_id
        self.agent_instance_id = agent_instance_id
        self.task_id = task_id
        self._manifest: Manifest | None = None
        self._manifest_loaded = False

    async def _load_manifest(self) -> Manifest | None:
        if self._manifest_loaded:
            return self._manifest
        stmt = (
            select(Manifest)
            .join(Squad, Squad.current_manifest_id == Manifest.id)
            .where(Squad.id == self.squad_id)
        )
        result = await self._session.execute(stmt)
        self._manifest = result.scalar_one_or_none()
        self._manifest_loaded = True
        return self._manifest

    # ---- Checks publicos ----

    async def check_repo(self, repo: str) -> AuthorizationResult:
        """Squad pode operar git neste repo? (clone, push, branch)."""
        manifest = await self._load_manifest()
        if manifest is None:
            return self._no_manifest_result()

        owns = (manifest.content or {}).get("owns", {})
        owned_repos = [normalize_repo_id(r) for r in owns.get("repos", [])]
        target = normalize_repo_id(repo)
        if target in owned_repos:
            return AuthorizationResult(
                True, "owned", matched_rule=f"owns.repos:{target}"
            )
        return AuthorizationResult(
            False,
            "out_of_scope",
            suggestion=f"repo '{repo}' nao esta em owns.repos. " + CROSS_SQUAD_HINT,
        )

    async def check_edit_file(self, repo: str, file_path: str) -> AuthorizationResult:
        """Editar arquivo: repo deve estar owned, ou path em modules_in_shared_repos."""
        manifest = await self._load_manifest()
        if manifest is None:
            return self._no_manifest_result()

        owns = (manifest.content or {}).get("owns", {})
        norm_repo = normalize_repo_id(repo)

        # 1. Repo owned diretamente
        for owned in owns.get("repos", []):
            if normalize_repo_id(owned) == norm_repo:
                return AuthorizationResult(
                    True, "owned", matched_rule=f"owns.repos:{norm_repo}"
                )

        # 2. Pattern em shared repo
        full_path = f"{norm_repo}/{file_path.lstrip('/')}"
        for pattern in owns.get("modules_in_shared_repos", []):
            if fnmatch.fnmatchcase(full_path, pattern):
                return AuthorizationResult(
                    True,
                    "owned_module",
                    matched_rule=f"owns.modules_in_shared_repos:{pattern}",
                )

        return AuthorizationResult(
            False,
            "out_of_scope",
            suggestion=(
                f"path '{file_path}' em repo '{repo}' nao esta no escopo. "
                + CROSS_SQUAD_HINT
            ),
        )

    async def check_db_schema(self, schema_name: str) -> AuthorizationResult:
        manifest = await self._load_manifest()
        if manifest is None:
            return self._no_manifest_result()
        owns = (manifest.content or {}).get("owns", {})
        db_owns = owns.get("database", {}) or owns.get("database_schemas", [])
        # database pode ser dict {"schemas": [...]} ou lista direta
        schemas: list[str] = []
        if isinstance(db_owns, dict):
            schemas = list(db_owns.get("schemas", []))
        elif isinstance(db_owns, list):
            schemas = list(db_owns)
        # Usa fnmatch (glob) com comparacao case-insensitive, igualando o
        # comportamento de check_event_publish e check_api_publish.
        # Ex: "pay_*" autoriza "pay_charges", "*" autoriza qualquer schema.
        schema_lower = schema_name.lower()
        for pattern in schemas:
            if fnmatch.fnmatchcase(schema_lower, pattern.lower()):
                return AuthorizationResult(
                    True, "owned", matched_rule=f"owns.database:{pattern}"
                )
        return AuthorizationResult(
            False,
            "out_of_scope",
            suggestion=f"schema '{schema_name}' fora do escopo. " + CROSS_SQUAD_HINT,
        )

    async def check_event_publish(self, topic: str) -> AuthorizationResult:
        manifest = await self._load_manifest()
        if manifest is None:
            return self._no_manifest_result()
        owns = (manifest.content or {}).get("owns", {})
        publishes = (owns.get("events", {}) or {}).get("publishes", [])
        for pattern in publishes:
            if fnmatch.fnmatchcase(topic, pattern):
                return AuthorizationResult(
                    True, "owned", matched_rule=f"owns.events.publishes:{pattern}"
                )
        return AuthorizationResult(
            False,
            "out_of_scope",
            suggestion=f"topic '{topic}' nao esta em owns.events.publishes. "
            + CROSS_SQUAD_HINT,
        )

    async def check_api_publish(self, route: str) -> AuthorizationResult:
        manifest = await self._load_manifest()
        if manifest is None:
            return self._no_manifest_result()
        owns = (manifest.content or {}).get("owns", {})
        publishes = (owns.get("apis", {}) or {}).get("publishes", [])
        for pattern in publishes:
            if fnmatch.fnmatchcase(route, pattern):
                return AuthorizationResult(
                    True, "owned", matched_rule=f"owns.apis.publishes:{pattern}"
                )
        return AuthorizationResult(
            False,
            "out_of_scope",
            suggestion=f"rota '{route}' nao esta em owns.apis.publishes. "
            + CROSS_SQUAD_HINT,
        )


    async def check_jira_project(self, project_key: str) -> AuthorizationResult:
        """Squad pode operar (ler/escrever) issues neste projeto Jira?"""
        manifest = await self._load_manifest()
        if manifest is None:
            return self._no_manifest_result()
        owns = (manifest.content or {}).get("owns", {})
        projects = owns.get("jira_projects", []) or []
        if project_key.upper() in [str(p).upper() for p in projects]:
            return AuthorizationResult(
                True, "owned", matched_rule=f"owns.jira_projects:{project_key}"
            )
        return AuthorizationResult(
            False,
            "out_of_scope",
            suggestion=f"projeto Jira '{project_key}' fora do escopo. "
            + CROSS_SQUAD_HINT,
        )

    # ---- Logging ----

    async def log(
        self,
        tool_name: str,
        resource: str,
        result: AuthorizationResult,
    ) -> ToolAuthorizationAttempt:
        """Persiste a tentativa em tool_authorization_attempts."""
        attempt = ToolAuthorizationAttempt(
            client_id=self.client_id,
            squad_id=self.squad_id,
            agent_instance_id=self.agent_instance_id,
            task_id=self.task_id,
            tool_name=tool_name,
            resource=resource,
            allowed=result.allowed,
            reason=result.reason,
            matched_rule=result.matched_rule,
            suggestion=result.suggestion,
        )
        self._session.add(attempt)
        await self._session.flush()
        return attempt

    async def authorize(
        self,
        tool_name: str,
        resource: str,
        result: AuthorizationResult,
    ) -> AuthorizationResult:
        """Conveniencia: loga a tentativa e retorna o resultado."""
        await self.log(tool_name, resource, result)
        return result

    # ---- Helpers ----

    def _no_manifest_result(self) -> AuthorizationResult:
        return AuthorizationResult(
            False, "no_manifest", suggestion=CONFIGURE_MANIFEST_HINT
        )
