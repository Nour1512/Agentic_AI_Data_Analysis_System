"""Evidence-based analysis agent for SQL query results.

The agent deliberately has no database dependency.  It receives the rows
already retrieved by the SQL agent and asks the configured LLM to turn those
rows into a validated, business-friendly ``AnalysisResponse``.
"""

from __future__ import annotations

import json
import logging
from typing import Protocol

from agents_schema.analysis import AnalysisRequest, AnalysisResponse
from agents_schema.common import ConfidenceLevel, ErrorInfo, WarningInfo
from prompts.analysis_prompt import ANALYSIS_SYSTEM_PROMPT


logger = logging.getLogger(__name__)


class LLMClient(Protocol):
    """Minimal interface required from the shared LLM client."""

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        """Return the model's text response."""


class AnalysisAgent:
    """Analyze validated data and return evidence-based business insights.

    The injected client keeps this module independent of a particular model
    provider and makes it straightforward to unit test with a fake client.
    """

    def __init__(self, llm_client: LLMClient) -> None:
        self.llm_client = llm_client

    def run(self, analysis_request: AnalysisRequest) -> AnalysisResponse:
        """Generate and validate an analysis for a structured request.

        Model and validation failures are returned as a structured response so
        the orchestrator can complete the workflow with a transparent error.
        """

        self._validate_request(analysis_request)

        if not analysis_request.data_results:
            return self._empty_result_response(analysis_request)

        logger.info(
            "Analysis Agent started for request_id=%s with %d rows.",
            analysis_request.request_id,
            len(analysis_request.data_results),
        )

        try:
            raw_response = self.llm_client.generate(
                system_prompt=ANALYSIS_SYSTEM_PROMPT,
                user_prompt=self._build_user_prompt(analysis_request),
            )
            response = self._parse_response(raw_response)
            response.request_id = analysis_request.request_id

            logger.info(
                "Analysis Agent completed for request_id=%s.",
                analysis_request.request_id,
            )
            return response

        except Exception as exc:
            logger.exception(
                "Analysis Agent failed for request_id=%s.",
                analysis_request.request_id,
            )
            return AnalysisResponse(
                request_id=analysis_request.request_id,
                summary="Analysis could not be generated.",
                confidence_level=ConfidenceLevel.LOW,
                error=ErrorInfo(
                    code="ANALYSIS_ERROR",
                    message="Failed to analyze the provided data.",
                    details=str(exc),
                ),
            )

    @staticmethod
    def _validate_request(analysis_request: AnalysisRequest) -> None:
        """Validate the minimum information needed for traceable analysis."""

        if not analysis_request.request_id.strip():
            raise ValueError("AnalysisRequest.request_id cannot be empty.")
        if not analysis_request.original_question.strip():
            raise ValueError(
                "AnalysisRequest.original_question cannot be empty.")

    @staticmethod
    def _build_user_prompt(analysis_request: AnalysisRequest) -> str:
        """Serialize only the supplied evidence and required analysis context.

        Columns are annotated with semantic types so the LLM knows which
        columns are identifiers (count-only) and which are measures.
        """
        from services.visualization_service import classify_fields, SEMANTIC_IDENTIFIER, SEMANTIC_MEASURE
        import pandas as pd

        # Build a quick semantic profile of the columns
        sample_data = [row.values for row in analysis_request.data_results[:5]]
        semantic_annotations = {}
        if sample_data:
            try:
                df = pd.DataFrame(sample_data)
                field_types = classify_fields(df)
                semantic_annotations = field_types
            except Exception:
                pass

        annotated_columns = []
        for column in analysis_request.data_columns:
            col_info = column.model_dump(mode="json")
            sem_type = semantic_annotations.get(column.name, "unknown")
            col_info["semantic_type"] = sem_type
            if sem_type == SEMANTIC_IDENTIFIER:
                col_info["allowed_aggregations"] = ["COUNT", "COUNT_DISTINCT"]
                col_info["disallowed_aggregations"] = ["SUM", "AVG", "MIN", "MAX"]
                col_info["note"] = "This is an entity identifier. NEVER use SUM/AVG on it."
            elif sem_type == SEMANTIC_MEASURE:
                col_info["allowed_aggregations"] = ["SUM", "AVG", "MIN", "MAX", "COUNT"]
            annotated_columns.append(col_info)

        request_data = {
            "request_id": analysis_request.request_id,
            "original_question": analysis_request.original_question,
            "analysis_goals": analysis_request.analysis_goals,
            "requested_formats": [
                output_format.value
                for output_format in analysis_request.requested_formats
            ],
            "data_columns": annotated_columns,
            "data_results_sample": [
                row.values for row in analysis_request.data_results[:5]
            ],
            "data_warnings": [
                warning.model_dump(mode="json")
                for warning in analysis_request.data_warnings
            ],
            "response_schema": {
                "request_id": "string",
                "summary": "string",
                "key_findings": [
                    {
                        "title": "string",
                        "description": "string",
                        "metric": "string | null",
                        "importance": "high | medium | low"
                    }
                ],
                "business_context": ["string"],
                "recommendations": ["string"],
                "confidence_level": "high | medium | low",
                "chart_recommendations": [
                    {
                        "chart_type": "string",
                        "title": "string",
                        "x_axis_column": "string | null",
                        "y_axis_column": "string | null",
                        "group_by_column": "string | null",
                        "rationale": "string | null",
                    },
                ],
                "warnings": [{"code": "string", "message": "string", "details": "string | null"}],
            },
        }

        return (
            "Analyze this request using only the supplied dataset. Return only "
            "a JSON object that matches response_schema.\n\n"
            "IMPORTANT: Each column has a 'semantic_type' annotation. "
            "Columns marked 'identifier' are entity IDs — NEVER use SUM or AVG on them. "
            "Use COUNT or COUNT_DISTINCT instead. "
            "Only columns marked 'numeric_measure' should be aggregated with SUM/AVG/MIN/MAX.\n\n"
            f"ANALYSIS REQUEST:\n{json.dumps(request_data, indent=2, default=str)}"
        )

    @classmethod
    def _parse_response(cls, raw_response: str) -> AnalysisResponse:
        """Remove accidental code fences and validate the model JSON."""

        try:
            data = json.loads(cls._clean_json(raw_response))
        except json.JSONDecodeError as exc:
            raise ValueError(
                "Analysis Agent LLM response was not valid JSON.") from exc

        try:
            return AnalysisResponse.model_validate(data)
        except Exception as exc:
            raise ValueError(
                "Analysis Agent response does not match AnalysisResponse schema."
            ) from exc

    @staticmethod
    def _clean_json(response: str) -> str:
        """Remove a single Markdown fence when a model adds one accidentally."""

        cleaned = response.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[len("```json"):].strip()
        elif cleaned.startswith("```"):
            cleaned = cleaned[3:].strip()
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3].strip()
        return cleaned

    @staticmethod
    def _empty_result_response(analysis_request: AnalysisRequest) -> AnalysisResponse:
        """Avoid asking the LLM to infer insights when no rows were returned."""

        warning = WarningInfo(
            code="EMPTY_DATASET",
            message="No data rows were available for analysis.",
            details="The SQL/data-retrieval stage returned an empty result set.",
        )
        return AnalysisResponse(
            request_id=analysis_request.request_id,
            summary="No data was available to answer the question.",
            confidence_level=ConfidenceLevel.LOW,
            warnings=[*analysis_request.data_warnings, warning],
        )
