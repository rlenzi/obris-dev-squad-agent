"""Git worktree manager: clone cached + worktree descartavel por execucao.

Por que worktrees descartaveis:
- Multiplos agentes podem trabalhar no mesmo repo em paralelo sem colisao.
- Cada task tem seu working dir isolado.
- Limpo no fim da execucao; sem state vazando entre tasks.

Estrutura no filesystem:
  $cache_root/
    <client_id>/
      <repo_slug>.git/         <-- bare clone cached (atualizado via fetch)
      worktrees/
        <task_id_or_uuid>/     <-- worktree descartavel por execucao
"""

from __future__ import annotations

import asyncio
import logging
import shutil
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse
from uuid import UUID

from dev_autonomo.common.repos import normalize_repo_id

logger = logging.getLogger(__name__)


class GitOperationError(RuntimeError):
    pass


@dataclass(slots=True)
class CheckedOutWorktree:
    """Resultado de checkout_for_task: caminho + metadata."""

    path: Path
    repo_url: str
    repo_slug: str
    branch: str
    base_branch: str
    client_id: UUID
    task_handle: str

    async def cleanup(self) -> None:
        """Remove o worktree do filesystem e da lista de worktrees do bare repo."""
        if not self.path.exists():
            return
        # `git worktree remove --force` precisa rodar de DENTRO do bare ou apontar
        # diretamente o path. Tentamos a forma mais segura: shutil + prune.
        await _run_git(self.path, ["status"], check=False)  # noop, validacao
        # Remove fisicamente
        shutil.rmtree(self.path, ignore_errors=True)
        # Limpa a registry do bare
        bare = self.path.parent.parent / f"{self.repo_slug}.git"
        if bare.exists():
            await _run_git(bare, ["worktree", "prune"], check=False)


async def _run_git(
    cwd: Path, args: list[str], *, env: dict[str, str] | None = None, check: bool = True
) -> tuple[int, str, str]:
    import os

    proc_env = os.environ.copy()
    if env:
        proc_env.update(env)
    proc = await asyncio.create_subprocess_exec(
        "git",
        *args,
        cwd=str(cwd),
        env=proc_env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    out = stdout.decode("utf-8", errors="replace")
    err = stderr.decode("utf-8", errors="replace")
    if check and proc.returncode != 0:
        raise GitOperationError(
            f"git {' '.join(args)} falhou (rc={proc.returncode}): {err.strip() or out.strip()}"
        )
    return proc.returncode or 0, out, err


def _extract_owner_repo(repo_url: str) -> tuple[str, str]:
    """Extrai (owner, repo) de URL do GitHub. Aceita HTTPS e SSH."""
    s = repo_url.strip().rstrip("/")
    if s.endswith(".git"):
        s = s[:-4]
    if s.startswith("git@"):
        # git@github.com:owner/repo
        path = s.split(":", 1)[1]
    else:
        parsed = urlparse(s)
        path = parsed.path.lstrip("/")
    parts = path.split("/")
    if len(parts) < 2:
        raise ValueError(f"URL invalido: {repo_url}")
    return parts[-2], parts[-1]


class GitWorktreeManager:
    """Gerencia clones bare cached e worktrees descartaveis por task."""

    def __init__(self, cache_root: Path) -> None:
        self.cache_root = cache_root
        self.cache_root.mkdir(parents=True, exist_ok=True)

    def bare_path(self, client_id: UUID, repo_url: str) -> Path:
        slug = normalize_repo_id(repo_url)
        return self.cache_root / str(client_id) / f"{slug}.git"

    def worktrees_dir(self, client_id: UUID, repo_url: str) -> Path:
        return self.cache_root / str(client_id) / "worktrees" / normalize_repo_id(repo_url)

    async def _ensure_bare(
        self, client_id: UUID, repo_url: str, *, github_token: str | None
    ) -> Path:
        """Garante que existe um bare clone atualizado pro repo."""
        bare = self.bare_path(client_id, repo_url)
        bare.parent.mkdir(parents=True, exist_ok=True)
        auth_url = repo_url
        if github_token and repo_url.startswith("https://"):
            # injeta token na URL pra clone/fetch autenticado
            auth_url = repo_url.replace(
                "https://", f"https://x-access-token:{github_token}@", 1
            )
        if not bare.exists():
            logger.info("Clonando bare repo: %s -> %s", repo_url, bare)
            await _run_git(
                bare.parent,
                ["clone", "--bare", auth_url, bare.name],
                env={"GIT_TERMINAL_PROMPT": "0"},
            )
        else:
            logger.info("Atualizando bare repo cached: %s", bare)
            # Define URL temporariamente com auth pro fetch
            if github_token and auth_url != repo_url:
                await _run_git(bare, ["remote", "set-url", "origin", auth_url], check=False)
            await _run_git(bare, ["fetch", "--prune", "origin"], env={"GIT_TERMINAL_PROMPT": "0"})
            # Reset URL sem token (nao queremos token persistido no .git/config)
            if github_token and auth_url != repo_url:
                await _run_git(bare, ["remote", "set-url", "origin", repo_url], check=False)
        return bare

    async def checkout_for_task(
        self,
        *,
        client_id: UUID,
        repo_url: str,
        task_handle: str,
        new_branch: str,
        base_branch: str | None = None,
        github_token: str | None = None,
    ) -> CheckedOutWorktree:
        """Cria um worktree fresco a partir do bare clone, em uma nova branch."""
        bare = await self._ensure_bare(client_id, repo_url, github_token=github_token)
        slug = normalize_repo_id(repo_url)

        # Descobre default branch se nao foi passado
        if base_branch is None:
            rc, out, _ = await _run_git(bare, ["symbolic-ref", "HEAD"], check=False)
            if rc == 0 and out.strip():
                base_branch = out.strip().split("/")[-1]
            else:
                base_branch = "main"

        wt_root = self.worktrees_dir(client_id, repo_url)
        wt_root.mkdir(parents=True, exist_ok=True)
        # Limpa qualquer worktree antigo com mesmo handle
        wt_path = wt_root / task_handle
        if wt_path.exists():
            shutil.rmtree(wt_path, ignore_errors=True)
            await _run_git(bare, ["worktree", "prune"], check=False)

        # Cria worktree a partir do base branch remoto
        logger.info(
            "Criando worktree: bare=%s path=%s branch=%s base=origin/%s",
            bare,
            wt_path,
            new_branch,
            base_branch,
        )
        await _run_git(
            bare,
            ["worktree", "add", "-b", new_branch, str(wt_path), base_branch],
        )
        # Configura identidade do git no worktree
        await _run_git(wt_path, ["config", "user.name", "obris-agent"], check=False)
        await _run_git(
            wt_path, ["config", "user.email", "agent@dev-autonomo.local"], check=False
        )
        # Configura remote URL com token pra futuros push (descartado junto com worktree)
        if github_token and repo_url.startswith("https://"):
            auth_url = repo_url.replace(
                "https://", f"https://x-access-token:{github_token}@", 1
            )
            await _run_git(wt_path, ["remote", "set-url", "origin", auth_url], check=False)

        return CheckedOutWorktree(
            path=wt_path,
            repo_url=repo_url,
            repo_slug=slug,
            branch=new_branch,
            base_branch=base_branch,
            client_id=client_id,
            task_handle=task_handle,
        )
