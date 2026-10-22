from typing import Any

from pydantic import BaseModel, Field


class VisualizationRequest(BaseModel):
    """Request to generate a single chart (used by LLM-recommended charts)."""
    request_id: str
    chart_type: str
    title: str
    data: list[dict[str, Any]]
    x_axis_column: str | None = None
    y_axis_column: str | None = None
    group_by_column: str | None = None
    output_format: str = "png"
    output_directory: str = "outputs/charts"


from .common import ErrorInfo


class ChartConfig(BaseModel):
    """Configuration for a single chart that the frontend can render natively.

    Axis metadata tells the renderer exactly how to map data to axes
    without guessing based on column order.
    """
    chart_type: str  # bar, line, pie, scatter, histogram, horizontal_bar
    title: str
    description: str | None = None
    purpose: str | None = None
    insight: str | None = None
    image_path: str | None = None

    # Semantic axis fields — the renderer uses these directly
    x_column: str | None = None
    y_column: str | None = None
    group_column: str | None = None

    x_axis_type: str | None = None   # "numeric", "categorical", "datetime"
    y_axis_type: str | None = None   # "numeric", "categorical", "datetime"
    x_axis_label: str | None = None  # Human-readable label, e.g. "Customer Count"
    y_axis_label: str | None = None  # Human-readable label, e.g. "City"

    data: list[dict[str, Any]] = Field(default_factory=list)
    success: bool = True
    error_message: str | None = None


class KPICard(BaseModel):
    """A single KPI metric card for the dashboard."""
    label: str
    value: str
    delta: str | None = None
    delta_color: str = "normal"  # "normal", "inverse", "off"


class CanonicalMetrics(BaseModel):
    """Authoritative metrics computed once from the actual SQL data.

    Every downstream consumer (KPIs, charts, insights, report) must
    use these exact numbers to prevent contradictions.
    """
    record_count: int = 0
    column_names: list[str] = Field(default_factory=list)

    # Per-numeric-column aggregates
    numeric_summaries: dict[str, dict[str, Any]] = Field(default_factory=dict)
    # e.g. {"customer_count": {"total": 1727, "average": 95.94, "min": 60, "max": 145}}

    # Top/bottom category per numeric column (if a categorical col exists)
    top_categories: dict[str, dict[str, Any]] = Field(default_factory=dict)
    # e.g. {"customer_count": {"top": "Aswan", "top_value": 145, "bottom": "Suez", "bottom_value": 60}}

    field_types: dict[str, str] = Field(default_factory=dict)
    # e.g. {"city": "categorical", "customer_count": "numeric"}


class DashboardConfig(BaseModel):
    """Full dashboard configuration for frontend rendering."""
    title: str = "Data Dashboard"
    description: str | None = None
    kpis: list[KPICard] = Field(default_factory=list)
    charts: list[ChartConfig] = Field(default_factory=list)
    data_table: list[dict[str, Any]] = Field(default_factory=list)
    columns: list[str] = Field(default_factory=list)
    filter_columns: list[str] = Field(default_factory=list)
    user_question: str | None = None
    total_planned: int = 0
    total_generated: int = 0
    total_failed: int = 0

    canonical_metrics: CanonicalMetrics | None = None


class VisualizationResponse(BaseModel):
    request_id: str
    success: bool
    chart_path: str | None = None
    chart_url: str | None = None
    dashboard: DashboardConfig | None = None
    error: ErrorInfo | None = None