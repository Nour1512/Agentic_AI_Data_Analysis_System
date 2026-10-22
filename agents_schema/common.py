from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class RequestStatus(str, Enum):
    SUCCESS = "success"
    ERROR = "error"
    PARTIAL = "partial"


class OutputFormat(str, Enum):
    TEXT = "text"
    CHART = "chart"
    REPORT = "report"


class ValidationStatus(str, Enum):
    VALID = "valid"
    EMPTY_RESULT = "empty_result"
    VALID_WITH_WARNINGS = "valid_with_warnings"
    INVALID = "invalid"


class ConfidenceLevel(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class DataColumn(BaseModel):
    name: str
    data_type: str
    description: str | None = None


class DataRow(BaseModel):
    values: dict[str, Any]

    def __getitem__(self, item: str) -> Any:
        return self.values.get(item)

    def get(self, item: str, default: Any = None) -> Any:
        return self.values.get(item, default)

    def to_dict(self) -> dict[str, Any]:
        return self.values


class ErrorInfo(BaseModel):
    code: str
    message: str
    details: str | None = None


class WarningInfo(BaseModel):
    code: str
    message: str
    details: str | None = None