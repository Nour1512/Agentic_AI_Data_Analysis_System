"""Offline unit tests for :mod:`agents.analysis_agent`."""

import json
import unittest

from agents.analysis_agent import AnalysisAgent
from agents_schema.analysis import AnalysisRequest
from agents_schema.common import ConfidenceLevel, DataColumn, DataRow


class FakeLLMClient:
    """Record the prompt and return a controlled model response."""

    def __init__(self, response: str) -> None:
        self.response = response
        self.calls: list[dict[str, str]] = []

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        self.calls.append(
            {"system_prompt": system_prompt, "user_prompt": user_prompt}
        )
        return self.response


class AnalysisAgentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.request = AnalysisRequest(
            request_id="analysis-001",
            original_question="Which product has the highest sales?",
            analysis_goals=["Identify the top-selling product"],
            data_columns=[
                DataColumn(name="product", data_type="string"),
                DataColumn(name="sales", data_type="integer"),
            ],
            data_results=[
                DataRow(values={"product": "Laptop", "sales": 150}),
                DataRow(values={"product": "Phone", "sales": 120}),
            ],
        )

    def test_returns_validated_response_and_uses_supplied_data(self) -> None:
        client = FakeLLMClient(
            json.dumps(
                {
                    "request_id": "model-provided-id",
                    "summary": "Laptop has the highest sales at 150 units.",
                    "key_findings": ["Laptop sold 30 more units than Phone."],
                    "business_context": ["Laptop is the leading product in this result set."],
                    "recommendations": ["Maintain Laptop inventory."],
                    "confidence_level": "high",
                    "chart_recommendation": {
                        "chart_type": "bar",
                        "title": "Sales by Product",
                        "x_axis_column": "product",
                        "y_axis_column": "sales",
                        "rationale": "A bar chart compares product totals clearly.",
                    },
                }
            )
        )

        response = AnalysisAgent(client).run(self.request)

        self.assertEqual(response.request_id, self.request.request_id)
        self.assertEqual(response.confidence_level, ConfidenceLevel.HIGH)
        self.assertEqual(response.chart_recommendation.chart_type, "bar")
        self.assertEqual(len(client.calls), 1)
        self.assertIn('"sales": 150', client.calls[0]["user_prompt"])

    def test_empty_result_does_not_call_the_llm(self) -> None:
        client = FakeLLMClient("this response must not be used")
        request = self.request.model_copy(update={"data_results": []})

        response = AnalysisAgent(client).run(request)

        self.assertEqual(response.confidence_level, ConfidenceLevel.LOW)
        self.assertEqual(response.warnings[0].code, "EMPTY_DATASET")
        self.assertEqual(client.calls, [])

    def test_invalid_model_json_becomes_structured_error(self) -> None:
        response = AnalysisAgent(FakeLLMClient("not valid json")).run(self.request)

        self.assertEqual(response.confidence_level, ConfidenceLevel.LOW)
        self.assertEqual(response.error.code, "ANALYSIS_ERROR")
        self.assertIn("could not be generated", response.summary)

    def test_empty_question_is_rejected(self) -> None:
        request = self.request.model_copy(update={"original_question": "  "})

        with self.assertRaisesRegex(ValueError, "original_question"):
            AnalysisAgent(FakeLLMClient("{}")).run(request)


if __name__ == "__main__":
    unittest.main()
