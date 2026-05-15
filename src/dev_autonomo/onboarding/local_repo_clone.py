"""Clone local de repos pra ingest da RAG durante onboarding_analyzer v2.

Cada clone fica isolado em {CLONE_BASE_DIR}/{client_id}/{task_id}/ — tenant
isolation por filesystem. Backend gerencia clone + cleanup; o sandbox da
Anthropic Managed Agent clona o mesmo repo separadamente (via
github_repository resource) — preocupacoes separadas, sem
acoplamento implicito de filesystem.

Erros de clone sao tipados via CloneError com causa especifica (auth,
not_found, network, generic) pra que o orquestrador possa decidir o que
fazer (retentar com token novo, abortar, marcar task FAILED com motivo).
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from dev_autonomo.config import get_settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class CloneError(Exception):
    """Erro de clone com causa estruturada."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason
        self.detail = detail


class CloneAuthError(CloneError):
    """Token ausente, recusado, ou sem permissao no repo."""


class CloneNotFoundError(CloneError):
    """Repo nao existe na URL fornecida."""


class CloneNetworkError(CloneError):
    """Falha de rede / DNS / timeout."""


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class CloneResult:
    """Resultado de um clone bem-sucedido."""

    path: Path
    commit_hash: str
    default_branch: str
    size_bytes: int


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def get_clone_path(client_id: UUID, task_id: UUID) -> Path:
    """Monta o path canonical pro clone dessa task.

    Estrutura: {CLONE_BASE_DIR}/{client_id}/{task_id}/

    CLONE_BASE_DIR vem da settings (default ~/.local/share/dev-autonomo/
    clones). Expansao de ~ acontece aqui pra normalizar.
    """
    base = Path(get_settings().CLONE_BASE_DIR).expanduser().resolve()
    return base / str(client_id) / str(task_id)


def ensure_parent_exists(path: Path) -> None:
    """Cria diretorios ancestrais com permissao restritiva (700)."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)


# ---------------------------------------------------------------------------
# Clone + cleanup
# ---------------------------------------------------------------------------


async def clone_repo(
    *,
    repo_url: str,
    target_path: Path,
    github_token: str | None = None,
    branch: str | None = None,
    depth: int | None = 1,
    timeout_seconds: int = 300,
) -> CloneResult:
    """Clona um repo Git pro target_path.

    Args:
        repo_url: URL HTTPS do repo (ex: https://github.com/owner/repo).
            Sem sufixo .git eh aceito; sera adicionado automaticamente.
        target_path: diretorio destino (deve nao existir; sera criado).
        github_token: opcional, usado em https://x-access-token:TOKEN@...
            quando o repo eh privado. None pra repos publicos.
        branch: opcional, --branch <name>. None = default branch.
        depth: shallow clone com --depth N. None = clone completo.
            Default 1 (so o tip, suficiente pra OA scan + RAG ingest).
        timeout_seconds: limite de tempo pro processo git.

    Returns:
        CloneResult com path, commit_hash, default_branch, size.

    Raises:
        CloneAuthError: 401/403 do GitHub (token ruim, repo privado).
        CloneNotFoundError: 404 do GitHub.
        CloneNetworkError: timeout, DNS, conexao recusada.
        CloneError: outros erros (ex: ref nao existe).
    """
    if target_path.exists():
        raise CloneError(
            "target_path_exists",
            f"diretorio destino ja existe: {target_path}. Cleanup primeiro.",
        )
    ensure_parent_exists(target_path)

    # Monta URL com token inline se for privado. Token nao fica no log.
    clone_url = repo_url.rstrip("/")
    if clone_url.endswith(".git"):
        clone_url = clone_url[:-4]
    if github_token:
        if not clone_url.startswith("https://"):
            raise CloneError(
                "unsupported_url_scheme",
                "token so eh suportado em https://github.com/... URLs",
            )
        # injecao do token apos o esquema: https://x-access-token:TOKEN@github.com/...
        clone_url = clone_url.replace(
            "https://", f"https://x-access-token:{github_token}@", 1,
        )

    cmd = ["git", "clone"]
    if depth is not None:
        cmd.extend(["--depth", str(depth)])
    if branch is not None:
        cmd.extend(["--branch", branch])
    cmd.extend([clone_url, str(target_path)])

    # Logging com URL sanitizada (sem token)
    safe_url = repo_url.rstrip("/").removesuffix(".git")
    logger.info(
        "clone_repo: iniciando target=%s url=%s branch=%s depth=%s",
        target_path, safe_url, branch or "<default>", depth,
    )

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=timeout_seconds,
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            raise CloneNetworkError(
                "timeout",
                f"git clone passou de {timeout_seconds}s",
            ) from None

        stderr_text = stderr_bytes.decode("utf-8", errors="replace")
    except FileNotFoundError as exc:
        raise CloneError(
            "git_not_installed",
            "binario 'git' nao encontrado no PATH",
        ) from exc

    if proc.returncode != 0:
        _raise_classified_error(stderr_text)

    # Coleta metadata do clone
    commit_hash = await _git_rev_parse(target_path, "HEAD")
    default_branch = await _git_default_branch(target_path)
    size_bytes = _dir_size_bytes(target_path)

    logger.info(
        "clone_repo: OK target=%s commit=%s branch=%s size=%d MB",
        target_path, commit_hash[:10], default_branch, size_bytes // (1024 * 1024),
    )

    return CloneResult(
        path=target_path,
        commit_hash=commit_hash,
        default_branch=default_branch,
        size_bytes=size_bytes,
    )


def cleanup_clone(target_path: Path) -> None:
    """Remove o diretorio do clone. Idempotente — nao falha se ja foi.

    Usar SEMPRE em ``finally`` block, mesmo apos erro em etapas seguintes.
    """
    if not target_path.exists():
        logger.debug("cleanup_clone: %s ja inexistente, skip", target_path)
        return
    try:
        shutil.rmtree(target_path)
        logger.info("cleanup_clone: removido %s", target_path)
    except OSError as exc:
        # Nao deixar erro de cleanup esconder erro real anterior. Log e segue.
        logger.warning(
            "cleanup_clone: falha removendo %s: %s — diretorio pode ficar orfao",
            target_path, exc,
        )

    # Tenta limpar tambem o parent (diretorio do client) se ficou vazio.
    # Importante pra nao manter pasta vazia por cliente que nao tem mais clones.
    parent = target_path.parent
    try:
        if parent.exists() and not any(parent.iterdir()):
            parent.rmdir()
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _raise_classified_error(stderr: str) -> None:
    """Mapeia stderr do git pra exception tipada."""
    msg = stderr.lower()

    # Ordem dos checks importa: auth/not_found podem aparecer juntos
    if "could not resolve host" in msg or "name or service not known" in msg:
        raise CloneNetworkError("dns_failure", stderr[:300])
    if "connection refused" in msg or "operation timed out" in msg:
        raise CloneNetworkError("connection_failed", stderr[:300])
    if "fatal: authentication failed" in msg or "invalid username" in msg:
        raise CloneAuthError("auth_failed", stderr[:300])
    if "could not read username" in msg:
        raise CloneAuthError("auth_required", stderr[:300])
    if "repository not found" in msg or "remote: not found" in msg:
        raise CloneNotFoundError("repo_not_found", stderr[:300])
    if "remote branch" in msg and "not found" in msg:
        raise CloneError("branch_not_found", stderr[:300])

    raise CloneError("clone_failed", stderr[:300])


async def _git_rev_parse(repo: Path, ref: str) -> str:
    """Roda git rev-parse {ref} no repo."""
    proc = await asyncio.create_subprocess_exec(
        "git", "-C", str(repo), "rev-parse", ref,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise CloneError(
            "git_rev_parse_failed",
            stderr.decode("utf-8", errors="replace")[:200],
        )
    return stdout.decode("utf-8").strip()


async def _git_default_branch(repo: Path) -> str:
    """Detecta a branch checkada (HEAD symbolic ref)."""
    proc = await asyncio.create_subprocess_exec(
        "git", "-C", str(repo), "symbolic-ref", "--short", "HEAD",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        # Detached HEAD (raro em shallow clone padrao mas possivel)
        return "HEAD"
    return stdout.decode("utf-8").strip()


def _dir_size_bytes(path: Path) -> int:
    """Soma tamanho de todos arquivos recursivamente. Pula symlinks."""
    total = 0
    for entry in path.rglob("*"):
        if entry.is_file() and not entry.is_symlink():
            try:
                total += entry.stat().st_size
            except OSError:
                continue
    return total
