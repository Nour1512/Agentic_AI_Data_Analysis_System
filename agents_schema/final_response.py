from pydantic import BaseModel, Field

from .common import (
    ErrorInfo,
    RequestStatus,
    WarningInfo,
)


class FinalResponse(BaseModel):
    request_id: str

    question: str

    status: RequestStatus

    text_insights: str | None = None

    chart_url: str | None = None

    report_url: str | None = None

    warnings: list[WarningInfo] = Field(
        default_factory=list
    )

    error: ErrorInfo | None = None