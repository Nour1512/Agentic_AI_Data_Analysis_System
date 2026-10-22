from pydantic import BaseModel

from .analysis import AnalysisResponse
from .common import OutputFormat
from .orchestrator import TaskSpec, UserRequest
from .sql import DataResponse
from .visualization import VisualizationResponse
from .report import ReportResponse


class AnalysisState(BaseModel):
    user_request: UserRequest

    task_spec: TaskSpec | None = None

    data_response: DataResponse | None = None

    analysis_response: AnalysisResponse | None = None

    visualization_response: VisualizationResponse | None = None

    report_response: ReportResponse | None = None

    final_response: object | None = None