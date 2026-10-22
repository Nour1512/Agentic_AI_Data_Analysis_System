from typing import Any

from pydantic import BaseModel, Field

from .common import (
    DataColumn,
    DataRow,
    ErrorInfo,
    ValidationStatus,
    WarningInfo,
)


class DataRequest(BaseModel):
    request_id: str

    query_intent: str

    tables_required: list[str] = Field(
        default_factory=list
    )

    columns_required: list[str] = Field(
        default_factory=list
    )

    filters: dict[str, Any] = Field(
        default_factory=dict
    )

    aggregations: list[str] = Field(
        default_factory=list
    )

    group_by: list[str] = Field(
        default_factory=list
    )

    order_by: list[str] = Field(
        default_factory=list
    )

    limit: int | None = None

    expected_format: str = "tabular"




class DataResponse(BaseModel):
    request_id: str

    query_executed: str

    columns: list[DataColumn] = Field(
        default_factory=list
    )

    results: list[DataRow] = Field(
        default_factory=list
    )

    row_count: int

    validation_status: ValidationStatus

    warnings: list[WarningInfo] = Field(
        default_factory=list
    )

    error: ErrorInfo | None = None