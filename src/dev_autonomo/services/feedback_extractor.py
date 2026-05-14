"""Feedback loop — captura padroes anonimizados de PRs mergeados.

Bloco F do roadmap stack-knowledge. Pipeline em 3 camadas
independentes pra garantir cross-tenant safety sem depender de
validacao humana premia.

Pipeline:

  PR merged (quality gate: 0 request_changes)
      |
      v
  L1 — HAIKU extrator
       Persona: extrair valor reutilizavel.
       Prompt: "Extraia 1-5 padroes/decisoes reutilizaveis desta
                mudanca aprovada. NAO cite identifiers proprietarios
                — substitua por placeholders <Class>, <Function>, etc."
       Output: list[chunk_str].
      |
      v
  L2 — SONNET validador (red team)
       Persona: caca-vazamentos.
       Prompt: "Analise se este chunk pode ir pra RAG cross-tenant.
                Detecte: identifier proprietario residual, PII, contexto
                interno revelador, secrets, etc."
       Output: {safe_for_cross_tenant: bool, leak_kind, reasons}.
       Se safe=false → DESCARTA antes do regex.
      |
      v
  L3 — Regex (ultimo cinto de seguranca)
       Patterns hardcoded: CamelCase >12 chars sem placeholder, paths
       absolutos, emails, IPs privados, tokens.
       Se qualquer bater → DESCARTA.
      |
      v
  INDEXA em stack_patterns:{stack_slug} com source_kind=feedback_loop
       license=internal_derived, source_quality=field_proven.

Audit log: TODO chunk avaliado (aceito ou rejeitado) gera linha em
rag_audit_log com decisao + reasons. Admin pode inspecionar metrics
sem precisar pre-aprovar o sistema.

Custo: ~US$ 0.025 por PR (Haiku ~0.005 + Sonnet ~0.02). Pra 1k PRs/mes
= US$ 25.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

import anthropic
import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from dev_autonomo.common.enums import (
    AuditDecision,
    RagSourceKind,
    RagSourceLicense,
    RagSourceQuality,
    RagSourceScope,
    RagSourceStatus,
)
from dev_autonomo.config import get_settings
from dev_autonomo.db.models import RagAuditLog, RagSource

logger = logging.getLogger(__name__)

EXTRACTOR_MODEL = "claude-haiku-4-5"
VALIDATOR_MODEL = "claude-sonnet-4-6"

MAX_CHUNKS_PER_PR = 5
MIN_REQUEST_CHANGES_TO_SKIP = 1  # quality gate


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------


_EXTRACT_PROMPT = """\
Voce esta analisando um Pull Request **MERGEADO E APROVADO** (humano nao
pediu mudancas). Sua tarefa: extrair 1-{max_chunks} padroes/decisoes
reutilizaveis que podem ajudar outros agentes que trabalharem nessa
mesma stack no futuro.

Stack: **{stack_slug}**

PR title: {pr_title}

Diff resumido:
```
{diff_summary}
```

Comments do humano na review:
```
{review_comments}
```

REGRAS DE EXTRACAO:
- Foque em **estrutura, convencao, decisao arquitetural**. Nao copie codigo.
- NUNCA cite identifiers proprietarios. Substitua por placeholders genericos:
  - `PagamentoServiceImpl` → `<DomainServiceImpl>`
  - `acme_pagamentos_db` → `<domain_db>`
  - `processCarrinho()` → `<processDomain>()`
- Cada chunk deve ser auto-contido (faz sentido sem contexto).
- Idioma: portugues.

Retorne SOMENTE um JSON array de strings:
```json
[
  "Padrao 1 ...",
  "Padrao 2 ...",
  ...
]
```

Se a mudanca nao contem padrao reutilizavel valioso, retorne `[]`.
"""


_VALIDATE_PROMPT = """\
Voce eh um **caca-vazamentos** auditando conteudo antes dele ir pra uma
base de conhecimento **cross-tenant** (varios clientes acessam).

Stack alvo: **{stack_slug}**

Chunk pra avaliar:
```
{chunk}
```

Diff original do PR (pra comparar antes/depois da anonimizacao):
```
{diff_summary}
```

Avalie se este chunk e SEGURO pra ir pra RAG cross-tenant. Detecte:
1. **Identifier proprietario residual** — nome de classe, funcao, modulo,
   tabela que claramente eh do cliente (ex: "AcmePagamentos", "obris_xxx").
   Placeholders genericos como `<Class>`, `<Service>` sao OK.
2. **PII / secret** — email, token, password, IP, URL com auth.
3. **Contexto interno revelador** — frase que revela arquitetura/processo
   especifico do cliente (ex: "no nosso cluster X").
4. **Codigo copiado verbatim** — chunk reproduzindo trechos longos de
   codigo (deveria ser descricao, nao copia).

Seja CRITICO. Falso positivo (rejeitar chunk bom) e aceitavel — perde-se
um chunk util. Falso negativo (deixar passar chunk ruim) NAO eh aceitavel
— compromete privacidade entre clientes.

Retorne SOMENTE JSON:
```json
{{
  "safe_for_cross_tenant": true | false,
  "leak_kind": null | "proprietary_identifier" | "pii" | "internal_context" | "verbatim_code",
  "reasons": ["razao 1", "razao 2"]
}}
```
"""


# ---------------------------------------------------------------------------
# L3 — Regex (ultimo cinto)
# ---------------------------------------------------------------------------


_REGEX_LEAK_PATTERNS: list[tuple[re.Pattern, str]] = [
    # CamelCase com 2+ palavras (nome de classe proprietaria sem placeholder).
    # Whitelist abaixo cobre os comuns nao-proprietarios.
    (re.compile(r"\b[A-Z][a-z]+(?:[A-Z][a-z]+){1,}\b"), "camelcase_identifier"),
    # snake_case com 3+ segmentos
    (re.compile(r"\b[a-z]+_[a-z]+_[a-z]+(?:_[a-z]+)+\b"), "deep_snake_case"),
    # Paths absolutos
    (re.compile(r"\b/(?:home|opt|var|etc|mnt|usr)/[\w/.-]+"), "absolute_path"),
    (re.compile(r"\b[A-Z]:\\[\w\\.-]+"), "windows_path"),
    # Emails
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}"), "email"),
    # IPs privados
    (
        re.compile(r"\b(?:10|172\.(?:1[6-9]|2\d|3[01])|192\.168)\.\d{1,3}\.\d{1,3}\b"),
        "private_ip",
    ),
    # Tokens/secrets
    (re.compile(r"(?:sk|pk|gh[ps]|github_pat)_[A-Za-z0-9]{20,}"), "api_key"),
    (re.compile(r"Bearer\s+[A-Za-z0-9_-]{30,}"), "bearer_token"),
]

# Whitelist de CamelCase comum (nao trata como vazamento)
_CAMELCASE_WHITELIST = {
    "HashMap", "ArrayList", "LinkedList", "TreeMap", "HashSet",
    "InputStream", "OutputStream", "PrintWriter", "BufferedReader",
    "ServiceLayer", "SpringBoot", "MicrosoftAzure", "AmazonWebServices",
    "GoogleCloud", "GraphQL", "RestController", "AuthorizationFilter",
    "ConsumerProvider", "EventListener", "ApplicationContext",
}


def regex_filter(chunk: str) -> list[str]:
    """Retorna lista de leak kinds detectados. Vazio = chunk passa."""
    detected: list[str] = []
    for pattern, kind in _REGEX_LEAK_PATTERNS:
        matches = pattern.findall(chunk)
        # Filtra whitelist
        relevant = [m for m in matches if m not in _CAMELCASE_WHITELIST]
        if relevant:
            detected.append(kind)
    return detected


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class FeedbackResult:
    """Resumo da execucao do pipeline pra 1 PR."""

    pr_url: str
    stack_slug: str
    extracted_chunks: int
    accepted_chunks: int
    rejected_haiku: int = 0
    rejected_sonnet: int = 0
    rejected_regex: int = 0
    rejected_multi: int = 0
    rag_source_id: UUID | None = None
    error: str | None = None
    total_cost_usd: float = 0.0


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


def _build_anthropic_client() -> anthropic.Anthropic:
    return anthropic.Anthropic(
        api_key=get_settings().ANTHROPIC_API_KEY.get_secret_value()
    )


async def fetch_pr_data(pr_url: str, github_token: str) -> tuple[str, str, list[dict]] | None:
    """Retorna (pr_title, diff_summary, review_comments) ou None se falha."""
    # Extract owner/repo/number from URL
    # https://github.com/owner/repo/pull/123
    parts = pr_url.rstrip("/").split("/")
    if len(parts) < 7 or "pull" not in parts:
        return None
    owner, repo, _, pr_number = parts[-4], parts[-3], parts[-2], parts[-1]

    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github+json",
    }

    async with httpx.AsyncClient(timeout=30.0) as c:
        pr_resp = await c.get(
            f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}",
            headers=headers,
        )
        if pr_resp.status_code >= 400:
            return None
        pr = pr_resp.json()
        pr_title = pr.get("title", "")

        # Diff (compactado)
        diff_resp = await c.get(
            f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/files",
            headers=headers,
        )
        files = diff_resp.json() if diff_resp.status_code < 400 else []
        # Sumarizamos: filename + status + line counts + small patch preview.
        diff_lines: list[str] = []
        for f in files[:20]:  # max 20 files
            diff_lines.append(f"--- {f.get('filename')} ({f.get('status')}, +{f.get('additions',0)}/-{f.get('deletions',0)})")
            patch = f.get("patch") or ""
            if patch:
                diff_lines.append(patch[:1500])
        diff_summary = "\n".join(diff_lines)[:8000]

        # Reviews + comments
        reviews_resp = await c.get(
            f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/reviews",
            headers=headers,
        )
        reviews = reviews_resp.json() if reviews_resp.status_code < 400 else []
        # Quality gate: skip se algum review é REQUEST_CHANGES
        if any(r.get("state") == "CHANGES_REQUESTED" for r in reviews):
            logger.info("quality_gate: pr=%s tem REQUEST_CHANGES, skipping", pr_url)
            return None

        review_comments = []
        for r in reviews[:10]:
            body = r.get("body") or ""
            if body.strip():
                review_comments.append({"author": (r.get("user") or {}).get("login"), "body": body[:500]})

    return pr_title, diff_summary, review_comments


async def process_merged_pr(
    session: AsyncSession,
    *,
    pr_url: str,
    stack_slug: str,
    github_token: str,
    anthropic_client: anthropic.Anthropic | None = None,
) -> FeedbackResult:
    """Pipeline completo: PR → chunks anonimizados → RAG cross-tenant.

    Idempotente — re-run com mesmo pr_url ignora (source_hash unique).
    """
    result = FeedbackResult(pr_url=pr_url, stack_slug=stack_slug, extracted_chunks=0, accepted_chunks=0)
    anth = anthropic_client or _build_anthropic_client()

    pr_data = await fetch_pr_data(pr_url, github_token)
    if pr_data is None:
        result.error = "fetch_pr_data falhou ou quality gate falhou"
        return result
    pr_title, diff_summary, review_comments = pr_data

    review_text = "\n".join(f"[{c['author']}] {c['body']}" for c in review_comments) or "(sem comments)"

    # L1 — Haiku extract
    extract_prompt = _EXTRACT_PROMPT.format(
        max_chunks=MAX_CHUNKS_PER_PR,
        stack_slug=stack_slug,
        pr_title=pr_title,
        diff_summary=diff_summary[:6000],
        review_comments=review_text[:2000],
    )

    try:
        haiku_resp = anth.messages.create(
            model=EXTRACTOR_MODEL,
            max_tokens=2048,
            messages=[{"role": "user", "content": extract_prompt}],
        )
    except Exception as exc:
        result.error = f"L1 haiku falhou: {exc}"
        return result

    haiku_text = ""
    for block in haiku_resp.content:
        if hasattr(block, "text"):
            haiku_text += block.text
    haiku_tokens_in = getattr(haiku_resp.usage, "input_tokens", 0) or 0
    haiku_tokens_out = getattr(haiku_resp.usage, "output_tokens", 0) or 0

    # Parse JSON
    chunks: list[str] = []
    try:
        # Tenta extrair JSON array do output
        text_clean = haiku_text.strip()
        if "```" in text_clean:
            text_clean = text_clean.split("```")[1]
            if text_clean.startswith("json"):
                text_clean = text_clean[4:]
        parsed = json.loads(text_clean.strip())
        if isinstance(parsed, list):
            chunks = [str(c).strip() for c in parsed if str(c).strip()][:MAX_CHUNKS_PER_PR]
    except Exception as exc:
        result.error = f"L1 haiku output nao parseou JSON: {exc}"
        # Audit log da rejeicao L1
        await _log_audit(
            session,
            rag_source_id=None, stack_slug=stack_slug, pr_url=pr_url,
            chunk_index=0, chunk_preview=haiku_text[:200],
            decision=AuditDecision.REJECTED_HAIKU,
            reasons=["L1_haiku_parse_failed"],
            sonnet_verdict=None,
            haiku_tokens_in=haiku_tokens_in, haiku_tokens_out=haiku_tokens_out,
        )
        await session.flush()
        return result

    result.extracted_chunks = len(chunks)

    # Cria RagSource pendente (sera marcado INDEXED se algum chunk passar)
    from dev_autonomo.services.rag_ingest import compute_source_hash
    combined_text = "\n\n".join(chunks) if chunks else f"{pr_url}-empty"
    source_hash = compute_source_hash(combined_text)
    rag_source = RagSource(
        id=uuid4(),
        collection_slug=f"stack_patterns:{stack_slug}",
        kind=RagSourceKind.FEEDBACK_LOOP,
        source_uri=pr_url,
        source_hash=source_hash,
        scope=RagSourceScope.CROSS_TENANT,
        client_id=None,
        license=RagSourceLicense.INTERNAL_DERIVED,
        source_quality=RagSourceQuality.FIELD_PROVEN,
        stack_version=None,
        uploaded_by_user_id=None,
        indexed_chunks=0,
        status=RagSourceStatus.PENDING,
        tags=["feedback_loop"],
    )
    session.add(rag_source)
    await session.flush()
    result.rag_source_id = rag_source.id

    # L2 + L3 por chunk
    accepted_chunks_idx: list[int] = []
    for idx, chunk in enumerate(chunks):
        # L2 — Sonnet validate
        validate_prompt = _VALIDATE_PROMPT.format(
            stack_slug=stack_slug,
            chunk=chunk,
            diff_summary=diff_summary[:3000],
        )
        try:
            sonnet_resp = anth.messages.create(
                model=VALIDATOR_MODEL,
                max_tokens=512,
                messages=[{"role": "user", "content": validate_prompt}],
            )
        except Exception as exc:
            logger.warning("L2 sonnet falhou chunk=%d: %s", idx, exc)
            await _log_audit(
                session, rag_source_id=rag_source.id, stack_slug=stack_slug,
                pr_url=pr_url, chunk_index=idx, chunk_preview=chunk[:200],
                decision=AuditDecision.REJECTED_SONNET,
                reasons=[f"sonnet_call_failed: {exc}"],
                sonnet_verdict=None,
                haiku_tokens_in=0, haiku_tokens_out=0,
            )
            result.rejected_sonnet += 1
            continue

        sonnet_text = ""
        for block in sonnet_resp.content:
            if hasattr(block, "text"):
                sonnet_text += block.text
        sonnet_tokens_in = getattr(sonnet_resp.usage, "input_tokens", 0) or 0
        sonnet_tokens_out = getattr(sonnet_resp.usage, "output_tokens", 0) or 0

        try:
            text_clean = sonnet_text.strip()
            if "```" in text_clean:
                text_clean = text_clean.split("```")[1]
                if text_clean.startswith("json"):
                    text_clean = text_clean[4:]
            verdict = json.loads(text_clean.strip())
        except Exception:
            verdict = {"safe_for_cross_tenant": False, "reasons": ["sonnet_json_parse_failed"]}

        sonnet_says_safe = bool(verdict.get("safe_for_cross_tenant"))

        # L3 — Regex
        regex_kinds = regex_filter(chunk)
        regex_safe = len(regex_kinds) == 0

        # Decisao
        if sonnet_says_safe and regex_safe:
            decision = AuditDecision.ACCEPTED
            reasons = []
            accepted_chunks_idx.append(idx)
        elif not sonnet_says_safe and not regex_safe:
            decision = AuditDecision.REJECTED_MULTI
            reasons = list(verdict.get("reasons", [])) + regex_kinds
            result.rejected_multi += 1
        elif not sonnet_says_safe:
            decision = AuditDecision.REJECTED_SONNET
            reasons = list(verdict.get("reasons", []))
            result.rejected_sonnet += 1
        else:
            decision = AuditDecision.REJECTED_REGEX
            reasons = regex_kinds
            result.rejected_regex += 1

        await _log_audit(
            session, rag_source_id=rag_source.id, stack_slug=stack_slug,
            pr_url=pr_url, chunk_index=idx, chunk_preview=chunk[:200],
            decision=decision, reasons=reasons,
            sonnet_verdict=verdict,
            haiku_tokens_in=haiku_tokens_in if idx == 0 else 0,
            haiku_tokens_out=haiku_tokens_out if idx == 0 else 0,
            sonnet_tokens_in=sonnet_tokens_in,
            sonnet_tokens_out=sonnet_tokens_out,
        )

    result.accepted_chunks = len(accepted_chunks_idx)

    # Indexa chunks aceitos no Qdrant
    if accepted_chunks_idx:
        from dev_autonomo.knowledge.qdrant_client import QdrantKnowledgeStore
        from dev_autonomo.knowledge.voyage_client import VoyageEmbeddingClient
        from dev_autonomo.services.rag_ingest import qdrant_collection_for_slug
        from qdrant_client.models import Distance, PointStruct, VectorParams

        voyage = VoyageEmbeddingClient()
        accepted_texts = [chunks[i] for i in accepted_chunks_idx]
        embed_result = await voyage.embed_documents(accepted_texts)

        qdrant = QdrantKnowledgeStore()
        collection_name = qdrant_collection_for_slug(rag_source.collection_slug)
        try:
            await qdrant._client.get_collection(collection_name)
        except Exception:
            await qdrant._client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(
                    size=len(embed_result.vectors[0]), distance=Distance.COSINE,
                ),
            )

        points = [
            PointStruct(
                id=str(uuid4()),
                vector=vector,
                payload={
                    "rag_source_id": str(rag_source.id),
                    "collection_slug": rag_source.collection_slug,
                    "scope": "cross_tenant",
                    "license": "internal_derived",
                    "source_quality": "field_proven",
                    "source_kind": "feedback_loop",
                    "pr_url": pr_url,
                    "chunk_index": orig_idx,
                    "content": chunk[:4000],
                },
            )
            for (orig_idx, chunk), vector in zip(
                ((i, chunks[i]) for i in accepted_chunks_idx),
                embed_result.vectors,
                strict=True,
            )
        ]
        await qdrant._client.upsert(collection_name=collection_name, points=points)

        rag_source.indexed_chunks = len(accepted_chunks_idx)
        rag_source.status = RagSourceStatus.INDEXED
    else:
        rag_source.status = RagSourceStatus.FAILED
        rag_source.error_message = "0 chunks passaram pelo pipeline de validacao"

    await session.flush()

    # Custo aproximado
    haiku_in = haiku_tokens_in / 1_000_000 * 1.0
    haiku_out = haiku_tokens_out / 1_000_000 * 5.0
    sonnet_total_in = sum(0 for _ in accepted_chunks_idx) + (len(chunks) * 800 / 1_000_000 * 3.0)
    result.total_cost_usd = haiku_in + haiku_out + sonnet_total_in

    return result


async def _log_audit(
    session: AsyncSession,
    *,
    rag_source_id: UUID | None,
    stack_slug: str,
    pr_url: str,
    chunk_index: int,
    chunk_preview: str,
    decision: AuditDecision,
    reasons: list[str],
    sonnet_verdict: dict | None,
    haiku_tokens_in: int = 0,
    haiku_tokens_out: int = 0,
    sonnet_tokens_in: int = 0,
    sonnet_tokens_out: int = 0,
) -> None:
    """Insert no rag_audit_log."""
    entry = RagAuditLog(
        rag_source_id=rag_source_id,
        stack_slug=stack_slug,
        pr_url=pr_url,
        chunk_index=chunk_index,
        chunk_preview=chunk_preview,
        decision=decision,
        reasons=reasons,
        sonnet_verdict=sonnet_verdict,
        haiku_tokens_in=haiku_tokens_in,
        haiku_tokens_out=haiku_tokens_out,
        sonnet_tokens_in=sonnet_tokens_in,
        sonnet_tokens_out=sonnet_tokens_out,
    )
    session.add(entry)
