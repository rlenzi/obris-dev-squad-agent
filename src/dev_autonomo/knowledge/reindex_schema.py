"""Schema da mensagem de reindexação incremental via RabbitMQ.

Define o contrato de dados publicado pelo webhook GitHub (push event)
e consumido pelo ReindexWorker.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

# Nome da fila durable onde as mensagens de reindexação são publicadas
REINDEX_QUEUE = "knowledge.reindex"


@dataclass(slots=True)
class ReindexMessage:
    """Payload normalizado de um evento de push do GitHub para reindexação.

    Campos
    ------
    client_id:
        UUID do cliente dono do repositório.
    squad_id:
        UUID da squad cujo Knowledge Hub será atualizado.
    repo_path:
        Caminho absoluto (no filesystem do worker) para o clone local do repo.
    repo_label:
        Identificador legível do repositório (ex: ``'obris-dev-squad-agent'``).
    files:
        Lista de caminhos relativos à raiz do repositório alterados no push.
    commit_hash:
        Hash do commit HEAD após o push (opcional, usado para rastreabilidade).
    """

    client_id: UUID
    squad_id: UUID
    repo_path: str
    repo_label: str
    files: list[str] = field(default_factory=list)
    commit_hash: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReindexMessage":
        """Desserializa o payload JSON recebido da fila."""
        return cls(
            client_id=UUID(data["client_id"]),
            squad_id=UUID(data["squad_id"]),
            repo_path=data["repo_path"],
            repo_label=data["repo_label"],
            files=list(data.get("files", [])),
            commit_hash=data.get("commit_hash"),
        )

    def to_dict(self) -> dict[str, Any]:
        """Serializa a mensagem para publicação na fila."""
        return {
            "client_id": str(self.client_id),
            "squad_id": str(self.squad_id),
            "repo_path": self.repo_path,
            "repo_label": self.repo_label,
            "files": self.files,
            "commit_hash": self.commit_hash,
        }
