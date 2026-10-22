from pathlib import Path

from agents.report_agent import ReportAgent
from agents_schema.report import ReportRequest


class FakeLLMClient:
    """Fake LLM client for testing."""

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        return """
Report Title: Sales Analysis

Executive Summary:
Sales increased during the analyzed period.

Key Findings:
- Sales increased from January to March.
- March recorded the highest sales value.

Business Context:
The overall trend indicates positive sales performance.

Recommendations:
Continue monitoring the sales trend.
"""


def test_report_agent_success(tmp_path: Path):
    """Test successful report generation."""

    request = ReportRequest(
        request_id="test_report_001",
        title="Sales Analysis",
        original_question="How did sales change over time?",
        summary="Sales increased during the analyzed period.",
        key_findings=[
            "Sales increased from January to March.",
            "March recorded the highest sales value.",
        ],
        business_context=[
            "The overall trend indicates positive sales performance."
        ],
        recommendations=[
            "Continue monitoring the sales trend."
        ],
        chart_path=None,
        additional_context=[],
    )

    agent = ReportAgent(
        llm_client=FakeLLMClient(),
        output_dir=str(tmp_path),
    )

    response = agent.run(request)

    assert response.success is True
    assert response.request_id == "test_report_001"
    assert response.report_path is not None

    report_path = Path(response.report_path)

    assert report_path.exists()

    content = report_path.read_text(encoding="utf-8")

    assert "Sales Analysis" in content
    assert "Sales increased" in content


def test_report_agent_llm_error(tmp_path: Path):
    """Test Report Agent behavior when the LLM fails."""

    class FailingLLMClient:
        def generate(self, system_prompt: str, user_prompt: str) -> str:
            raise RuntimeError("LLM connection failed")

    request = ReportRequest(
        request_id="test_report_002",
        title="Sales Analysis",
        original_question="How did sales change?",
        summary="Sales increased.",
    )

    agent = ReportAgent(
        llm_client=FailingLLMClient(),
        output_dir=str(tmp_path),
    )

    response = agent.run(request)

    assert response.success is False
    assert response.request_id == "test_report_002"
    assert response.error is not None
    assert response.error.code == "REPORT_ERROR"
    assert response.report_path is None


def test_report_agent_empty_request_id(tmp_path: Path):
    """Test validation of an empty request ID."""

    request = ReportRequest(
        request_id="",
        title="Sales Analysis",
        original_question="How did sales change?",
        summary="Sales increased.",
    )

    agent = ReportAgent(
        llm_client=FakeLLMClient(),
        output_dir=str(tmp_path),
    )

    try:
        agent.run(request)
        assert False, "Expected ValueError"
    except ValueError as exc:
        assert "request_id" in str(exc)