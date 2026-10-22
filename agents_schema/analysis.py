from typing import Any

from pydantic import BaseModel, Field

from .common import (
    ConfidenceLevel,
    DataColumn,
    DataRow,
    ErrorInfo,
    OutputFormat,
    WarningInfo,
)


class AnalysisRequest(BaseModel):
    request_id: str

    original_question: str

    data_columns: list[DataColumn] = Field(
        default_factory=list
    )

    data_results: list[DataRow] = Field(
        default_factory=list
    )

    analysis_goals: list[str] = Field(
        default_factory=list
    )

    requested_formats: list[OutputFormat] = Field(
        default_factory=lambda: [OutputFormat.TEXT]
    )

    data_warnings: list[WarningInfo] = Field(
        default_factory=list
    )




class Insight(BaseModel):
    title: str
    description: str
    metric: str | None = None
    importance: str = Field(default="medium") # "high", "medium", "low"

class ChartRecommendation(BaseModel):
    chart_type: str

    title: str

    x_axis_column: str | None = None

    y_axis_column: str | None = None

    group_by_column: str | None = None

    rationale: str | None = None



class AnalysisResponse(BaseModel):
    request_id: str

    summary: str

    key_findings: list[Insight] = Field(
        default_factory=list
    )

    business_context: list[str] = Field(
        default_factory=list
    )

    recommendations: list[str] = Field(
        default_factory=list
    )

    confidence_level: ConfidenceLevel

    chart_recommendations: list[ChartRecommendation] = Field(
        default_factory=list
    )

    warnings: list[WarningInfo] = Field(
        default_factory=list
    )

    error: ErrorInfo | None = None