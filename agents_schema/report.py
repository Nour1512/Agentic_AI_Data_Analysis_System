from typing import Any

from pydantic import BaseModel, Field

from .common import (
    ErrorInfo,
    WarningInfo,
)


class ReportChart(BaseModel):
    title: str
    chart_type: str
    insight: str | None = None
    image_path: str | None = None


class ReportRequest(BaseModel):
    request_id: str

    title: str

    original_question: str

    summary: str

    key_findings: list[str] = Field(
        default_factory=list
    )

    business_context: list[str] = Field(
        default_factory=list
    )

    recommendations: list[str] = Field(
        default_factory=list
    )

    charts: list[ReportChart] = Field(
        default_factory=list
    )

    additional_context: list[str] = Field(
        default_factory=list
    )

    # Actual retrieved data for the report to include tables/data overviews
    data_rows: list[dict[str, Any]] = Field(
        default_factory=list
    )

    data_columns: list[str] = Field(
        default_factory=list
    )

    row_count: int = 0

    sql_query: str | None = None

    canonical_metrics: dict[str, Any] = Field(
        default_factory=dict
    )


class ReportKPI(BaseModel):
    label: str
    value: str
    description: str | None = None


class ReportInsight(BaseModel):
    title: str
    description: str
    value: str | None = None


class StructuredReport(BaseModel):
    title: str
    subtitle: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    executive_summary: str
    objective: str
    data_overview: str | None = None
    kpis: list[ReportKPI] = Field(default_factory=list)
    key_findings: list[str] = Field(default_factory=list)
    visualizations: list[ReportChart] = Field(default_factory=list)
    insights: list[ReportInsight] = Field(default_factory=list)
    detailed_analysis: str
    conclusion: str
    recommendations: list[str] = Field(default_factory=list)
    data_quality: list[str] = Field(default_factory=list)


class ReportResponse(BaseModel):
    request_id: str

    success: bool

    report_path: str | None = None

    report_url: str | None = None

    report_html: str | None = None

    structured_report: StructuredReport | None = None

    error: ErrorInfo | None = None

    warnings: list[WarningInfo] = Field(
        default_factory=list
    )