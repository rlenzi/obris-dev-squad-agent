"""Smoke do grader sem chamar Haiku real — mocka response."""
import asyncio
from decimal import Decimal
from unittest.mock import MagicMock, patch

from dev_autonomo.onboarding.grader import (
    grade_output, DEFAULT_OA_RUBRIC, _extract_json_payload,
)
from dev_autonomo.onboarding.schemas import (
    OnboardingAnalysisOutput, StackDetected, StackConventions,
    AgentRecommendation, ToolCallsSummary,
)


def _conv5():
    return {
        "testing": "pytest com pytest-asyncio em tests/",
        "naming": "snake_case modulos, PascalCase classes",
        "imports": "absolute imports a partir de dev_autonomo",
        "error_handling": "HTTPException nos routers",
        "commits": "tipo(escopo): descricao",
    }


def _valid_output():
    return OnboardingAnalysisOutput(
        summary="Esse é um repo Python/FastAPI bem estruturado com testes em tests/.",
        stacks=[StackDetected(
            slug="python-fastapi", name="Backend",
            paths=["src/"], framework="fastapi", framework_version="0.115",
            conventions=StackConventions(
                observed_patterns=_conv5(), recommended_for_agents=_conv5(),
            ),
        )],
        jira_projects=["LEO"],
        recommended_agents=[
            AgentRecommendation(tier="architect", stack_slug=None, rationale="Coord squad"),
            AgentRecommendation(tier="dev", stack_slug="python-fastapi", rationale="Backend dev"),
        ],
        tool_calls_summary=ToolCallsSummary(
            file_reads=42, bash_commands=15,
            git_log_called=True, git_log_max_count=100,
        ),
    )


def _make_fake_response(text: str, in_tokens=500, out_tokens=200):
    block = MagicMock()
    block.type = "text"
    block.text = text
    resp = MagicMock()
    resp.content = [block]
    resp.usage.input_tokens = in_tokens
    resp.usage.output_tokens = out_tokens
    return resp


def test_extract_json_payload():
    """Strip markdown fence quando presente."""
    plain = '{"a": 1}'
    assert _extract_json_payload(plain) == '{"a": 1}'

    fenced = '```json\n{"a": 1}\n```'
    assert _extract_json_payload(fenced) == '{"a": 1}'

    fenced_alt = '```\n{"a": 1}\n```'
    assert _extract_json_payload(fenced_alt) == '{"a": 1}'
    print("[extract_json] OK")


async def test_grade_all_pass():
    """Haiku diz que tudo passou → overall=True, feedback vazio."""
    out = _valid_output()
    haiku_response = {
        "overall_passed": True,
        "checks": [
            {"check_id": "scan_breadth", "passed": True, "reason": "42 file_reads adequado"},
            {"check_id": "conventions_depth", "passed": True, "reason": "5 categorias substantivas"},
            {"check_id": "anti_patterns_evidence", "passed": True, "reason": "lista vazia eh OK"},
            {"check_id": "tests_examined", "passed": True, "reason": "menciona pytest"},
            {"check_id": "git_history_checked", "passed": True, "reason": "git_log -100"},
        ],
        "feedback_for_retry": "",
    }
    fake_resp = _make_fake_response(__import__("json").dumps(haiku_response))
    mock_client = MagicMock()
    mock_client.messages.create.return_value = fake_resp

    verdict = await grade_output(out, anthropic_client=mock_client)
    assert verdict.overall_passed is True
    assert len(verdict.checks) == 5
    assert all(c.passed for c in verdict.checks)
    assert verdict.feedback_for_retry == ""
    assert verdict.input_tokens == 500
    print(f"[all_pass] OK overall={verdict.overall_passed} cost=${verdict.cost_usd}")


async def test_grade_one_fail():
    """Haiku falha 1 check → overall=False, feedback presente."""
    out = _valid_output()
    haiku_response = {
        "overall_passed": False,
        "checks": [
            {"check_id": "scan_breadth", "passed": True, "reason": "verifiquei e atende"},
            {"check_id": "conventions_depth", "passed": False, "reason": "categorias muito superficiais — 1 frase cada"},
            {"check_id": "anti_patterns_evidence", "passed": True, "reason": "vazio ok"},
            {"check_id": "tests_examined", "passed": True, "reason": "pytest ok"},
            {"check_id": "git_history_checked", "passed": True, "reason": "git log -100"},
        ],
        "feedback_for_retry": "Detalhe mais as conventions — cada categoria precisa ter 2+ frases sobre o que voce observou.",
    }
    fake_resp = _make_fake_response(__import__("json").dumps(haiku_response))
    mock_client = MagicMock()
    mock_client.messages.create.return_value = fake_resp

    verdict = await grade_output(out, anthropic_client=mock_client)
    assert verdict.overall_passed is False
    failed = [c for c in verdict.checks if not c.passed]
    assert len(failed) == 1
    assert failed[0].check_id == "conventions_depth"
    assert "Detalhe mais" in verdict.feedback_for_retry
    print(f"[one_fail] OK feedback={verdict.feedback_for_retry[:50]!r}")


async def test_grade_omitted_check():
    """Haiku omite 1 check → marca como FAILED por omissao."""
    out = _valid_output()
    # Faltam 2 checks (anti_patterns_evidence e tests_examined)
    haiku_response = {
        "overall_passed": True,
        "checks": [
            {"check_id": "scan_breadth", "passed": True, "reason": "verifiquei e atende"},
            {"check_id": "conventions_depth", "passed": True, "reason": "verifiquei e atende"},
            {"check_id": "git_history_checked", "passed": True, "reason": "verifiquei e atende"},
        ],
        "feedback_for_retry": "",
    }
    fake_resp = _make_fake_response(__import__("json").dumps(haiku_response))
    mock_client = MagicMock()
    mock_client.messages.create.return_value = fake_resp

    verdict = await grade_output(out, anthropic_client=mock_client)
    # Overall deve ser False (omissao bloqueia pass)
    assert verdict.overall_passed is False
    assert len(verdict.checks) == 5  # grader incluiu os omitidos
    omitted = [c for c in verdict.checks if not c.passed]
    assert {c.check_id for c in omitted} == {"anti_patterns_evidence", "tests_examined"}
    print(f"[omitted] OK overall={verdict.overall_passed} omitted={[c.check_id for c in omitted]}")


async def test_grade_markdown_wrapped():
    """Haiku as vezes embrulha em ```json``` — deve funcionar."""
    out = _valid_output()
    haiku_text = "```json\n" + __import__("json").dumps({
        "overall_passed": True,
        "checks": [
            {"check_id": c.id, "passed": True, "reason": "verifiquei e atende"}
            for c in DEFAULT_OA_RUBRIC
        ],
        "feedback_for_retry": "",
    }) + "\n```"
    fake_resp = _make_fake_response(haiku_text)
    mock_client = MagicMock()
    mock_client.messages.create.return_value = fake_resp

    verdict = await grade_output(out, anthropic_client=mock_client)
    assert verdict.overall_passed is True
    print(f"[markdown_wrap] OK")


async def main():
    test_extract_json_payload()
    await test_grade_all_pass()
    await test_grade_one_fail()
    await test_grade_omitted_check()
    await test_grade_markdown_wrapped()
    print("\n=== SMOKE GRADER OK ===")


asyncio.run(main())
