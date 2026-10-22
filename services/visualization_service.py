"""Visualization Service — generates complete multi-chart dashboards.

Architecture:
    1. Receive ALL retrieved data + user question + optional LLM chart recommendations
    2. Analyze the data: detect column types, unique values, date columns, relationships
    3. Create a VISUALIZATION PLAN: which charts to generate and why
    4. Generate each chart independently (one failure does NOT kill the dashboard)
    5. Validate each chart before including it
    6. Build KPI cards from the actual data
    7. Compute canonical metrics from the actual data (single source of truth)
    8. Return a single unified DashboardConfig with all charts, KPIs, metrics, and metadata
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd
import numpy as np

from agents_schema.visualization import (
    CanonicalMetrics,
    ChartConfig,
    DashboardConfig,
    KPICard,
    VisualizationRequest,
    VisualizationResponse,
)
from agents_schema.common import ErrorInfo


logger = logging.getLogger(__name__)


# ====================================================================== #
# IDENTIFIER DETECTION PATTERNS
# ====================================================================== #

# Case-insensitive patterns that indicate a column is an entity identifier,
# NOT a business measure.  These must NEVER be aggregated with SUM/AVG.
IDENTIFIER_PATTERNS: list[str] = [
    "_id", "id_", "identifier",
    "customer_id", "customerid", "cust_id",
    "order_id", "orderid", "ord_id",
    "product_id", "productid", "prod_id",
    "user_id", "userid",
    "account_id", "accountid",
    "employee_id", "employeeid", "emp_id",
    "invoice_id", "invoiceid",
    "transaction_id", "transactionid",
    "item_id", "itemid",
    "category_id", "categoryid",
    "supplier_id", "supplierid",
    "store_id", "storeid",
    "branch_id", "branchid",
    "region_id", "regionid",
]

# Semantic type constants
SEMANTIC_IDENTIFIER = "identifier"
SEMANTIC_MEASURE = "numeric_measure"
SEMANTIC_CATEGORICAL = "categorical"
SEMANTIC_DATETIME = "datetime"
SEMANTIC_BOOLEAN = "boolean"
SEMANTIC_TEXT = "text"


def _is_identifier_by_name(col_name: str) -> bool:
    """Check if a column name matches known identifier patterns."""
    lower = col_name.lower().strip().replace(" ", "_")

    # Exact match: the column is literally named "id"
    if lower == "id":
        return True

    # Ends with "_id" or " id" (e.g. "Customer Id", "customer_id")
    if lower.endswith("_id") or lower.endswith(" id"):
        return True

    # Starts with "id_" (e.g. "id_customer")
    if lower.startswith("id_"):
        return True

    # Check against the full pattern list
    for pattern in IDENTIFIER_PATTERNS:
        if pattern in lower:
            return True

    return False


def _is_identifier_by_data(series: pd.Series, row_count: int) -> bool:
    """Heuristic: a numeric column with very high uniqueness and
    sequential-like values is likely an identifier, not a measure.

    This is ONLY used as a fallback when the name check didn't match.
    We require a minimum dataset size (20 rows) and strong sequential
    evidence to avoid false positives on small datasets.
    """
    if row_count < 20:
        return False  # Too few rows to reliably distinguish
    try:
        nunique = series.nunique()
        uniqueness_ratio = nunique / max(row_count, 1)

        # >95% unique integers that are clearly sequential → identifier
        if uniqueness_ratio > 0.95 and pd.api.types.is_integer_dtype(series):
            sorted_vals = series.dropna().sort_values()
            if len(sorted_vals) >= 10:
                diffs = sorted_vals.diff().dropna()
                # Mostly increments of 1 → sequential ID
                if (diffs == 1).mean() > 0.85:
                    return True
    except Exception:
        pass
    return False


# ====================================================================== #
# FIELD NAME HUMANIZER
# ====================================================================== #

def humanize_field_name(name: str) -> str:
    """Convert a field name like 'customer_count' to 'Customer Count'."""
    if not name:
        return name
    result = name.replace("_", " ").replace("-", " ")
    # Insert space before uppercase letters in camelCase
    result = re.sub(r'([a-z])([A-Z])', r'\1 \2', result)
    return result.title()


def _entity_display_name(col_name: str) -> str:
    """Turn an identifier column name into a human entity label.

    Examples:
        customer_id  → Customers
        order_id     → Orders
        product_id   → Products
        Customer Id  → Customers
        id           → Records
    """
    lower = col_name.lower().strip().replace(" ", "_")
    # Strip trailing _id / id
    base = re.sub(r'[_\s]?id$', '', lower).strip("_").strip()
    if not base:
        return "Records"
    # Pluralise naively
    human = base.replace("_", " ").title()
    if not human.endswith("s"):
        human += "s"
    return human


def normalize_metric_label(aggregation: str, field_name: str) -> str:
    """Generate a human-friendly metric label, preventing duplicate words.

    Examples:
        ("sum",   "total_orders")   → "Total Orders"
        ("avg",   "average_price")  → "Average Price"
        ("count_distinct", "customer_id") → "Customers"
        ("count", "order_id")       → "Orders"
        ("sum",   "revenue")        → "Total Revenue"
    """
    agg = aggregation.lower().strip()
    lower_field = field_name.lower().strip().replace(" ", "_")

    # For count/count_distinct on identifiers, use entity name
    if agg in ("count", "count_distinct"):
        if _is_identifier_by_name(field_name):
            return _entity_display_name(field_name)
        return f"Total {humanize_field_name(field_name)}"

    prefix_map = {
        "sum": "Total",
        "avg": "Average",
        "average": "Average",
        "mean": "Average",
        "min": "Minimum",
        "max": "Maximum",
        "median": "Median",
    }
    prefix = prefix_map.get(agg, agg.title())
    human = humanize_field_name(field_name)

    # Prevent duplicate prefix words: "Total Total Orders" → "Total Orders"
    human_words = human.split()
    if human_words and human_words[0].lower() == prefix.lower():
        return human  # Already starts with the prefix

    return f"{prefix} {human}"


# ====================================================================== #
# DATA NORMALIZER
# ====================================================================== #

def normalize_visualization_data(data: Any) -> pd.DataFrame:
    """Normalize any supported data format into a pandas DataFrame.

    Handles: list[dict], dict, DataFrame, list[list], list[tuple], JSON string.
    """
    if isinstance(data, pd.DataFrame):
        return data
    if isinstance(data, list):
        if not data:
            return pd.DataFrame()
        if isinstance(data[0], dict):
            return pd.DataFrame(data)
        return pd.DataFrame(data)
    if isinstance(data, dict):
        return pd.DataFrame([data]) if not any(isinstance(v, list) for v in data.values()) else pd.DataFrame(data)
    if isinstance(data, str):
        import json
        try:
            parsed = json.loads(data)
            return normalize_visualization_data(parsed)
        except (json.JSONDecodeError, TypeError):
            pass
    return pd.DataFrame()


# ====================================================================== #
# SEMANTIC FIELD TYPE CLASSIFIER
# ====================================================================== #

def classify_fields(df: pd.DataFrame) -> dict[str, str]:
    """Classify every column into a semantic type.

    Returns e.g. {"city": "categorical", "revenue": "numeric_measure",
                  "customer_id": "identifier", "order_date": "datetime"}

    Semantic types:
        identifier      — entity IDs (NEVER aggregate with SUM/AVG)
        numeric_measure  — true business metrics (Revenue, Quantity, etc.)
        categorical      — dimensions for grouping (City, Category, etc.)
        datetime         — time dimensions
        boolean          — binary flags
        text             — free-text / high-cardinality strings
    """
    field_types: dict[str, str] = {}
    row_count = len(df)

    for col in df.columns:
        # ---- 1. DATETIME ----
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            field_types[col] = SEMANTIC_DATETIME
            continue

        # ---- 2. BOOLEAN ----
        if pd.api.types.is_bool_dtype(df[col]):
            field_types[col] = SEMANTIC_BOOLEAN
            continue

        # ---- 3. NUMERIC (needs ID vs measure split) ----
        if pd.api.types.is_numeric_dtype(df[col]):
            # Check name-based identifier patterns FIRST
            if _is_identifier_by_name(col):
                field_types[col] = SEMANTIC_IDENTIFIER
                logger.info("[SEMANTIC] '%s' → IDENTIFIER (name pattern)", col)
                continue
            # Check data-based identifier heuristics
            if _is_identifier_by_data(df[col], row_count):
                field_types[col] = SEMANTIC_IDENTIFIER
                logger.info("[SEMANTIC] '%s' → IDENTIFIER (data heuristic)", col)
                continue
            # It's a real business measure
            field_types[col] = SEMANTIC_MEASURE
            continue

        # ---- 4. STRING-LIKE COLUMNS ----
        col_lower = col.lower()

        # Check for datetime-like string columns
        if any(kw in col_lower for kw in ("date", "time", "timestamp", "period")):
            try:
                pd.to_datetime(df[col], errors="raise", infer_datetime_format=True)
                field_types[col] = SEMANTIC_DATETIME
                continue
            except (ValueError, TypeError, OverflowError):
                pass

        # Categorical vs text: if unique ratio is low, it's categorical
        nunique = df[col].nunique()
        if nunique <= 50 or (nunique / max(row_count, 1)) < 0.5:
            field_types[col] = SEMANTIC_CATEGORICAL
        else:
            field_types[col] = SEMANTIC_TEXT

    return field_types


# ====================================================================== #
# DATA PROFILER
# ====================================================================== #

class DataProfile:
    """Profile of the retrieved dataset for chart planning."""

    def __init__(self, df: pd.DataFrame):
        self.df = df
        self.row_count = len(df)
        self.col_count = len(df.columns)
        self.columns = list(df.columns)

        self.field_types = classify_fields(df)

        # Semantic column groups
        self.identifier_cols = [c for c, t in self.field_types.items() if t == SEMANTIC_IDENTIFIER]
        self.measure_cols = [c for c, t in self.field_types.items() if t == SEMANTIC_MEASURE]
        self.categorical_cols = [c for c, t in self.field_types.items() if t == SEMANTIC_CATEGORICAL]
        self.date_cols = [c for c, t in self.field_types.items() if t == SEMANTIC_DATETIME]

        # Backward-compatible: numeric_cols = measure_cols (NOT identifiers)
        self.numeric_cols = self.measure_cols
        self.non_numeric_cols = [c for c in df.columns if c not in self.measure_cols]

        # Unique value counts for categorical columns
        self.unique_counts = {}
        for c in self.categorical_cols:
            try:
                self.unique_counts[c] = int(df[c].nunique())
            except Exception:
                self.unique_counts[c] = 0

    def log_profile(self):
        logger.info(
            "[VIZ PROFILE] %d rows x %d cols | identifiers=%s | measures=%s | categorical=%s | date=%s | types=%s",
            self.row_count, self.col_count,
            self.identifier_cols, self.measure_cols, self.categorical_cols, self.date_cols,
            self.field_types,
        )


# ====================================================================== #
# CANONICAL METRICS BUILDER
# ====================================================================== #

def build_canonical_metrics(df: pd.DataFrame, profile: DataProfile) -> CanonicalMetrics:
    """Compute authoritative metrics from the actual data.

    Every downstream consumer (KPIs, report, insights) MUST use these
    exact numbers to prevent contradictions.

    CRITICAL: Only NUMERIC_MEASURE columns are aggregated with SUM/AVG.
    IDENTIFIER columns get COUNT_DISTINCT only.
    """
    numeric_summaries: dict[str, dict[str, Any]] = {}
    top_categories: dict[str, dict[str, Any]] = {}

    # ---- Measure columns: full SUM/AVG/MIN/MAX ----
    for col in profile.measure_cols:
        try:
            series = df[col].dropna()
            numeric_summaries[col] = {
                "semantic_type": SEMANTIC_MEASURE,
                "total": round(float(series.sum()), 2),
                "average": round(float(series.mean()), 2),
                "min": round(float(series.min()), 2),
                "max": round(float(series.max()), 2),
                "median": round(float(series.median()), 2),
                "count": int(series.count()),
                "display_label": humanize_field_name(col),
            }
        except Exception:
            pass

    # ---- Identifier columns: COUNT DISTINCT only ----
    for col in profile.identifier_cols:
        try:
            count_distinct = int(df[col].nunique())
            entity_label = _entity_display_name(col)
            numeric_summaries[col] = {
                "semantic_type": SEMANTIC_IDENTIFIER,
                "count_distinct": count_distinct,
                "display_label": entity_label,
            }
            logger.info(
                "[CANONICAL] Identifier '%s' → COUNT_DISTINCT = %d (label: '%s')",
                col, count_distinct, entity_label,
            )
        except Exception:
            pass

    # ---- Top/bottom category per MEASURE col (NOT identifiers) ----
    if profile.categorical_cols:
        cat_col = profile.categorical_cols[0]
        for num_col in profile.measure_cols:
            try:
                grouped = df.groupby(cat_col)[num_col].sum()
                top_idx = grouped.idxmax()
                bottom_idx = grouped.idxmin()
                top_categories[num_col] = {
                    "category_field": cat_col,
                    "top": str(top_idx),
                    "top_value": round(float(grouped[top_idx]), 2),
                    "bottom": str(bottom_idx),
                    "bottom_value": round(float(grouped[bottom_idx]), 2),
                }
            except Exception:
                pass

    return CanonicalMetrics(
        record_count=profile.row_count,
        column_names=profile.columns,
        numeric_summaries=numeric_summaries,
        top_categories=top_categories,
        field_types=profile.field_types,
    )


# ====================================================================== #
# AXIS SEMANTICS — defines correct axis mapping per chart type
# ====================================================================== #

# For each chart type, which axis should be which field type
AXIS_SEMANTICS: dict[str, dict[str, str]] = {
    "bar":            {"x": "categorical", "y": "numeric"},
    "horizontal_bar": {"x": "numeric",     "y": "categorical"},
    "line":           {"x": "datetime",    "y": "numeric"},      # fallback: x=categorical
    "pie":            {"labels": "categorical", "values": "numeric"},
    "scatter":        {"x": "numeric",     "y": "numeric"},
    "histogram":      {"x": "numeric",     "y": None},           # y is auto (frequency)
}


def resolve_axes_for_chart_type(
    chart_type: str,
    profile: DataProfile,
    requested_x: str | None,
    requested_y: str | None,
    df: pd.DataFrame,
) -> dict[str, Any]:
    """Resolve axis assignments semantically based on chart type.

    Returns dict with keys: x_col, y_col, x_type, y_type, x_label, y_label.
    """

    semantics = AXIS_SEMANTICS.get(chart_type, AXIS_SEMANTICS["bar"])

    def find_column(requested: str | None, preferred_type: str | None, df: pd.DataFrame) -> str | None:
        """Find a column matching the requested name or preferred type."""
        if requested and requested in df.columns:
            return requested
        if requested:
            # Case-insensitive match
            lower_map = {c.lower().strip(): c for c in df.columns}
            if requested.lower().strip() in lower_map:
                return lower_map[requested.lower().strip()]
            # Partial match
            for col in df.columns:
                if requested.lower() in col.lower() or col.lower() in requested.lower():
                    return col

        # Fall back to first column of preferred type
        if preferred_type == "numeric" and profile.numeric_cols:
            return profile.numeric_cols[0]
        if preferred_type == "categorical" and profile.categorical_cols:
            return profile.categorical_cols[0]
        if preferred_type == "datetime" and profile.date_cols:
            return profile.date_cols[0]
        if preferred_type == "datetime" and profile.categorical_cols:
            # Fallback for line charts when no datetime col exists
            return profile.categorical_cols[0]

        return df.columns[0] if len(df.columns) > 0 else None

    if chart_type == "pie":
        label_col = find_column(requested_x, "categorical", df)
        value_col = find_column(requested_y, "numeric", df)
        return {
            "x_col": label_col,   # labels
            "y_col": value_col,   # values
            "x_type": "categorical",
            "y_type": "numeric",
            "x_label": humanize_field_name(label_col) if label_col else None,
            "y_label": humanize_field_name(value_col) if value_col else None,
        }

    if chart_type == "histogram":
        num_col = find_column(requested_x or requested_y, "numeric", df)
        return {
            "x_col": num_col,
            "y_col": None,
            "x_type": "numeric",
            "y_type": "numeric",
            "x_label": humanize_field_name(num_col) if num_col else None,
            "y_label": "Frequency",
        }

    if chart_type == "scatter":
        x_col = find_column(requested_x, "numeric", df)
        # For y, try to find a different numeric column
        y_col = find_column(requested_y, "numeric", df)
        if y_col == x_col and len(profile.numeric_cols) >= 2:
            y_col = profile.numeric_cols[1]
        return {
            "x_col": x_col,
            "y_col": y_col,
            "x_type": "numeric",
            "y_type": "numeric",
            "x_label": humanize_field_name(x_col) if x_col else None,
            "y_label": humanize_field_name(y_col) if y_col else None,
        }

    if chart_type == "horizontal_bar":
        # x = numeric (value axis), y = categorical (category axis)
        x_col = find_column(requested_x if requested_x and profile.field_types.get(requested_x) == "numeric" else requested_y, "numeric", df)
        y_col = find_column(requested_y if requested_y and profile.field_types.get(requested_y) == "categorical" else requested_x, "categorical", df)
        # Ensure we didn't assign the same column to both
        if x_col == y_col:
            if profile.numeric_cols:
                x_col = profile.numeric_cols[0]
            if profile.categorical_cols:
                y_col = profile.categorical_cols[0]
        return {
            "x_col": x_col,
            "y_col": y_col,
            "x_type": "numeric",
            "y_type": "categorical",
            "x_label": humanize_field_name(x_col) if x_col else None,
            "y_label": humanize_field_name(y_col) if y_col else None,
        }

    if chart_type == "line":
        x_pref = "datetime" if profile.date_cols else "categorical"
        x_col = find_column(requested_x, x_pref, df)
        y_col = find_column(requested_y, "numeric", df)
        return {
            "x_col": x_col,
            "y_col": y_col,
            "x_type": "datetime" if x_col in profile.date_cols else "categorical",
            "y_type": "numeric",
            "x_label": humanize_field_name(x_col) if x_col else None,
            "y_label": humanize_field_name(y_col) if y_col else None,
        }

    # Default: bar (x=categorical, y=numeric)
    x_col = find_column(requested_x, "categorical", df)
    y_col = find_column(requested_y, "numeric", df)
    if x_col == y_col:
        if profile.categorical_cols:
            x_col = profile.categorical_cols[0]
        if profile.numeric_cols:
            y_col = profile.numeric_cols[0]
    return {
        "x_col": x_col,
        "y_col": y_col,
        "x_type": "categorical",
        "y_type": "numeric",
        "x_label": humanize_field_name(x_col) if x_col else None,
        "y_label": humanize_field_name(y_col) if y_col else None,
    }


# ====================================================================== #
# CHART PLANNER
# ====================================================================== #

class ChartPlan:
    """A single planned chart."""
    def __init__(self, chart_type: str, title: str, purpose: str,
                 x_col: str | None, y_col: str | None,
                 group_col: str | None = None, priority: int = 5):
        self.chart_type = chart_type
        self.title = title
        self.purpose = purpose
        self.x_col = x_col
        self.y_col = y_col
        self.group_col = group_col
        self.priority = priority  # 1 = highest


def create_visualization_plan(
    profile: DataProfile,
    user_question: str,
    llm_recommendations: list[dict] | None = None,
) -> list[ChartPlan]:
    """Create a structured visualization plan based on data characteristics and user intent.

    Returns a list of ChartPlans sorted by priority.
    """
    plans: list[ChartPlan] = []
    q_lower = user_question.lower()

    has_time = bool(profile.date_cols)
    has_numeric = bool(profile.numeric_cols)
    has_categorical = bool(profile.categorical_cols)

    # ------------------------------------------------------------ #
    # 1. LLM-recommended charts (if any) — highest priority
    # ------------------------------------------------------------ #
    if llm_recommendations:
        for i, rec in enumerate(llm_recommendations):
            plans.append(ChartPlan(
                chart_type=rec.get("chart_type", "bar"),
                title=rec.get("title", f"Chart {i+1}"),
                purpose=rec.get("rationale", "LLM-recommended visualization"),
                x_col=rec.get("x_axis_column"),
                y_col=rec.get("y_axis_column"),
                group_col=rec.get("group_by_column"),
                priority=1,
            ))

    # ------------------------------------------------------------ #
    # 2. Time-series charts
    # ------------------------------------------------------------ #
    if has_time and has_numeric:
        date_col = profile.date_cols[0]
        for num_col in profile.numeric_cols[:4]:
            plans.append(ChartPlan(
                chart_type="line",
                title=f"{humanize_field_name(num_col)} Over Time",
                purpose=f"Show the trend of {humanize_field_name(num_col)} over {humanize_field_name(date_col)}",
                x_col=date_col,
                y_col=num_col,
                priority=2,
            ))

    # ------------------------------------------------------------ #
    # 3. Category comparison (bar chart)
    # ------------------------------------------------------------ #
    if has_categorical and has_numeric:
        cat_col = profile.categorical_cols[0]
        num_col = profile.numeric_cols[0]
        unique = profile.unique_counts.get(cat_col, 0)

        if unique <= 30:
            plans.append(ChartPlan(
                chart_type="bar",
                title=f"{humanize_field_name(num_col)} by {humanize_field_name(cat_col)}",
                purpose=f"Compare {humanize_field_name(num_col)} across {humanize_field_name(cat_col)} categories",
                x_col=cat_col,
                y_col=num_col,
                priority=2,
            ))

        # Top-N if many categories
        if unique > 5:
            plans.append(ChartPlan(
                chart_type="horizontal_bar",
                title=f"Top {min(10, unique)} {humanize_field_name(cat_col)} by {humanize_field_name(num_col)}",
                purpose=f"Identify the highest-performing {humanize_field_name(cat_col)} categories",
                x_col=num_col,
                y_col=cat_col,
                priority=3,
            ))

    # ------------------------------------------------------------ #
    # 4. Proportion/composition (pie chart)
    # ------------------------------------------------------------ #
    if has_categorical and has_numeric:
        cat_col = profile.categorical_cols[0]
        num_col = profile.numeric_cols[0]
        unique = profile.unique_counts.get(cat_col, 0)
        if 2 <= unique <= 10:
            plans.append(ChartPlan(
                chart_type="pie",
                title=f"{humanize_field_name(num_col)} Distribution by {humanize_field_name(cat_col)}",
                purpose=f"Show the proportion of {humanize_field_name(num_col)} across {humanize_field_name(cat_col)}",
                x_col=cat_col,
                y_col=num_col,
                priority=4,
            ))

    # ------------------------------------------------------------ #
    # 5. Second categorical dimension
    # ------------------------------------------------------------ #
    if len(profile.categorical_cols) >= 2 and has_numeric:
        cat2 = profile.categorical_cols[1]
        num_col = profile.numeric_cols[0]
        unique2 = profile.unique_counts.get(cat2, 0)
        if unique2 <= 20:
            plans.append(ChartPlan(
                chart_type="bar",
                title=f"{humanize_field_name(num_col)} by {humanize_field_name(cat2)}",
                purpose=f"Compare {humanize_field_name(num_col)} across the secondary dimension {humanize_field_name(cat2)}",
                x_col=cat2,
                y_col=num_col,
                priority=4,
            ))

    # ------------------------------------------------------------ #
    # 6. Scatter plot (two numeric columns)
    # ------------------------------------------------------------ #
    if len(profile.numeric_cols) >= 2:
        n1, n2 = profile.numeric_cols[0], profile.numeric_cols[1]
        plans.append(ChartPlan(
            chart_type="scatter",
            title=f"{humanize_field_name(n2)} vs {humanize_field_name(n1)}",
            purpose=f"Explore the relationship between {humanize_field_name(n1)} and {humanize_field_name(n2)}",
            x_col=n1,
            y_col=n2,
            priority=5,
        ))

    # ------------------------------------------------------------ #
    # 7. Distribution histogram (REMOVED)
    # ------------------------------------------------------------ #
    # User requested to remove histograms from the auto-generated dashboard.

    # ------------------------------------------------------------ #
    # 8. Keyword-based priority boosts
    # ------------------------------------------------------------ #
    trend_keywords = ("trend", "over time", "growth", "change", "monthly", "weekly", "daily", "yearly")
    top_keywords = ("top", "best", "worst", "highest", "lowest", "ranking", "rank")

    if any(kw in q_lower for kw in trend_keywords) and has_time and has_numeric:
        for p in plans:
            if p.chart_type == "line":
                p.priority = 1

    if any(kw in q_lower for kw in top_keywords) and has_categorical and has_numeric:
        for p in plans:
            if p.chart_type == "horizontal_bar":
                p.priority = 1

    # ------------------------------------------------------------ #
    # Deduplicate and sort by priority
    # ------------------------------------------------------------ #
    seen_titles = set()
    unique_plans = []
    for p in sorted(plans, key=lambda x: x.priority):
        key = (p.chart_type, p.x_col, p.y_col)
        if key not in seen_titles:
            seen_titles.add(key)
            unique_plans.append(p)

    # Limit to 8 charts max
    result = unique_plans[:8]

    logger.info("[VIZ PLAN] Created %d chart plans:", len(result))
    for i, p in enumerate(result):
        logger.info(
            "  [%d] %s | %s | x=%s y=%s | %s",
            i + 1, p.chart_type, p.title, p.x_col, p.y_col, p.purpose,
        )

    return result


# ====================================================================== #
# VISUALIZATION SERVICE
# ====================================================================== #

class VisualizationService:
    """Generate complete multi-chart dashboards from structured data."""

    # ------------------------------------------------------------------ #
    # PRIMARY API: generate_dashboard
    # ------------------------------------------------------------------ #

    def generate_dashboard(
        self,
        request_id: str,
        data: list[dict[str, Any]],
        user_question: str,
        title: str = "Analytics Dashboard",
        llm_chart_recommendations: list[dict] | None = None,
        analysis_summary: str | None = None,
    ) -> VisualizationResponse:
        """Generate a complete multi-chart dashboard from retrieved data.

        This is the PRIMARY entry point. It:
        1. Normalizes the data
        2. Profiles columns/types with field type classification
        3. Creates a visualization plan
        4. Generates each chart with correct axis semantics
        5. Validates each chart before including it
        6. Builds KPI cards from canonical metrics
        7. Returns a single unified DashboardConfig
        """

        logger.info(
            "[VIZ] generate_dashboard() called — request_id=%s, rows=%d, question='%s'",
            request_id, len(data), user_question[:80],
        )

        if not data:
            msg = "Visualization Agent received no data — cannot generate dashboard"
            logger.error("[VIZ] %s", msg)
            return self._error_response(request_id, msg)

        try:
            # 1. Normalize data
            df = normalize_visualization_data(data)
            if df.empty:
                return self._error_response(request_id, "Data could not be normalized into a DataFrame")

            # 2. Profile the data (includes field type classification)
            profile = DataProfile(df)
            profile.log_profile()

            if profile.row_count == 0:
                return self._error_response(request_id, "Dataset has 0 rows")

            # 3. Compute canonical metrics (single source of truth)
            canonical = build_canonical_metrics(df, profile)
            logger.info(
                "[VIZ] Canonical metrics: records=%d, numeric_summaries=%s",
                canonical.record_count, list(canonical.numeric_summaries.keys()),
            )

            # 4. Create visualization plan
            plan = create_visualization_plan(
                profile=profile,
                user_question=user_question,
                llm_recommendations=llm_chart_recommendations,
            )

            if not plan:
                logger.warning("[VIZ] No charts planned — dataset may be unsuitable for visualization")
                plan = []

            # 5. Generate each chart independently with correct axis semantics
            charts: list[ChartConfig] = []
            png_paths: list[str] = []
            failed_count = 0

            for i, chart_plan in enumerate(plan):
                logger.info(
                    "[VIZ] Generating chart %d/%d: %s — %s",
                    i + 1, len(plan), chart_plan.chart_type, chart_plan.title,
                )

                chart_config = self._generate_single_chart(
                    df=df,
                    profile=profile,
                    plan=chart_plan,
                    data=data,
                    request_id=request_id,
                    chart_index=i,
                )

                if chart_config.success:
                    charts.append(chart_config)
                    logger.info("[VIZ] Chart %d/%d generated successfully", i + 1, len(plan))

                    # Generate PNG for Word report
                    png_path = self._generate_png_from_plan(
                        df, chart_plan, profile, request_id, i,
                    )
                    if png_path:
                        png_paths.append(str(png_path))
                        chart_config.image_path = str(png_path)
                else:
                    failed_count += 1
                    logger.warning(
                        "[VIZ] Chart %d/%d FAILED: %s",
                        i + 1, len(plan), chart_config.error_message,
                    )
                    charts.append(chart_config)

            # 6. Build KPI cards from canonical metrics
            kpis = self._build_kpis_from_canonical(canonical, profile)

            # 7. Determine filter columns
            filter_cols = [
                c for c in profile.categorical_cols
                if 2 <= profile.unique_counts.get(c, 0) <= 20
            ]

            # 8. Build unified dashboard
            successful_charts = [c for c in charts if c.success]

            dashboard = DashboardConfig(
                title=title,
                description=(
                    f"Dashboard generated from {profile.row_count} records "
                    f"across {profile.col_count} columns"
                ),
                kpis=kpis,
                charts=successful_charts,
                data_table=data[:100],
                columns=profile.columns,
                filter_columns=filter_cols,
                user_question=user_question,
                total_planned=len(plan),
                total_generated=len(successful_charts),
                total_failed=failed_count,
                canonical_metrics=canonical,
            )

            logger.info(
                "[VIZ] Dashboard complete — KPIs=%d, charts=%d/%d (failed=%d), filters=%d",
                len(kpis), len(successful_charts), len(plan), failed_count, len(filter_cols),
            )

            return VisualizationResponse(
                request_id=request_id,
                success=len(successful_charts) > 0 or len(kpis) > 0,
                chart_path=png_paths[0] if png_paths else None,
                dashboard=dashboard,
                error=None,
            )

        except Exception as exc:
            logger.exception("[VIZ] generate_dashboard() FAILED: %s", exc)
            plt.close("all")
            return self._error_response(request_id, str(exc))

    # ------------------------------------------------------------------ #
    # LEGACY API: generate (single chart) — kept for backward compat
    # ------------------------------------------------------------------ #

    def generate(self, request: VisualizationRequest) -> VisualizationResponse:
        """Generate a single chart. Delegates to generate_dashboard for consistency."""
        return self.generate_dashboard(
            request_id=request.request_id,
            data=request.data,
            user_question=request.title,
            title=request.title,
            llm_chart_recommendations=[{
                "chart_type": request.chart_type,
                "title": request.title,
                "x_axis_column": request.x_axis_column,
                "y_axis_column": request.y_axis_column,
                "group_by_column": request.group_by_column,
                "rationale": "User-specified chart",
            }],
        )

    # ------------------------------------------------------------------ #
    # SINGLE CHART GENERATION — with semantic axis resolution
    # ------------------------------------------------------------------ #

    def _generate_single_chart(
        self,
        df: pd.DataFrame,
        profile: DataProfile,
        plan: ChartPlan,
        data: list[dict[str, Any]],
        request_id: str,
        chart_index: int,
    ) -> ChartConfig:
        """Generate a single chart config with semantically correct axis mapping."""

        try:
            # Resolve chart type
            chart_type = self._resolve_chart_type(df, plan.chart_type, plan.x_col, plan.y_col)

            # Resolve axes SEMANTICALLY based on chart type
            axes = resolve_axes_for_chart_type(
                chart_type=chart_type,
                profile=profile,
                requested_x=plan.x_col,
                requested_y=plan.y_col,
                df=df,
            )

            x_col = axes["x_col"]
            y_col = axes["y_col"]
            x_type = axes["x_type"]
            y_type = axes["y_type"]
            x_label = axes["x_label"]
            y_label = axes["y_label"]
            group_col = plan.group_col if plan.group_col and plan.group_col in df.columns else None

            # Validate axis assignments
            if chart_type in ("bar", "horizontal_bar", "line") and not y_col:
                if profile.numeric_cols:
                    y_col = profile.numeric_cols[0]
                    y_label = humanize_field_name(y_col)
                else:
                    return ChartConfig(
                        chart_type=chart_type, title=plan.title,
                        purpose=plan.purpose, success=False,
                        error_message=f"No numeric column available for {chart_type} chart",
                    )

            if chart_type == "scatter" and len(profile.numeric_cols) < 2:
                return ChartConfig(
                    chart_type=chart_type, title=plan.title,
                    purpose=plan.purpose, success=False,
                    error_message="Need at least 2 numeric columns for scatter plot",
                )

            # Prepare chart data with sorting for horizontal_bar
            chart_data = data
            if chart_type == "horizontal_bar" and x_col and y_col:
                # Sort descending by numeric value, take top 10
                sort_col = x_col  # x is numeric for horizontal_bar
                sorted_df = df.sort_values(by=sort_col, ascending=False).head(10)
                chart_data = sorted_df.to_dict("records")

            # Humanize the title
            title = self._humanize_title(plan.title)

            # Generate insight from data
            insight = self._generate_insight(df, chart_type, x_col, y_col, title)

            return ChartConfig(
                chart_type=chart_type,
                title=title,
                description=plan.purpose,
                purpose=plan.purpose,
                insight=insight,
                x_column=x_col,
                y_column=y_col,
                group_column=group_col,
                x_axis_type=x_type,
                y_axis_type=y_type,
                x_axis_label=x_label,
                y_axis_label=y_label,
                data=chart_data,
                success=True,
            )

        except Exception as exc:
            logger.warning("[VIZ] Chart generation failed for '%s': %s", plan.title, exc)
            return ChartConfig(
                chart_type=plan.chart_type,
                title=plan.title,
                purpose=plan.purpose,
                success=False,
                error_message=str(exc),
            )

    # ------------------------------------------------------------------ #
    # TITLE HUMANIZATION
    # ------------------------------------------------------------------ #

    @staticmethod
    def _humanize_title(title: str) -> str:
        """Humanize a chart title: capitalize, remove underscores, fix plurals."""
        result = title
        # Replace underscored field names within the title
        parts = result.split()
        humanized_parts = []
        for part in parts:
            if "_" in part:
                humanized_parts.append(humanize_field_name(part))
            else:
                humanized_parts.append(part)
        return " ".join(humanized_parts)

    # ------------------------------------------------------------------ #
    # INSIGHT GENERATION
    # ------------------------------------------------------------------ #

    @staticmethod
    def _generate_insight(
        df: pd.DataFrame,
        chart_type: str,
        x_col: str | None,
        y_col: str | None,
        title: str,
    ) -> str:
        """Generate a data-driven insight for a chart.

        RULES:
        - NEVER compute Total/Avg on identifier columns
        - The category referenced in 'Highest: X' MUST match the chart's
          actual dimension column, not a random column from the df
        """
        try:
            # Determine which column is the value (measure) and which is the category
            value_col = None
            category_col = None

            if chart_type == "histogram":
                value_col = x_col
            elif chart_type in ("horizontal_bar",):
                value_col = x_col  # horizontal_bar: x is numeric
                category_col = y_col
            else:
                value_col = y_col
                category_col = x_col

            if not value_col or value_col not in df.columns:
                return ""

            # HARD RULE: skip if value_col is an identifier
            if _is_identifier_by_name(value_col):
                logger.info("[INSIGHT] Skipping insight for identifier column '%s'", value_col)
                return ""

            series = df[value_col]
            if not pd.api.types.is_numeric_dtype(series):
                return ""

            total = series.sum()
            avg = series.mean()
            max_val = series.max()
            min_val = series.min()
            label = normalize_metric_label("sum", value_col)
            avg_label = normalize_metric_label("avg", value_col)

            if category_col and category_col in df.columns:
                # VALIDATION: category_col must NOT be an identifier either
                if _is_identifier_by_name(category_col):
                    # Fall back to aggregate-only insight without category names
                    return f"{label}: {total:,.2f}. {avg_label}: {avg:,.2f}. Range: {min_val:,.2f} to {max_val:,.2f}."

                max_idx = series.idxmax()
                min_idx = series.idxmin()
                max_cat = str(df.loc[max_idx, category_col]) if max_idx is not None else "N/A"
                min_cat = str(df.loc[min_idx, category_col]) if min_idx is not None else "N/A"
                cat_label = humanize_field_name(category_col)

                insight = (
                    f"{label}: {total:,.2f}. "
                    f"Highest {cat_label}: {max_cat} ({max_val:,.2f}). "
                    f"Lowest {cat_label}: {min_cat} ({min_val:,.2f}). "
                    f"{avg_label}: {avg:,.2f}."
                )
            else:
                insight = f"{label}: {total:,.2f}. {avg_label}: {avg:,.2f}. Range: {min_val:,.2f} to {max_val:,.2f}."

            return insight

        except Exception:
            return ""

    # ------------------------------------------------------------------ #
    # CHART TYPE RESOLUTION
    # ------------------------------------------------------------------ #

    def _resolve_chart_type(self, df, requested, x_col, y_col):
        supported = {"bar", "line", "pie", "scatter", "histogram", "horizontal_bar"}
        aliases = {
            "bar_chart": "bar", "barchart": "bar", "bar chart": "bar",
            "line_chart": "line", "linechart": "line", "line chart": "line",
            "pie_chart": "pie", "piechart": "pie", "pie chart": "pie",
            "scatter_plot": "scatter", "scatterplot": "scatter",
            "donut": "pie", "donut_chart": "pie",
            "hist": "histogram", "distribution": "histogram",
            "horizontal_bar": "horizontal_bar", "hbar": "horizontal_bar",
        }
        cleaned = requested.lower().strip()
        resolved = aliases.get(cleaned, cleaned)
        return resolved if resolved in supported else self._auto_detect_chart_type(df, x_col, y_col)

    def _auto_detect_chart_type(self, df, x_col, y_col):
        profile = DataProfile(df)
        if profile.date_cols:
            return "line"
        if profile.categorical_cols and profile.numeric_cols:
            return "bar"
        if len(profile.numeric_cols) >= 2:
            return "scatter"
        return "bar"

    # ------------------------------------------------------------------ #
    # KPI GENERATION — from canonical metrics
    # ------------------------------------------------------------------ #

    def _build_kpis_from_canonical(self, canonical: CanonicalMetrics, profile: DataProfile) -> list[KPICard]:
        """Build KPI cards using canonical metrics (single source of truth).

        RULES:
        - IDENTIFIER columns → show COUNT DISTINCT (e.g. "Customers: 2,001")
        - NUMERIC_MEASURE columns → show Total and Average
        - NEVER show "Total Customer Id" or "Avg Customer Id"
        """
        kpis = []

        kpis.append(KPICard(label="Total Records", value=f"{canonical.record_count:,}"))

        # ---- Entity counts from identifier columns ----
        for col, summary in canonical.numeric_summaries.items():
            if summary.get("semantic_type") == SEMANTIC_IDENTIFIER:
                count_distinct = summary.get("count_distinct", 0)
                entity_label = summary.get("display_label", _entity_display_name(col))
                kpis.append(KPICard(label=f"Total {entity_label}", value=f"{count_distinct:,}"))

        # ---- Measure summaries ----
        measure_count = 0
        for col, summary in canonical.numeric_summaries.items():
            if summary.get("semantic_type") != SEMANTIC_MEASURE:
                continue
            if measure_count >= 3:
                break
            measure_count += 1

            total = summary.get("total", 0)
            avg = summary.get("average", 0)
            label = summary.get("display_label", humanize_field_name(col))

            # Format total with K/M suffix
            if abs(total) >= 1_000_000:
                formatted = f"{total / 1_000_000:,.1f}M"
            elif abs(total) >= 1_000:
                formatted = f"{total / 1_000:,.1f}K"
            else:
                formatted = f"{total:,.2f}"

            total_label = normalize_metric_label("sum", col)
            avg_label = normalize_metric_label("avg", col)

            kpis.append(KPICard(label=total_label, value=formatted))
            kpis.append(KPICard(label=avg_label, value=f"{avg:,.2f}"))

        # Top category KPI from canonical data (measures only)
        for col, cat_info in list(canonical.top_categories.items())[:1]:
            cat_field = cat_info.get("category_field", col)
            label = humanize_field_name(cat_field)
            kpis.append(KPICard(label=f"Top {label}", value=str(cat_info.get("top", ""))))

        return kpis[:8]

    # ------------------------------------------------------------------ #
    # PNG GENERATION (for Word reports) — with correct axis semantics
    # ------------------------------------------------------------------ #

    def _generate_png_from_plan(
        self, df: pd.DataFrame, plan: ChartPlan,
        profile: DataProfile,
        request_id: str, index: int,
    ) -> Path | None:
        try:
            output_dir = Path("outputs/charts")
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = output_dir / f"{request_id}_chart_{index}.png"

            # Resolve axes semantically
            chart_type = self._resolve_chart_type(df, plan.chart_type, plan.x_col, plan.y_col)
            axes = resolve_axes_for_chart_type(chart_type, profile, plan.x_col, plan.y_col, df)
            x_col = axes["x_col"]
            y_col = axes["y_col"]
            x_label = axes["x_label"] or ""
            y_label = axes["y_label"] or ""

            fig, ax = plt.subplots(figsize=(10, 6))
            fig.patch.set_facecolor("#0d1117")
            ax.set_facecolor("#161b22")
            ax.tick_params(colors="#c9d1d9")
            ax.xaxis.label.set_color("#c9d1d9")
            ax.yaxis.label.set_color("#c9d1d9")
            ax.title.set_color("#c9d1d9")
            for spine in ax.spines.values():
                spine.set_color("#30363d")

            colors = ["#58a6ff", "#bd56eb", "#2ea043", "#f0883e", "#da3633",
                      "#388bfd", "#a371f7", "#3fb950", "#d29922", "#f85149"]

            if chart_type == "bar" and x_col and y_col:
                plot_df = df.head(20)
                ax.bar(plot_df[x_col].astype(str), plot_df[y_col], color="#58a6ff")
                ax.set_xlabel(x_label)
                ax.set_ylabel(y_label)
                plt.xticks(rotation=45, ha="right")

            elif chart_type == "horizontal_bar" and x_col and y_col:
                # x=numeric, y=categorical. Sort descending, top value at top.
                sorted_df = df.sort_values(by=x_col, ascending=True).tail(10)
                ax.barh(sorted_df[y_col].astype(str), sorted_df[x_col], color="#58a6ff")
                ax.set_xlabel(x_label)
                ax.set_ylabel(y_label)

            elif chart_type == "line" and x_col and y_col:
                ax.plot(df[x_col].astype(str), df[y_col], marker="o", color="#58a6ff", linewidth=2)
                ax.set_xlabel(x_label)
                ax.set_ylabel(y_label)
                plt.xticks(rotation=45, ha="right")

            elif chart_type == "pie" and x_col and y_col:
                plot_df = df.head(10)
                ax.pie(plot_df[y_col].abs(), labels=plot_df[x_col].astype(str),
                       autopct="%1.1f%%", colors=colors[:len(plot_df)],
                       textprops={"color": "#c9d1d9"})

            elif chart_type == "scatter" and x_col and y_col:
                ax.scatter(df[x_col], df[y_col], color="#58a6ff", alpha=0.7)
                ax.set_xlabel(x_label)
                ax.set_ylabel(y_label)

            elif chart_type == "histogram" and x_col:
                ax.hist(df[x_col], bins=min(20, len(df)), color="#58a6ff", edgecolor="#0d1117")
                ax.set_xlabel(x_label)
                ax.set_ylabel("Frequency")

            title = self._humanize_title(plan.title)
            ax.set_title(title, fontsize=14, fontweight="bold")
            fig.savefig(output_path, format="png", dpi=150, bbox_inches="tight")
            plt.close(fig)
            return output_path

        except Exception as exc:
            logger.warning("[VIZ] PNG generation failed for '%s': %s", plan.title, exc)
            plt.close("all")
            return None

    # ------------------------------------------------------------------ #
    # ERROR RESPONSE
    # ------------------------------------------------------------------ #

    def _error_response(self, request_id: str, message: str) -> VisualizationResponse:
        logger.error("[VIZ] Error: %s", message)
        return VisualizationResponse(
            request_id=request_id,
            success=False,
            error=ErrorInfo(code="VISUALIZATION_ERROR", message=message),
        )