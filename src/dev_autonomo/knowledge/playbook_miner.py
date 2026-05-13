"""Playbook miner: extrai regras reutilizaveis de PR review comments.

Pipeline:
1. Recebe `PRReviewCommentEvent` (publicado pelo webhook GitHub).
2. Chama Claude Haiku para classificar (regra reutilizavel ou caso pontual).
3. Se reutilizavel, gera embedding via Voyage e grava em `playbook_entries`
   + Qdrant partition `playbook:{squad}`.
4. Toda chamada Claude eh gravada em `claude_api_calls` (cost tracking).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

from qdrant_client.models import PointStruct
from sqlalchemy.ext.asyncio import AsyncSession

from dev_autonomo.common.claude_client import ClaudeClient
from dev_autonomo.db.models import PlaybookEntry
from dev_autonomo.knowledge.qdrant_client import (
    KnowledgePartition,
    QdrantKnowledgeStore,
)
from dev_autonomo.knowledge.voyage_client import VoyageEmbeddingClient

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class PRReviewCommentEvent:
    """Payload normalizado de um PR review comment do GitHub."""

    client_id: UUID
    squad_id: UUID
    pr_number: int
    comment_id: int
    comment_body: str
    file_path: str | None = None
    diff_hunk: str | None = None
    author_login: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PRReviewCommentEvent:
        return cls(
            client_id=UUID(data["client_id"]),
            squad_id=UUID(data["squad_id"]),
            pr_number=int(data["pr_number"]),
            comment_id=int(data["comment_id"]),
            comment_body=data["comment_body"],
            file_path=data.get("file_path"),
            diff_hunk=data.get("diff_hunk"),
            author_login=data.get("author_login"),
        )


@dataclass(slots=True)
class MiningResult:
    """Resultado do processamento de um comment."""

    is_reusable_rule: bool
    rationale: str
    entry_id: UUID | None
    cost_usd: float
    error: str | None = None


CLASSIFIER_SYSTEM_PROMPT = (
    "Voce e um classificador de comments de PR review. Sua tarefa e decidir se "
    "um comment expressa uma REGRA REUTILIZAVEL (que vale aplicar em codigo "
    "futuro do mesmo time) ou um CASO PONTUAL (so vale para o PR especifico).\n\n"
    "REGRA REUTILIZAVEL: principio generalizavel, padrao do time, regra de negocio "
    "ou tecnica.\n"
    "Exemplos: 'sempre use httpx ao inves de requests', 'todo endpoint de pagamento "
    "precisa validar idempotencia', 'nao acesse o ORM direto, use o repository'.\n\n"
    "CASO PONTUAL: correcao especifica do PR sem aplicabilidade futura.\n"
    "Exemplos: 'esse nome de variavel ta errado', 'esqueceu de remover esse "
    "console.log', 'falta um import aqui'.\n\n"
    "Voce DEVE responder com JSON valido na estrutura especificada. Nada alem do JSON."
)


CLASSIFIER_USER_PROMPT_TEMPLATE = """Comment do PR review:
\"\"\"
{comment_body}
\"\"\"

Contexto:
- Arquivo: {file_path}
- Diff hunk:
{diff_hunk}

Responda APENAS com JSON nesta estrutura exata:
{{
  "is_reusable_rule": true | false,
  "rationale": "explicacao curta (1-2 frases) do porque",
  "rule_text": "regra reescrita em forma generalizavel (so se is_reusable_rule=true)",
  "scope_glob": "ex: src/api/**, payments/**, ou * para qualquer arquivo (so se is_reusable_rule=true)",
  "severity": "low | medium | high",
  "example_code": "trecho de codigo como exemplo, opcional"
}}"""


async def mine_pr_review_comment(
    event: PRReviewCommentEvent,
    *,
    session: AsyncSession,
    claude: ClaudeClient | None = None,
    voyage: VoyageEmbeddingClient | None = None,
    qdrant: QdrantKnowledgeStore | None = None,
    model: str = "claude-haiku-4-5",
) -> MiningResult:
    """Processa um PR review comment. Persiste PlaybookEntry se reutilizavel."""
    claude = claude or ClaudeClient(session=session)
    voyage = voyage or VoyageEmbeddingClient()
    qdrant = qdrant or QdrantKnowledgeStore()

    user_prompt = CLASSIFIER_USER_PROMPT_TEMPLATE.format(
        comment_body=event.comment_body,
        file_path=event.file_path or "(nao informado)",
        diff_hunk=event.diff_hunk or "(nao informado)",
    )

    response = await claude.complete(
        model=model,
        messages=[{"role": "user", "content": user_prompt}],
        system=CLASSIFIER_SYSTEM_PROMPT,
        max_tokens=512,
        temperature=0.2,
        client_id=event.client_id,
    )

    try:
        classification = _parse_json_response(response.text)
    except ValueError as exc:
        logger.warning(
            "Playbook miner: JSON invalido para comment %s: %s", event.comment_id, exc
        )
        return MiningResult(
            is_reusable_rule=False,
            rationale=f"JSON parse failed: {exc}",
            entry_id=None,
            cost_usd=float(response.cost_usd),
            error=str(exc),
        )

    is_reusable = bool(classification.get("is_reusable_rule", False))
    rationale = str(classification.get("rationale", ""))

    if not is_reusable:
        return MiningResult(
            is_reusable_rule=False,
            rationale=rationale,
            entry_id=None,
            cost_usd=float(response.cost_usd),
        )

    rule_text = str(classification.get("rule_text", "")).strip()
    if not rule_text:
        return MiningResult(
            is_reusable_rule=False,
            rationale="is_reusable_rule=true mas rule_text vazio",
            entry_id=None,
            cost_usd=float(response.cost_usd),
            error="rule_text_missing",
        )

    scope_glob = str(classification.get("scope_glob") or "*")
    severity = str(classification.get("severity") or "medium").lower()
    if severity not in {"low", "medium", "high", "critical"}:
        severity = "medium"
    example_code = classification.get("example_code") or None

    # Persiste PlaybookEntry
    origin = f"pr_review:PR#{event.pr_number}#comment:{event.comment_id}"
    entry = PlaybookEntry(
        client_id=event.client_id,
        squad_id=event.squad_id,
        scope_glob=scope_glob,
        rule_text=rule_text,
        example_code=example_code,
        severity=severity,
        origin=origin,
    )
    session.add(entry)
    await session.flush()  # popular entry.id

    # Embedding da regra e insert no Qdrant
    embed_text = f"{scope_glob} :: {rule_text}"
    embed_result = await voyage.embed_documents([embed_text])
    vector_id = str(uuid4())

    await qdrant.ensure_collection(KnowledgePartition.PLAYBOOK, event.squad_id)
    await qdrant.upsert_points(
        KnowledgePartition.PLAYBOOK,
        event.squad_id,
        [
            PointStruct(
                id=vector_id,
                vector=embed_result.vectors[0],
                payload={
                    "client_id": str(event.client_id),
                    "squad_id": str(event.squad_id),
                    "playbook_entry_id": str(entry.id),
                    "scope_glob": scope_glob,
                    "severity": severity,
                    "rule_text": rule_text,
                    "origin": origin,
                },
            )
        ],
    )

    entry.embedding_vector_id = vector_id
    await session.flush()

    return MiningResult(
        is_reusable_rule=True,
        rationale=rationale,
        entry_id=entry.id,
        cost_usd=float(response.cost_usd),
    )


def _parse_json_response(text: str) -> dict[str, Any]:
    """Extrai JSON do response, tolerando wrappers como ```json ... ```."""
    s = text.strip()
    # Remove fences ```json ... ``` ou ``` ... ```
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s[3:]
        if s.endswith("```"):
            s = s[: -3].strip()
    try:
        return json.loads(s)
    except json.JSONDecodeError as exc:
        # ultima tentativa: encontrar o primeiro `{` e ultimo `}`
        start = s.find("{")
        end = s.rfind("}")
        if start >= 0 and end > start:
            return json.loads(s[start : end + 1])
        raise ValueError(f"resposta nao contem JSON valido: {exc}") from exc
