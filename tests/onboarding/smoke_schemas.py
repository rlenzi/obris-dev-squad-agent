"""Smoke dos schemas: valido aceita, invalido rejeita com mensagem util."""
from pydantic import ValidationError
from dev_autonomo.onboarding.schemas import (
    OnboardingAnalysisOutput,
    StackDetected,
    StackConventions,
    AntiPatternDetected,
    AgentRecommendation,
    ToolCallsSummary,
)


def _conv5() -> dict[str, str]:
    return {
        "testing": "pytest com pytest-asyncio em tests/",
        "naming": "snake_case modulos, PascalCase classes",
        "imports": "absolute imports a partir de dev_autonomo",
        "error_handling": "HTTPException nos routers",
        "commits": "tipo(escopo): descricao",
    }


def test_valid_minimal():
    """Caso minimal valido — passa."""
    output = OnboardingAnalysisOutput(
        summary="Esse é um repo simples com backend Python/FastAPI em src/.",
        stacks=[
            StackDetected(
                slug="python-fastapi",
                name="Backend Python/FastAPI",
                paths=["src/"],
                framework="fastapi",
                framework_version="0.115.0",
                conventions=StackConventions(
                    observed_patterns=_conv5(),
                    recommended_for_agents=_conv5(),
                ),
            ),
        ],
        jira_projects=["LEO"],
        recommended_agents=[
            AgentRecommendation(
                tier="architect",
                stack_slug=None,
                rationale="Coordena Devs pra qualquer demanda multi-area",
            ),
            AgentRecommendation(
                tier="dev",
                stack_slug="python-fastapi",
                rationale="Backend é o codigo principal do projeto",
            ),
        ],
        tool_calls_summary=ToolCallsSummary(
            file_reads=42, bash_commands=15, git_log_called=True, git_log_max_count=100,
        ),
    )
    print(f"[valid_minimal] OK summary={output.summary[:40]!r}")


def test_reject_slug_invalid():
    try:
        StackDetected(
            slug="Python_FastAPI",  # PascalCase + underscore invalido
            name="x", paths=["src/"], framework=None, framework_version=None,
            conventions=StackConventions(
                observed_patterns=_conv5(),
                recommended_for_agents=_conv5(),
            ),
        )
        print("[slug] FAIL: aceitou slug invalido")
    except ValidationError as e:
        print(f"[slug] OK rejeitou: {str(e)[:80]}")


def test_reject_conventions_shallow():
    try:
        StackConventions(
            observed_patterns={"testing": "pytest"},  # so 1 categoria
            recommended_for_agents=_conv5(),
        )
        print("[conv shallow] FAIL: aceitou conventions raso")
    except ValidationError as e:
        print(f"[conv shallow] OK rejeitou: {str(e)[:80]}")


def test_reject_anti_pattern_vague():
    try:
        AntiPatternDetected(
            issue="varias funcoes ruins",
            severity="medium",
            occurrences=["em muitos lugares"],  # sem path
            recommendation="evitar isso",
        )
        print("[antipattern vague] FAIL: aceitou occurrence vaga")
    except ValidationError as e:
        print(f"[antipattern vague] OK rejeitou: {str(e)[:80]}")


def test_anti_pattern_concrete():
    """Path:line concreto eh aceito."""
    ap = AntiPatternDetected(
        issue="Catch-all exception em routers, ~15% dos handlers, silencioso",
        severity="medium",
        occurrences=[
            "src/dev_autonomo/control_plane/routers/foo.py:42",
            "src/dev_autonomo/control_plane/routers/bar.py:117",
        ],
        recommendation="Usar exception especifica ou HTTPException com status correto",
    )
    print(f"[antipattern concrete] OK: {len(ap.occurrences)} occurrences")


def test_reject_missing_architect():
    try:
        OnboardingAnalysisOutput(
            summary="x" * 60,
            stacks=[StackDetected(
                slug="python-fastapi", name="x", paths=["src/"],
                framework=None, framework_version=None,
                conventions=StackConventions(
                    observed_patterns=_conv5(), recommended_for_agents=_conv5(),
                ),
            )],
            jira_projects=[],
            recommended_agents=[
                AgentRecommendation(
                    tier="dev", stack_slug="python-fastapi",
                    rationale="rationale com mais que 10 chars",
                ),
                AgentRecommendation(
                    tier="reviewer", stack_slug=None,
                    rationale="rationale com mais que 10 chars",
                ),
            ],
            tool_calls_summary=ToolCallsSummary(
                file_reads=10, bash_commands=5,
            ),
        )
        print("[missing architect] FAIL: aceitou sem Architect")
    except ValidationError as e:
        print(f"[missing architect] OK rejeitou: 'architect' in error={'architect' in str(e)}")


def test_reject_dev_without_stack():
    try:
        OnboardingAnalysisOutput(
            summary="x" * 60,
            stacks=[StackDetected(
                slug="python-fastapi", name="x", paths=["src/"],
                framework=None, framework_version=None,
                conventions=StackConventions(
                    observed_patterns=_conv5(), recommended_for_agents=_conv5(),
                ),
            )],
            jira_projects=[],
            recommended_agents=[
                AgentRecommendation(
                    tier="architect", stack_slug=None,
                    rationale="rationale com mais que 10 chars",
                ),
                AgentRecommendation(
                    tier="dev", stack_slug=None,  # Dev sem stack — invalido
                    rationale="rationale com mais que 10 chars",
                ),
            ],
            tool_calls_summary=ToolCallsSummary(file_reads=10, bash_commands=5),
        )
        print("[dev no stack] FAIL: aceitou Dev sem stack")
    except ValidationError as e:
        print(f"[dev no stack] OK rejeitou: stack_slug in error={'stack_slug' in str(e)}")


def test_reject_jira_format():
    try:
        OnboardingAnalysisOutput(
            summary="x" * 60,
            stacks=[StackDetected(
                slug="python-fastapi", name="x", paths=["src/"],
                framework=None, framework_version=None,
                conventions=StackConventions(
                    observed_patterns=_conv5(), recommended_for_agents=_conv5(),
                ),
            )],
            jira_projects=["leo"],  # lowercase invalido
            recommended_agents=[
                AgentRecommendation(
                    tier="architect", stack_slug=None,
                    rationale="rationale com mais que 10 chars",
                ),
                AgentRecommendation(
                    tier="dev", stack_slug="python-fastapi",
                    rationale="rationale com mais que 10 chars",
                ),
            ],
            tool_calls_summary=ToolCallsSummary(file_reads=10, bash_commands=5),
        )
        print("[jira lowercase] FAIL: aceitou jira lowercase")
    except ValidationError as e:
        print(f"[jira lowercase] OK rejeitou")


def test_reject_short_summary():
    try:
        OnboardingAnalysisOutput(
            summary="curto",  # < 50 chars
            stacks=[StackDetected(
                slug="python-fastapi", name="x", paths=["src/"],
                framework=None, framework_version=None,
                conventions=StackConventions(
                    observed_patterns=_conv5(), recommended_for_agents=_conv5(),
                ),
            )],
            jira_projects=[],
            recommended_agents=[
                AgentRecommendation(
                    tier="architect", stack_slug=None,
                    rationale="rationale com mais que 10 chars",
                ),
                AgentRecommendation(
                    tier="dev", stack_slug="python-fastapi",
                    rationale="rationale com mais que 10 chars",
                ),
            ],
            tool_calls_summary=ToolCallsSummary(file_reads=10, bash_commands=5),
        )
        print("[short summary] FAIL: aceitou summary curto")
    except ValidationError as e:
        print(f"[short summary] OK rejeitou")


def test_extra_fields_forbidden():
    """Schema strict — campo extra eh rejeitado."""
    try:
        StackDetected(
            slug="python-fastapi", name="x", paths=["src/"],
            framework=None, framework_version=None,
            conventions=StackConventions(
                observed_patterns=_conv5(), recommended_for_agents=_conv5(),
            ),
            mystery_field="oi",  # extra
        )
        print("[extra fields] FAIL: aceitou campo extra")
    except ValidationError as e:
        print(f"[extra fields] OK rejeitou: 'extra' in error={'extra' in str(e).lower() or 'mystery' in str(e).lower()}")


test_valid_minimal()
test_reject_slug_invalid()
test_reject_conventions_shallow()
test_reject_anti_pattern_vague()
test_anti_pattern_concrete()
test_reject_missing_architect()
test_reject_dev_without_stack()
test_reject_jira_format()
test_reject_short_summary()
test_extra_fields_forbidden()
print("\n=== SMOKE SCHEMAS OK ===")
