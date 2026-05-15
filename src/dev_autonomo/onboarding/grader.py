"""Grader independente do Onboarding Analyst v2.

Recebe o OnboardingAnalysisOutput produzido pelo OA + uma rubric (lista de
checks). Chama Claude Haiku (modelo barato e adequado pra verificacao) pra
julgar se cada check passou. Devolve verdict + feedback corretivo pra retry.

O grader NAO viu o trabalho sendo feito — so o output final + os criterios.
Isso protege contra a tendencia natural do agente principal de "achar que
terminou" minimizando trabalho. Grader checa fato, nao narrativa.

Custo: Haiku 4.5 ~25x mais barato que Opus. Tipico grading de OA scan custa
US$ 0.001-0.01.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

import anthropic
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from dev_autonomo.common.claude_pricing import get_pricing
from dev_autonomo.config import get_settings
from dev_autonomo.onboarding.schemas import OnboardingAnalysisOutput

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Rubric data classes
# ---------------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class CheckDefinition:
    """Uma checagem individual do rubric."""

    id: str
    description: str
    verify_prompt: str


@dataclass(slots=True, frozen=True)
class CheckResult:
    """Resultado de um check apos avaliacao do grader."""

    check_id: str
    passed: bool
    reason: str


@dataclass(slots=True)
class GraderVerdict:
    """Output completo do grader."""

    overall_passed: bool
    checks: list[CheckResult]
    feedback_for_retry: str
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal
    grader_model: str
    raw_response: str = field(default="", repr=False)


# ---------------------------------------------------------------------------
# Rubric padrao do OA scan v2
# ---------------------------------------------------------------------------


DEFAULT_OA_RUBRIC: list[CheckDefinition] = [
    CheckDefinition(
        id="scan_breadth",
        description="OA varreu o repositorio com profundidade suficiente",
        verify_prompt=(
            "Olhe tool_calls_summary do output. Verifique:\n"
            "  - file_reads >= 15 * numero de stacks detectadas (ex: 2 stacks → 30 file reads)\n"
            "  - bash_commands >= 10 (listagem, grep, find, etc.)\n"
            "Se OA leu poucos arquivos, NAO PASSA — pode ter inferido stacks "
            "sem cobertura real."
        ),
    ),
    CheckDefinition(
        id="conventions_depth",
        description="Cada Stack tem conventions com profundidade adequada",
        verify_prompt=(
            "Para cada item em stacks[*].conventions:\n"
            "  - observed_patterns tem >= 5 categorias com texto substantivo "
            "(2+ frases cada, nao 1 palavra)\n"
            "  - recommended_for_agents tem >= 5 categorias com texto substantivo\n"
            "  - recommended_for_agents NAO copia anti-padroes literalmente "
            "de observed_patterns (deve ser filtrado/melhorado)\n"
            "Se conventions sao rasas ('uso pytest', 'snake case'), NAO PASSA."
        ),
    ),
    CheckDefinition(
        id="anti_patterns_evidence",
        description="Anti-patterns tem evidencia concreta (path:line)",
        verify_prompt=(
            "Se anti_patterns_detected nao esta vazio, cada item:\n"
            "  - issue tem >= 10 chars de descricao especifica\n"
            "  - occurrences tem path:line concreto (ex: 'src/foo.py:42'), "
            "NAO generalizacao ('em varios arquivos', 'em muitos lugares')\n"
            "  - recommendation explica o que fazer em vez do anti-pattern\n"
            "Anti-patterns vagos sao pior que ausentes — NAO PASSA."
        ),
    ),
    CheckDefinition(
        id="tests_examined",
        description="OA examinou arquivos de teste se o repo tem testes",
        verify_prompt=(
            "Verifique se o summary do OA menciona testes (pytest, vitest, "
            "junit, etc.) E se conventions tem categoria 'testing' / 'tests' "
            "preenchida.\n"
            "Se summary indica que tem testes mas conventions nao tem section "
            "de testing, NAO PASSA.\n"
            "Se o repo claramente nao tem testes (summary diz 'nao encontrei "
            "testes'), PASSA — eh estado licito."
        ),
    ),
    CheckDefinition(
        id="git_history_checked",
        description="OA consultou historico Git pra Jira projects e padroes",
        verify_prompt=(
            "Verifique tool_calls_summary.git_log_called == true E "
            "git_log_max_count >= 50.\n"
            "Se git_log nao foi chamado ou foi com -N pequeno (< 50), "
            "NAO PASSA — OA perdeu evidencia importante de Jira refs e "
            "padroes de commit."
        ),
    ),
]


# ---------------------------------------------------------------------------
# Schemas internos do grader
# ---------------------------------------------------------------------------


class _GraderCheckResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    check_id: str
    passed: bool
    reason: str = Field(..., min_length=5)


class _GraderResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    overall_passed: bool
    checks: list[_GraderCheckResponse] = Field(..., min_length=1)
    feedback_for_retry: str = Field(
        default="",
        description=(
            "Quando overall_passed=False, mensagem corretiva pro OA refazer. "
            "Tom de code review — direto, especifico, sem floreio. Vazio "
            "quando overall_passed=True."
        ),
    )


# ---------------------------------------------------------------------------
# API publica
# ---------------------------------------------------------------------------


async def grade_output(
    output: OnboardingAnalysisOutput,
    *,
    rubric: list[CheckDefinition] | None = None,
    anthropic_client: anthropic.Anthropic | None = None,
) -> GraderVerdict:
    """Avalia o output do OA contra o rubric. Chama Claude Haiku 1x.

    Args:
        output: o JSON estruturado produzido pelo OA scan.
        rubric: lista de checks. None usa DEFAULT_OA_RUBRIC.
        anthropic_client: opcional, default constroi do settings.

    Returns:
        GraderVerdict com per-check results, feedback pra retry, custo.

    Raises:
        anthropic.APIError quando a API Claude falha (timeout, rate limit, etc).
        ValidationError quando a resposta do Haiku nao bate no schema esperado
            (alguns casos extremos onde Haiku ignora o JSON mode — log + sobe).
    """
    rubric = rubric or DEFAULT_OA_RUBRIC
    if not rubric:
        raise ValueError("rubric vazia — grader precisa de ao menos 1 check")

    settings = get_settings()
    client = anthropic_client or _build_client()
    model = settings.GRADER_MODEL

    # Monta prompt do grader
    system_prompt = _build_system_prompt(rubric)
    user_message = _build_user_message(output)

    logger.info(
        "grader: avaliando OA output (%d checks) com modelo %s",
        len(rubric), model,
    )

    response = client.messages.create(
        model=model,
        max_tokens=2048,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )

    # Extrai conteudo textual
    raw_text = ""
    for block in response.content:
        if getattr(block, "type", "") == "text":
            raw_text = block.text  # type: ignore[attr-defined]
            break
    if not raw_text:
        raise ValueError("grader: Haiku retornou resposta sem bloco de texto")

    # Tenta extrair JSON do response (Haiku as vezes embrulha em ```)
    json_text = _extract_json_payload(raw_text)
    try:
        parsed = _GraderResponse.model_validate_json(json_text)
    except ValidationError:
        logger.error("grader: resposta nao bate no schema:\n%s", raw_text[:1000])
        raise

    # Custo
    input_tokens = response.usage.input_tokens
    output_tokens = response.usage.output_tokens
    try:
        pricing = get_pricing(model, provider="anthropic")
        cost = pricing.cost_usd(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=0,
            cache_write_tokens=0,
        )
    except Exception:
        cost = Decimal("0")

    # Confere cobertura: todos check_ids do rubric foram avaliados pelo Haiku?
    expected_ids = {c.id for c in rubric}
    seen_ids = {c.check_id for c in parsed.checks}
    missing = expected_ids - seen_ids
    if missing:
        logger.warning(
            "grader: Haiku omitiu checks %s — marcando como FAILED por omissao",
            missing,
        )

    results: list[CheckResult] = [
        CheckResult(check_id=c.check_id, passed=c.passed, reason=c.reason)
        for c in parsed.checks
    ]
    for mid in missing:
        results.append(CheckResult(
            check_id=mid,
            passed=False,
            reason="Grader nao avaliou esse check (resposta omitiu) — tratando como falha.",
        ))

    # overall reflete: parsed.overall_passed AND nada faltou AND nenhum check falhou
    overall = parsed.overall_passed and not missing and all(r.passed for r in results)

    verdict = GraderVerdict(
        overall_passed=overall,
        checks=results,
        feedback_for_retry=(parsed.feedback_for_retry or "").strip() if not overall else "",
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost,
        grader_model=model,
        raw_response=raw_text,
    )
    logger.info(
        "grader: verdict overall=%s cost=$%s tokens=%d/%d",
        overall, cost, input_tokens, output_tokens,
    )
    return verdict


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _build_client() -> anthropic.Anthropic:
    return anthropic.Anthropic(
        api_key=get_settings().ANTHROPIC_API_KEY.get_secret_value()
    )


def _build_system_prompt(rubric: list[CheckDefinition]) -> str:
    """Monta o system prompt do grader incluindo as definicoes do rubric."""
    rubric_text = "\n\n".join(
        f"### {check.id}\n"
        f"**Descricao:** {check.description}\n"
        f"**Como verificar:** {check.verify_prompt}"
        for check in rubric
    )
    return (
        "Voce eh um grader independente avaliando o output de um agente "
        "Onboarding Analyst. Sua tarefa: julgar OBJETIVAMENTE se cada "
        "check do rubric passou, baseado APENAS no output JSON fornecido.\n\n"
        "Voce NAO viu o trabalho sendo feito. Nao se deixa influenciar por "
        "esforco aparente — checa fato. Se o agente diz 'eu fiz X mas o "
        "JSON nao mostra X', NAO PASSOU.\n\n"
        "Seja CRITICO mas justo. Se algo eh genuinamente bom, marque passed. "
        "Se algo eh raso ou tem evidencia fraca, marque failed e explique.\n\n"
        f"# Rubric ({len(rubric)} checks)\n\n{rubric_text}\n\n"
        "# Formato de resposta (OBRIGATORIO)\n\n"
        "Responda APENAS com JSON valido neste schema (sem markdown wrapper):\n\n"
        "{\n"
        '  "overall_passed": <bool: todos os checks passaram?>,\n'
        '  "checks": [\n'
        '    {"check_id": "<id>", "passed": <bool>, "reason": "<por que>"},\n'
        '    ...\n'
        '  ],\n'
        '  "feedback_for_retry": "<mensagem corretiva pro OA se overall_passed=False, '
        "tom de code review direto. Vazio quando overall_passed=True.>\"\n"
        "}\n\n"
        "Use os check_id EXATOS do rubric. Nao invente checks novos. "
        "Cada reason precisa ter 5+ chars e ser especifico (nao 'ok' ou 'falhou')."
    )


def _build_user_message(output: OnboardingAnalysisOutput) -> str:
    """Monta a mensagem user com o JSON do OA pra grader avaliar."""
    return (
        "# Output do Onboarding Analyst pra avaliar:\n\n"
        "```json\n"
        f"{output.model_dump_json(indent=2)}\n"
        "```\n\n"
        "Avalie cada check do rubric e responda o JSON estruturado."
    )


def _extract_json_payload(text: str) -> str:
    """Extrai bloco JSON do texto (Haiku as vezes embrulha em ```json...```)."""
    stripped = text.strip()
    if stripped.startswith("```"):
        # remove fence marker
        lines = stripped.split("\n")
        # primeira linha eh ```json ou ```
        # ultima linha eh ```
        inner = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])
        return inner
    return stripped
