"""Schema da mensagem de reindexação incremental publicada na fila RabbitMQ.

Utilizado pelo webhook GitHub (event push) para enfileirar arquivos que
precisam ser reindexados no Knowledge Hub da squad.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

# Nome da fila de reindexação incremental (push do GitHub -> worker de indexação)
REINDEX_QUEUE = "devauto.knowledge.reindex"


@dataclass(slots=True)
class ReindexMessage:
    """Mensagem enfileirada quando um push no GitHub altera arquivos de uma squad.

    Campos
    ------
    client_id:   UUID do cliente dono da squad.
    squad_id:    UUID da squad cujo Knowledge Hub deve ser atualizado.
    repo:        full_name do repositório (ex: ``"owner/repo"``).
    ref:         ref do push (ex: ``"refs/heads/main"``).
    commit_hash: SHA do commit mais recente (``after`` no payload do GitHub).
    files:       Lista deduplicada de caminhos de arquivos afetados
                 (added + modified + removed).
    """

    client_id: UUID
    squad_id: UUID
    repo: str
    ref: str
    commit_hash: str
    files: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serializa para dict compatível com ``publish()`` do common/queue.py."""
        return {
            "client_id": str(self.client_id),
            "squad_id": str(self.squad_id),
            "repo": self.repo,
            "ref": self.ref,
            "commit_hash": self.commit_hash,
            "files": self.files,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReindexMessage":
        """Desserializa a partir de dict (consumer-side)."""
        return cls(
            client_id=UUID(data["client_id"]),
            squad_id=UUID(data["squad_id"]),
            repo=data["repo"],
            ref=data["ref"],
            commit_hash=data["commit_hash"],
            files=list(data.get("files", [])),
        )
