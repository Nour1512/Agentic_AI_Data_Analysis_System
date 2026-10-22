from __future__ import annotations

import logging
from typing import Any

from agents.orchestrator.orchestrator import (
    OrchestratorAgent,
)
from agents.sql_agent_python_only import SQLAgentFromScratch
from agents.analysis_agent import AnalysisAgent
from agents.report_agent import ReportAgent
from agents_schema import state
from services.visualization_service import (
    VisualizationService,
)

from agents_schema.common import DataRow
from agents_schema.state import AnalysisState
from agents_schema.orchestrator import UserRequest
from agents_schema.analysis import AnalysisRequest
from agents_schema.visualization import VisualizationRequest
from agents_schema.report import ReportRequest


logger = logging.getLogger(__name__)


class OrchestratorWorkflow:
    """
    Controls the complete Agentic AI Data Analysis workflow.

    Workflow:

        UserRequest
            |
            v
        Orchestrator Agent
            |
            v
        TaskSpec
            |
            v
        SQL Agent
            |
            |-- creates DataRequest
            |-- generates SQL
            |-- executes SQL
            |
            v
        DataResponse
            |
            v
        Analysis Agent
            |
            v
        AnalysisResponse
            |
            +----------------------+
            |                      |
            v                      v
        Visualization          Report
          Service               Agent
            |                      |
            v                      v
        Visualization          ReportResponse
         Response                  |
            |                      |
            +----------+-----------+
                       |
                       v
                 Final Response

    Every user request in this system is a data-analysis request,
    therefore the SQL Agent is always part of the workflow.
    """

    def __init__(
        self,
        orchestrator_agent: OrchestratorAgent,
        sql_agent: SQLAgentFromScratch,
        analysis_agent: AnalysisAgent,
        visualization_service: VisualizationService,
        report_agent: ReportAgent,
    ) -> None:
        """
        Initialize the workflow with the required agents/services.
        """

        self.orchestrator_agent = orchestrator_agent
        self.sql_agent = sql_agent
        self.analysis_agent = analysis_agent
        self.visualization_service = visualization_service
        self.report_agent = report_agent

    # MAIN WORKFLOW
    def run(
        self,
        user_request: UserRequest,
    ) -> AnalysisState:
        """
        Execute the complete data-analysis workflow.

        Parameters
        ----------
        user_request:
            The request submitted by the user.

        Returns
        -------
        AnalysisState
            The final state containing all results generated
            throughout the workflow.
        """

        self._validate_user_request(user_request)

        # -----------------------------------------------------
        # INITIAL STATE
        # -----------------------------------------------------

        state = AnalysisState(
            user_request=user_request
        )

        logger.info(
            "Starting workflow for request_id=%s",
            user_request.request_id,
        )

        try:

            # STEP 1: ORCHESTRATOR

            logger.info(
                "Running Orchestrator Agent for request_id=%s",
                user_request.request_id,
            )

            orchestrator_response = self.orchestrator_agent.run(
                user_question=user_request.question,
                requested_formats=getattr(user_request, "requested_formats", None),
                context=getattr(user_request, "context", None),
            )

            if orchestrator_response is None:
                raise ValueError("Orchestrator agent failed to generate a TaskSpec.")

            task_spec = orchestrator_response
            state.task_spec = task_spec

            logger.info(
                "TaskSpec created successfully for request_id=%s",
                user_request.request_id,
            )


            # STEP 2: SQL AGENT

            logger.info(
                "Running SQL Agent for request_id=%s",
                user_request.request_id,
            )

            # TaskSpec -> DataRequest -> SQL generation -> Validation -> Execution -> DataResponse
            state.data_response = self.sql_agent.run(task_spec, request_id=user_request.request_id)

            logger.info(
                "SQL Agent completed for request_id=%s",
                user_request.request_id,
            )

            logger.debug("DataResponse payload sending to AnalysisAgent: %s", state.data_response.model_dump())

            # STEP 3: ANALYSIS AGENT

            logger.info(
                "Running Analysis Agent for request_id=%s",
                user_request.request_id,
            )

            analysis_request = self._create_analysis_request(
                state
            )

            state.analysis_response = self.analysis_agent.run(
                analysis_request=analysis_request
            )

            logger.info(
                "Analysis Agent completed for request_id=%s",
                user_request.request_id,
            )

            # STEP 4: VISUALIZATION ROUTING

            if self._visualization_required(state):

                logger.info(
                    "Visualization required for request_id=%s",
                    user_request.request_id,
                )

                visualization_request = (
                    self._create_visualization_request(state)
                )

                state.visualization_response = (
                    self.visualization_service.generate(
                        visualization_request
                    )
                )

                logger.info(
                    "Visualization completed for request_id=%s",
                    user_request.request_id,
                )

            else:

                logger.info(
                    "Visualization not required for request_id=%s",
                    user_request.request_id,
                )

            # STEP 5: REPORT ROUTING

            if self._report_required(state):

                logger.info(
                    "Report required for request_id=%s",
                    user_request.request_id,
                )

                report_request = self._create_report_request(
                    state
                )

                state.report_response = self.report_agent.run(
                    report_request=report_request
                )

                logger.info(
                    "Report generation completed for request_id=%s",
                    user_request.request_id,
                )

            else:

                logger.info(
                    "Report not required for request_id=%s",
                    user_request.request_id,
                )


            # STEP 6: FINAL RESPONSE

            state.final_response = self._build_final_response(
                state
            )

            logger.info(
                "Workflow completed successfully for "
                "request_id=%s",
                user_request.request_id,
            )

            return state

        except Exception as exc:

            logger.exception(
                "Workflow failed for request_id=%s",
                user_request.request_id,
            )

            # Store the error in final_response so the caller
            # can inspect the failed workflow state.
            state.final_response = {
                "success": False,
                "request_id": user_request.request_id,
                "error": str(exc),
            }

            return state

    # ANALYSIS REQUEST

    def _create_analysis_request(
        self,
        state: AnalysisState,
    ) -> AnalysisRequest:
        if state.task_spec is None:
            raise RuntimeError("Cannot create AnalysisRequest without TaskSpec.")

        if state.data_response is None:
            raise RuntimeError("Cannot create AnalysisRequest without DataResponse.")

        original_question = (
            getattr(state.task_spec, "original_question", None)
            or getattr(state.task_spec, "question", None)
            or state.user_request.question
        )

        formatted_results = []
        for r in state.data_response.results:
            # Case 1: Already a DataRow object
            if isinstance(r, DataRow):
                formatted_results.append(r)
            # Case 2: Dictionary already containing a "values" wrapper
            elif isinstance(r, dict) and "values" in r and isinstance(r["values"], dict):
                formatted_results.append(DataRow(values=r["values"]))
            # Case 3: Flat dictionary (e.g. {"product_name": "Ultra Laptop Pro", ...})
            elif isinstance(r, dict):
                formatted_results.append(DataRow(values=r))
            # Case 4: Fallback object with model_dump or attributes
            elif hasattr(r, "values"):
                formatted_results.append(
                    DataRow(values=r.values) if isinstance(r.values, dict) else DataRow(values={"result": str(r.values)})
                )
            elif hasattr(r, "model_dump"):
                dump = r.model_dump()
                val = dump.get("values", dump)
                formatted_results.append(DataRow(values=val if isinstance(val, dict) else {"result": str(val)}))
            else:
                formatted_results.append(DataRow(values={"result": str(r)}))

        return AnalysisRequest(
            request_id=state.user_request.request_id,
            original_question=original_question,
            data_columns=state.data_response.columns,
            data_results=formatted_results,
            analysis_goals=state.task_spec.analysis_goals,
            requested_formats=state.task_spec.requested_formats,
            data_warnings=state.data_response.warnings,
        )

    # VISUALIZATION ROUTING

    def _visualization_required(
        self,
        state: AnalysisState,
    ) -> bool:
        """
        Determine whether the Visualization Service should
        be executed.
        """

        if state.task_spec is None:
            return False

        if state.task_spec.visualization_required:
            return True

        if (
            state.analysis_response is not None
            and state.analysis_response.chart_recommendations
            is not None
            and len(state.analysis_response.chart_recommendations) > 0
        ):
            return True

        return False

    # CREATE VISUALIZATION REQUEST

    def _create_visualization_request(
        self,
        state: AnalysisState,
    ) -> VisualizationRequest:
        if state.task_spec is None:
            raise RuntimeError("Cannot create VisualizationRequest without TaskSpec.")

        if state.data_response is None:
            raise RuntimeError("Cannot create VisualizationRequest without DataResponse.")

        # Safely read attributes with default values if they are missing on TaskSpec
        chart_type = getattr(state.task_spec, "chart_type", None) or "bar"
        title = getattr(state.task_spec, "chart_title", None) or "Data Visualization"
        x_column = getattr(state.task_spec, "x_column", None)
        y_column = getattr(state.task_spec, "y_column", None)

        data = []
        for r in state.data_response.results:
            if isinstance(r, DataRow):
                data.append(r.values)
            elif hasattr(r, "values"):
                data.append(r.values if isinstance(r.values, dict) else {"result": str(r.values)})
            elif isinstance(r, dict):
                val = r.get("values", r)
                data.append(val if isinstance(val, dict) else r)
            elif hasattr(r, "model_dump"):
                dump = r.model_dump()
                val = dump.get("values", dump)
                data.append(val if isinstance(val, dict) else {"result": str(val)})
            else:
                data.append({"result": str(r)})

        # Fallback: if the TaskSpec didn't specify x/y columns, use the
        # first two actual columns returned by the SQL Agent instead of
        # leaving them as None (which crashes chart generation later).
        if x_column is None or y_column is None:
            result_columns = [
                getattr(c, "name", None) or (c.get("name") if isinstance(c, dict) else None)
                for c in (state.data_response.columns or [])
            ]
            result_columns = [c for c in result_columns if c]

            if x_column is None and len(result_columns) >= 1:
                x_column = result_columns[0]

            if y_column is None and len(result_columns) >= 2:
                y_column = result_columns[1]

        return VisualizationRequest(
            request_id=state.user_request.request_id,
            chart_type=chart_type,
            data=data,
            title=title,
            x_axis_column=x_column,
            y_axis_column=y_column,
        )

    # REPORT ROUTING

    def _report_required(
        self,
        state: AnalysisState,
    ) -> bool:
        """
        Determine whether the Report Agent should be executed.
        Forced to True to ensure reports are always generated per user request.
        """
        return True

    # CREATE REPORT REQUEST

    def _create_report_request(
            self,
            state: AnalysisState,
        ) -> ReportRequest:
            """
            Convert AnalysisResponse + workflow information into
            the ReportRequest expected by the Report Agent.
            """

            if state.task_spec is None:
                raise RuntimeError(
                    "Cannot create ReportRequest without TaskSpec."
                )

            if state.analysis_response is None:
                raise RuntimeError(
                    "Cannot create ReportRequest without "
                    "AnalysisResponse."
                )

            # Build ReportChart objects from the visualization response
            from agents_schema.report import ReportChart as _ReportChart

            report_charts = []
            if (
                state.visualization_response is not None
                and state.visualization_response.success
                and state.visualization_response.dashboard is not None
            ):
                for chart_cfg in state.visualization_response.dashboard.charts:
                    report_charts.append(
                        _ReportChart(
                            title=chart_cfg.title,
                            chart_type=chart_cfg.chart_type,
                            insight=chart_cfg.insight,
                            image_path=chart_cfg.image_path,
                        )
                    )
            elif (
                state.visualization_response is not None
                and state.visualization_response.success
                and state.visualization_response.chart_path
            ):
                # Legacy single-chart path
                report_charts.append(
                    _ReportChart(
                        title="Generated Chart",
                        chart_type="bar",
                        image_path=state.visualization_response.chart_path,
                    )
                )

            # Fallback chain to ensure original_question is never empty/None
            original_question = (
                getattr(state.task_spec, "original_question", None)
                or getattr(state.task_spec, "question", None)
                or state.user_request.question
            )

            return ReportRequest(
                request_id=state.user_request.request_id,

                title=(
                    f"Data Analysis Report - "
                    f"{getattr(state.task_spec, 'intent', 'Summary')}"
                ),

                original_question=original_question,

                summary=(
                    state.analysis_response.summary
                ),

                key_findings=[
                    f"{kf.title}: {kf.description}"
                    for kf in state.analysis_response.key_findings
                ],

                business_context=(
                    state.analysis_response.business_context
                ),

                recommendations=(
                    state.analysis_response.recommendations
                ),

                charts=report_charts,

                additional_context=(
                    getattr(state.task_spec, "additional_instructions", None)
                ),
            )

    # FINAL RESPONSE

    def _build_final_response(
        self,
        state: AnalysisState,
    ) -> dict[str, Any]:
        """
        Build a unified final response from the outputs
        generated by the workflow.
        """

        response: dict[str, Any] = {
            "success": True,

            "request_id": (
                state.user_request.request_id
            ),

            "question": (
                state.user_request.question
            ),
        }

        # ANALYSIS

        if state.analysis_response is not None:

            response["analysis"] = {
                "summary": (
                    state.analysis_response.summary
                ),

                "key_findings": (
                    state.analysis_response.key_findings
                ),

                "business_context": (
                    state.analysis_response.business_context
                ),

                "recommendations": (
                    state.analysis_response.recommendations
                ),

                "confidence": (
                    state.analysis_response.confidence_level
                ),
            }

        # VISUALIZATION

        if state.visualization_response is not None:

            response["visualization"] = {
                "success": (
                    state.visualization_response.success
                ),

                "chart_path": (
                    state.visualization_response.chart_path
                ),

                "chart_url": (
                    state.visualization_response.chart_url
                ),

                "error": (
                    state.visualization_response.error.message
                    if state.visualization_response.error
                    else None
                ),
            }

        # REPORT

        if state.report_response is not None:

            response["report"] = {
                "success": (
                    state.report_response.success
                ),

                "report_path": (
                    state.report_response.report_path
                ),

                "report_url": (
                    state.report_response.report_url
                ),

                "error": (
                    state.report_response.error.message
                    if state.report_response.error
                    else None
                ),
            }

        return response

    # VALIDATION

    @staticmethod
    def _validate_user_request(
        user_request: UserRequest,
    ) -> None:
        """
        Validate the incoming UserRequest before starting
        the workflow.
        """

        if not user_request.request_id:
            raise ValueError(
                "UserRequest.request_id cannot be empty."
            )

        if not user_request.question.strip():
            raise ValueError(
                "UserRequest.question cannot be empty."
            )