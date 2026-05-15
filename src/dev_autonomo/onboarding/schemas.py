"""Schemas Pydantic do output estruturado do Onboarding Analyst (OA) v2.

O OA produz UM unico JSON ao fim do scan. Backend usa OnboardingAnalysisOutput
como contrato rigido — qualquer JSON malformado eh rejeitado e dispara
retry com mensagem corretiva, em vez de parsing heuristico.

Pra cada Stack detectada, o schema separa:
- observed_patterns (descritivo, vai pro relatorio da tela 3)
- recommended_for_agents (prescritivo, vai pro system prompt do Dev)

Anti-patterns sao separados com path:line concreto pra evitar
generalizacoes vagas.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


_SLUG_RE = re.compile(r"^[a-z0-9-]+$")


class StackConventions(BaseModel):
    """Convencoes da stack em duas dimensoes: descritiva vs prescritiva."""

    model_config = ConfigDict(extra="forbid")

    observed_patterns: dict[str, str] = Field(
        ...,
        description=(
            "Categoria -> descricao em prosa do que o OA OBSERVOU no codigo. "
            "Honesto inclusive sobre divergencias e padroes inconsistentes. "
            "Vai pro relatorio que o cliente le."
        ),
    )
    recommended_for_agents: dict[str, str] = Field(
        ...,
        description=(
            "Categoria -> diretriz prescritiva pra os agentes seguirem. "
            "FILTRADA pelo OA: nao copia anti-padroes observados, recomenda "
            "boa pratica. Vai pro system prompt do Dev."
        ),
    )

    @field_validator("observed_patterns", "recommended_for_agents")
    @classmethod
    def _at_least_5_categories(cls, v: dict[str, str]) -> dict[str, str]:
        # Goal: conventions_depth — minimo 5 categorias substantivas
        non_empty = {k: val for k, val in v.items() if val and val.strip()}
        if len(non_empty) < 5:
            raise ValueError(
                f"conventions precisam ter ao menos 5 categorias preenchidas. "
                f"Recebi {len(non_empty)}: {list(non_empty.keys())}",
            )
        return v


class StackDetected(BaseModel):
    """Stack identificada pelo OA scan."""

    model_config = ConfigDict(extra="forbid")

    slug: str = Field(..., description="ex: python-fastapi, typescript-react-vite")
    name: str = Field(..., min_length=1, description="display name humano")
    paths: list[str] = Field(
        ...,
        min_length=1,
        description="paths no repo onde essa stack vive (ex: ['src/api/'])",
    )
    framework: str | None = Field(None, description="ex: fastapi, next, spring-boot")
    framework_version: str | None = Field(None, description="versao detectada")
    conventions: StackConventions

    @field_validator("slug")
    @classmethod
    def _slug_format(cls, v: str) -> str:
        if not _SLUG_RE.match(v):
            raise ValueError(
                f"slug deve ser kebab-case lowercase: '{v}' invalido",
            )
        return v


class AntiPatternDetected(BaseModel):
    """Pattern observado no codigo que NAO deve ser replicado pelos agentes."""

    model_config = ConfigDict(extra="forbid")

    issue: str = Field(..., min_length=10, description="descricao do problema")
    severity: Literal["low", "medium", "high"]
    occurrences: list[str] = Field(
        ...,
        min_length=1,
        description=(
            "lista de path:line concretos onde o anti-pattern aparece. "
            "Generalizacoes vagas ('muitas funcoes') sao rejeitadas pelo grader."
        ),
    )
    recommendation: str = Field(
        ...,
        min_length=10,
        description="diretriz pra agente Dev evitar replicar",
    )

    @field_validator("occurrences")
    @classmethod
    def _occurrences_concrete(cls, v: list[str]) -> list[str]:
        # Cada occurrence precisa ter um delimitador (`:` ou `/`) sinalizando path
        for occ in v:
            if not occ or not occ.strip():
                raise ValueError(f"occurrence vazia rejeitada: {v}")
            if ":" not in occ and "/" not in occ:
                raise ValueError(
                    f"occurrence '{occ}' nao parece path:line ou path/file — "
                    "evitar generalizacoes vagas",
                )
        return v


class AgentRecommendation(BaseModel):
    """Agente recomendado pra esta squad baseado nas stacks detectadas."""

    model_config = ConfigDict(extra="forbid")

    tier: Literal["ba", "architect", "dev", "reviewer"]
    stack_slug: str | None = Field(
        None,
        description=(
            "null pra BA/Architect/Reviewer genericos. Obrigatorio pra Dev — "
            "agente especialista em UMA stack."
        ),
    )
    rationale: str = Field(
        ...,
        min_length=10,
        description="por que esse agente faz sentido pra essa squad",
    )

    @field_validator("stack_slug")
    @classmethod
    def _slug_format_when_present(cls, v: str | None) -> str | None:
        if v is not None and not _SLUG_RE.match(v):
            raise ValueError(f"stack_slug invalido: '{v}' deve ser kebab-case")
        return v


class ToolCallsSummary(BaseModel):
    """Sumario das tools que o OA usou — vira evidencia pro grader.

    O OA preenche isso ao fim do scan. Permite o grader verificar
    breadth (varreu o suficiente?) sem precisar reler tool calls
    individuais.
    """

    model_config = ConfigDict(extra="forbid")

    file_reads: int = Field(..., ge=0, description="quantos arquivos foram lidos")
    bash_commands: int = Field(..., ge=0)
    grep_searches: int = Field(0, ge=0)
    glob_searches: int = Field(0, ge=0)
    git_log_called: bool = Field(
        False,
        description=(
            "Se True, OA chamou git log alguma vez — evidencia pra check "
            "git_history_checked do rubric."
        ),
    )
    git_log_max_count: int = Field(
        0, ge=0,
        description="maior -N usado em git log -<N>. Goal: >= 50",
    )


class OnboardingAnalysisOutput(BaseModel):
    """Output completo do OA scan v2. Schema rigido contratual."""

    model_config = ConfigDict(extra="forbid")

    summary: str = Field(
        ...,
        min_length=50,
        description=(
            "relatorio em prosa primeira pessoa do que o OA descobriu. "
            "Vai aparecer literal na tela 3 do wizard, sob o cabecalho "
            "'Olha o que encontrei no seu projeto'. Tom didatico e direto."
        ),
    )
    stacks: list[StackDetected] = Field(
        ...,
        min_length=1,
        description="ao menos 1 stack detectada (mesmo projeto trivial tem alguma)",
    )
    jira_projects: list[str] = Field(
        default_factory=list,
        description=(
            "Codigos Jira detectados em commits/PR templates (ex: ['LEO', 'ADMIN']). "
            "Lista vazia eh valida — cliente pode nao usar Jira."
        ),
    )
    anti_patterns_detected: list[AntiPatternDetected] = Field(default_factory=list)
    recommended_agents: list[AgentRecommendation] = Field(
        ...,
        min_length=2,
        description=(
            "ao menos 2 agentes (Architect + 1 Dev sao essenciais — sem eles "
            "a pipeline nao funciona)"
        ),
    )
    tool_calls_summary: ToolCallsSummary

    @field_validator("jira_projects")
    @classmethod
    def _jira_format(cls, v: list[str]) -> list[str]:
        # Jira project keys sao tipicamente uppercase 2-10 chars
        for code in v:
            if not re.match(r"^[A-Z][A-Z0-9]{1,9}$", code):
                raise ValueError(
                    f"jira_project '{code}' invalido: deve ser uppercase 2-10 chars",
                )
        return v

    @field_validator("recommended_agents")
    @classmethod
    def _has_essential_tiers(cls, v: list[AgentRecommendation]) -> list[AgentRecommendation]:
        # Architect e ao menos 1 Dev sao essenciais
        tiers = {a.tier for a in v}
        missing: list[str] = []
        if "architect" not in tiers:
            missing.append("architect")
        if "dev" not in tiers:
            missing.append("dev")
        if missing:
            raise ValueError(
                f"recommended_agents deve conter pelo menos {missing}. "
                f"Sem eles a pipeline nao funciona.",
            )
        # Cada Dev tem stack_slug
        for agent in v:
            if agent.tier == "dev" and agent.stack_slug is None:
                raise ValueError(
                    f"Dev sem stack_slug invalido: '{agent.rationale[:40]}'. "
                    "Dev sempre eh especialista em UMA stack.",
                )
        return v
