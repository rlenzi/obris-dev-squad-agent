"""Schema da mensagem de reindex que trafega na fila RabbitMQ.

Define o contrato tipado entre o webhook de push e o worker de reindex
incremental do Knowledge Hub.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

# Nome da fila RabbitMQ usada para disparar jobs de reindex incremental.
REINDEX_QUEUE = "knowledge.reindex"


@dataclass(slots=True)
class ReindexMessage:
    """Mensagem publicada na fila ``knowledge.reindex`` após um push no GitHub.

    Campos
    ------
    client_id
        UUID do cliente dono do repositório.
    squad_id
        UUID da squad responsável pelo repositório.
    repo_label
        Rótulo curto do repositório — ex: ``"backend"``.
    repo_path
        Caminho absoluto local do repositório clonado no worker.
    commit_hash
        SHA do commit que disparou o evento de push.
    files
        Lista de caminhos relativos dos arquivos do diff
        (added + modified + removed).
    """

    client_id: UUID
    squad_id: UUID
    repo_label: str
    repo_path: str
    commit_hash: str
    files: list[str]

    # ------------------------------------------------------------------
    # Serialização / desserialização
    # ------------------------------------------------------------------

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReindexMessage":
        """Desserializa um ``dict`` (vindo da fila) para ``ReindexMessage``."""
        return cls(
            client_id=UUID(data["client_id"]),
            squad_id=UUID(data["squad_id"]),
            repo_label=data["repo_label"],
            repo_path=data["repo_path"],
            commit_hash=data["commit_hash"],
            files=list(data["files"]),
        )

    def to_dict(self) -> dict[str, Any]:
        """Serializa para ``dict`` pronto para publicação JSON na fila.

        ``UUID`` são convertidos para ``str`` para compatibilidade com JSON.
        """
        return {
            "client_id": str(self.client_id),
            "squad_id": str(self.squad_id),
            "repo_label": self.repo_label,
            "repo_path": self.repo_path,
            "commit_hash": self.commit_hash,
            "files": list(self.files),
        }
