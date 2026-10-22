from typing import Any

from pydantic import BaseModel, Field

from .common import (
    ConfidenceLevel,
    ErrorInfo,
    OutputFormat,
    RequestStatus,
    WarningInfo,
)


class UserRequest(BaseModel):
    request_id: str
    question: str

    requested_formats: list[OutputFormat] = Field(
        default_factory=lambda: [OutputFormat.TEXT]
    )

    metadata: dict[str, Any] = Field(default_factory=dict)


class TaskSpec(BaseModel):
    request_id: str

    original_question: str

    intent: str

    requested_formats: list[OutputFormat]

    data_requirements: list[str]

    analysis_goals: list[str]

    report_required: bool = False

    visualization_required: bool = False

    additional_instructions: list[str] = Field(
        default_factory=list
    )


class OrchestratorResponse(BaseModel):
    request_id: str

    status: RequestStatus

    task_spec: TaskSpec | None = None

    confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM

    warnings: list[WarningInfo] = Field(
        default_factory=list
    )

    error: ErrorInfo | None = None