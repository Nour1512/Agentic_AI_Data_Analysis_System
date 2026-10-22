import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from agents_schema.orchestrator import UserRequest
from services.groq_service import GroqService
from services.report_renderer import ReportRenderer
from database.sqlserver_client import SQLServerClient
from agents.sql_agent_python_only import SQLAgentFromScratch
from agents.analysis_agent import AnalysisAgent
from agents.report_agent import ReportAgent
from agents.orchestrator.orchestrator import OrchestratorAgent
from agents.orchestrator.orchestrator_workflow import OrchestratorWorkflow
from services.visualization_service import VisualizationService


# ---------------------------------------------------------------------------
# Logging (audit trail)
# ---------------------------------------------------------------------------
os.makedirs("logs", exist_ok=True)
os.makedirs("reports", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("logs/audit.log"),
    ],
)

logger = logging.getLogger("audit.api")


# ---------------------------------------------------------------------------
# Workflow wiring
# ---------------------------------------------------------------------------
def create_workflow() -> OrchestratorWorkflow:
    groq_service = GroqService()
    sql_server_client = SQLServerClient()

    orchestrator_agent = OrchestratorAgent(llm_client=groq_service)
    sql_agent = SQLAgentFromScratch(groq_service=groq_service, database_client=sql_server_client)
    analysis_agent = AnalysisAgent(llm_client=groq_service)
    report_agent = ReportAgent(llm_client=groq_service)

    return OrchestratorWorkflow(
        orchestrator_agent=orchestrator_agent,
        sql_agent=sql_agent,
        analysis_agent=analysis_agent,
        visualization_service=VisualizationService(),
        report_agent=report_agent,
    )


workflow: Optional[OrchestratorWorkflow] = None
workflow_init_error: Optional[str] = None

try:
    workflow = create_workflow()
    logger.info("Workflow initialized successfully at startup")
except Exception as exc:  # noqa: BLE001 - surfaced via /api/health
    workflow_init_error = str(exc)
    logger.exception("Workflow failed to initialize at startup")


# ---------------------------------------------------------------------------
# Report file path helper
# ---------------------------------------------------------------------------
REPORTS_DIR = Path("reports")


def get_report_path(request_id: str) -> Path:
    """Return the canonical .docx path for a given request_id."""
    return REPORTS_DIR / f"{request_id}.docx"


# ---------------------------------------------------------------------------
# In-memory result store
# ---------------------------------------------------------------------------
class QueryStatus(str, Enum):
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class QueryStore:
    """Thread-safe in-memory store for query status/results.

    Swap this out for Redis/a DB table if you need results to survive a
    restart or to be shared across multiple API worker processes.
    """

    def __init__(self):
        self._lock = Lock()
        self._data: Dict[str, Dict[str, Any]] = {}

    def create(self, query_id: str, question: str) -> None:
        with self._lock:
            self._data[query_id] = {
                "query_id": query_id,
                "question": question,
                "status": QueryStatus.PROCESSING,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "completed_at": None,
                "result": None,
                "error": None,
                "report_path": None,
                "report_html": None,
            }

    def complete(self, query_id: str, result: Dict[str, Any], report_path: Optional[str] = None, report_html: Optional[str] = None) -> None:
        with self._lock:
            if query_id not in self._data:
                return
            self._data[query_id].update(
                status=QueryStatus.COMPLETED,
                completed_at=datetime.now(timezone.utc).isoformat(),
                result=result,
                report_path=report_path,
                report_html=report_html,
            )

    def fail(self, query_id: str, error: str) -> None:
        with self._lock:
            if query_id not in self._data:
                return
            self._data[query_id].update(
                status=QueryStatus.FAILED,
                completed_at=datetime.now(timezone.utc).isoformat(),
                error=error,
            )

    def get(self, query_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            record = self._data.get(query_id)
            return dict(record) if record else None

    def all_completed(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [
                dict(v) for v in self._data.values()
                if v.get("status") in (QueryStatus.COMPLETED, QueryStatus.FAILED)
            ]

    def all(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [dict(v) for v in self._data.values()]


store = QueryStore()


# ---------------------------------------------------------------------------
# Workflow execution helper
# ---------------------------------------------------------------------------
def _execute_workflow(query_id: str, question: str) -> Dict[str, Any]:
    """
    Run the full OrchestratorWorkflow synchronously, then render the report
    to disk (if the Report Agent succeeded).

    Returns the final response dict to be stored and returned to the client.
    """
    logger.info("[%s] workflow execution started", query_id)

    request_payload = UserRequest(request_id=query_id, question=question)
    state = workflow.run(request_payload)

    final_response = getattr(state, "final_response", None)
    if not final_response:
        raise RuntimeError("Workflow completed but produced no final_response")

    # -------------------------------------------------------------------
    # Render the report to disk (.docx) + generate HTML preview
    # The ReportAgent produces a StructuredReport but does NOT write files.
    # We call ReportRenderer here so both formats are available.
    # -------------------------------------------------------------------
    report_path_str: Optional[str] = None
    report_html_str: Optional[str] = None
    report_errors: List[str] = []

    if (
        state.report_response is not None
        and state.report_response.success
        and state.report_response.structured_report is not None
    ):
        structured_report = state.report_response.structured_report
        docx_path = get_report_path(query_id)

        # HTML preview (always attempt)
        try:
            report_html_str = ReportRenderer.render_html(structured_report)
            logger.info("[%s] HTML report preview generated (%d chars)", query_id, len(report_html_str))
        except Exception as html_exc:
            logger.warning("[%s] HTML rendering failed: %s", query_id, html_exc)
            report_errors.append(f"HTML preview failed: {html_exc}")

        # DOCX file (attempt; failure is non-fatal)
        try:
            REPORTS_DIR.mkdir(parents=True, exist_ok=True)
            ReportRenderer.render_docx(structured_report, docx_path)
            report_path_str = str(docx_path)
            logger.info("[%s] DOCX report saved to %s", query_id, docx_path)
        except Exception as docx_exc:
            logger.warning("[%s] DOCX rendering failed: %s", query_id, docx_exc)
            report_errors.append(f"DOCX generation failed: {docx_exc}")
    elif state.report_response is not None and not state.report_response.success:
        err_detail = (
            state.report_response.error.message
            if state.report_response.error
            else "Unknown report error"
        )
        report_errors.append(f"Report Agent failed: {err_detail}")

    # -------------------------------------------------------------------
    # Augment the final_response with rendered paths + HTML
    # -------------------------------------------------------------------
    if isinstance(final_response, dict):
        # Patch the "report" sub-dict with actual on-disk values
        if "report" in final_response and isinstance(final_response["report"], dict):
            final_response["report"]["report_path"] = report_path_str
            final_response["report"]["report_html"] = report_html_str
            final_response["report"]["available"] = report_path_str is not None
            if report_path_str:
                final_response["report"]["download_url"] = f"/api/report/{query_id}/download"
        elif report_path_str:
            # Workflow said no report was needed, but we still have one
            final_response["report"] = {
                "success": True,
                "report_path": report_path_str,
                "report_html": report_html_str,
                "available": True,
                "download_url": f"/api/report/{query_id}/download",
            }

        if report_errors:
            existing_errors = final_response.get("errors") or []
            if isinstance(existing_errors, list):
                existing_errors.extend(report_errors)
            else:
                existing_errors = report_errors
            final_response["errors"] = existing_errors

        # Normalise insights to a flat list for the frontend
        if "analysis" in final_response and "key_findings" in final_response.get("analysis", {}):
            raw_findings = final_response["analysis"]["key_findings"]
            normalized_insights = []
            for f in (raw_findings or []):
                if isinstance(f, dict):
                    normalized_insights.append(f)
                elif hasattr(f, "model_dump"):
                    normalized_insights.append(f.model_dump(mode="json"))
                else:
                    normalized_insights.append({"title": str(f), "description": "", "metric": None})
            final_response["insights"] = normalized_insights

        # Attach dashboard from visualization response
        if state.visualization_response is not None and state.visualization_response.dashboard is not None:
            dashboard = state.visualization_response.dashboard
            try:
                final_response["dashboard"] = dashboard.model_dump(mode="json")
            except Exception:
                pass

    return final_response, report_path_str, report_html_str


# ---------------------------------------------------------------------------
# API schemas
# ---------------------------------------------------------------------------
class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, description="Natural-language question for the system")


class AskResponse(BaseModel):
    query_id: str
    status: QueryStatus
    message: str


class ResultsResponse(BaseModel):
    query_id: str
    question: str
    status: QueryStatus
    created_at: str
    completed_at: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    workflow_initialized: bool
    workflow_error: Optional[str] = None
    active_queries: int
    timestamp: str


class ReportListItem(BaseModel):
    request_id: str
    question: str
    status: str
    created_at: str
    completed_at: Optional[str] = None
    summary_preview: Optional[str] = None
    report_available: bool = False
    download_url: Optional[str] = None


class ReportsListResponse(BaseModel):
    reports: List[ReportListItem]
    total: int


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
FRONTEND_DIR = Path("frontend/frontend")

app = FastAPI(
    title="Agentic AI Data Analysis API",
    description="Submit natural-language questions and retrieve orchestrated SQL + analysis + report results.",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Background job helper (kept for the legacy /api/ask endpoint)
# ---------------------------------------------------------------------------
def _run_workflow_job(query_id: str, question: str) -> None:
    """Executes the orchestrator workflow in the background and records the outcome."""
    logger.info("[%s] background job started", query_id)
    try:
        final_response, report_path_str, report_html_str = _execute_workflow(query_id, question)
        store.complete(query_id, final_response, report_path=report_path_str, report_html=report_html_str)
        logger.info("[%s] background job completed successfully", query_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("[%s] background job failed", query_id)
        store.fail(query_id, str(exc))


# ---------------------------------------------------------------------------
# MAIN ENDPOINT: POST /api/analyze   (synchronous — frontend blocks on this)
# ---------------------------------------------------------------------------
@app.post("/api/analyze")
async def analyze(req: AskRequest):
    """
    Submit a natural-language analysis request and receive the full result.

    Runs the complete OrchestratorWorkflow synchronously (in a thread pool so
    the event loop is not blocked), then returns a unified JSON response
    containing the analysis, dashboard, insights, and report metadata.
    """
    if workflow is None:
        logger.error("Rejecting /api/analyze: workflow not initialized (%s)", workflow_init_error)
        raise HTTPException(
            status_code=503,
            detail=f"Workflow not available: {workflow_init_error}",
        )

    query_id = str(uuid.uuid4())
    store.create(query_id, req.question)
    logger.info("[%s] /api/analyze accepted | question=%r", query_id, req.question)

    try:
        # Run the CPU/LLM-bound workflow in a thread so the async event loop
        # is not blocked (asyncio.to_thread requires Python 3.9+).
        final_response, report_path_str, report_html_str = await asyncio.to_thread(
            _execute_workflow, query_id, req.question
        )

        store.complete(
            query_id,
            final_response,
            report_path=report_path_str,
            report_html=report_html_str,
        )

        logger.info("[%s] /api/analyze completed", query_id)

        # Return the structured response directly (already fully assembled by
        # _execute_workflow).
        if isinstance(final_response, dict):
            return final_response
        return {"success": False, "request_id": query_id, "error": "Unexpected workflow output format"}

    except Exception as exc:
        logger.exception("[%s] /api/analyze failed", query_id)
        store.fail(query_id, str(exc))
        raise HTTPException(
            status_code=500,
            detail=f"Analysis failed: {exc}",
        )


# ---------------------------------------------------------------------------
# GET /api/report/{request_id}/download
# ---------------------------------------------------------------------------
@app.get("/api/report/{request_id}/download")
async def download_report(request_id: str):
    """
    Download the compiled .docx Word report for a given request_id.

    Responses:
    - 200  Report found and returned as a downloadable .docx file.
    - 404  No request or report exists for the given request_id.
    - 409  Analysis exists but the report has not been generated yet.
    - 500  Unexpected storage failure.
    """
    record = store.get(request_id)

    # If not in memory, check if the .docx exists on disk anyway
    # (covers the case where the server restarted after generating the file).
    report_path = get_report_path(request_id)
    file_on_disk = report_path.exists()

    if record is None and not file_on_disk:
        raise HTTPException(
            status_code=404,
            detail=f"No report found for request_id={request_id}",
        )

    if record is not None:
        if record["status"] == QueryStatus.PROCESSING:
            raise HTTPException(
                status_code=409,
                detail="Analysis is still processing. Please try again shortly.",
            )

        if record["status"] == QueryStatus.FAILED:
            raise HTTPException(
                status_code=404,
                detail="Analysis failed. No report was generated.",
            )

    if not file_on_disk:
        raise HTTPException(
            status_code=409,
            detail="Analysis completed but no report file was generated.",
        )

    # Determine a clean download filename
    question = (record or {}).get("question", "")
    safe_stem = "".join(c if c.isalnum() or c in " _-" else "_" for c in question[:40]).strip() or "report"
    safe_stem = safe_stem.replace(" ", "_")
    filename = f"{safe_stem}.docx"

    logger.info("[%s] Serving report download: %s", request_id, report_path)

    return FileResponse(
        path=str(report_path),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=filename,
    )


# ---------------------------------------------------------------------------
# GET /api/reports
# ---------------------------------------------------------------------------
@app.get("/api/reports", response_model=ReportsListResponse)
async def list_reports(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    """
    Return a paginated list of all analysis requests and their report status,
    sorted from newest to oldest.

    Also scans the `reports/` directory so entries with .docx files on disk
    are surfaced even if the server was restarted and the in-memory store lost
    the record.
    """
    # Collect all in-memory records
    all_records = store.all()

    # Supplement with any .docx files found on disk that are NOT in memory
    in_memory_ids = {r["query_id"] for r in all_records}
    for docx_file in REPORTS_DIR.glob("*.docx"):
        file_request_id = docx_file.stem
        if file_request_id not in in_memory_ids:
            stat = docx_file.stat()
            all_records.append({
                "query_id": file_request_id,
                "question": f"(Recovered from disk: {docx_file.name})",
                "status": QueryStatus.COMPLETED,
                "created_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                "completed_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                "result": None,
                "error": None,
                "report_path": str(docx_file),
                "report_html": None,
            })

    # Sort newest first
    all_records.sort(
        key=lambda r: r.get("created_at") or "",
        reverse=True,
    )

    total = len(all_records)
    paginated = all_records[offset: offset + limit]

    items: List[ReportListItem] = []
    for record in paginated:
        rid = record["query_id"]

        # Determine report availability
        report_available = False
        download_url = None
        if record.get("report_path") and Path(record["report_path"]).exists():
            report_available = True
            download_url = f"/api/report/{rid}/download"
        elif get_report_path(rid).exists():
            report_available = True
            download_url = f"/api/report/{rid}/download"

        # Build summary preview from the stored result (if available)
        summary_preview: Optional[str] = None
        result = record.get("result")
        if result and isinstance(result, dict):
            analysis = result.get("analysis") or {}
            summary_preview = analysis.get("summary") or result.get("question")
        if summary_preview and len(summary_preview) > 150:
            summary_preview = summary_preview[:150] + "…"

        items.append(
            ReportListItem(
                request_id=rid,
                question=record.get("question") or "",
                status=record.get("status", QueryStatus.COMPLETED),
                created_at=record.get("created_at") or "",
                completed_at=record.get("completed_at"),
                summary_preview=summary_preview,
                report_available=report_available,
                download_url=download_url,
            )
        )

    return ReportsListResponse(reports=items, total=total)


# ---------------------------------------------------------------------------
# Legacy endpoints (kept for compatibility)
# ---------------------------------------------------------------------------
@app.post("/api/ask", response_model=AskResponse, status_code=202)
async def ask_question(req: AskRequest, background_tasks: BackgroundTasks):
    """Submit a question. Processing happens in the background; poll /api/results/{query_id}."""
    if workflow is None:
        logger.error("Rejecting request: workflow not initialized (%s)", workflow_init_error)
        raise HTTPException(status_code=503, detail=f"Workflow not available: {workflow_init_error}")

    query_id = str(uuid.uuid4())
    store.create(query_id, req.question)
    logger.info("[%s] request accepted | question=%r", query_id, req.question)

    background_tasks.add_task(_run_workflow_job, query_id, req.question)

    return AskResponse(
        query_id=query_id,
        status=QueryStatus.PROCESSING,
        message="Question accepted. Poll GET /api/results/{query_id} for the outcome.",
    )


@app.get("/api/results/{query_id}", response_model=ResultsResponse)
async def get_results(query_id: str):
    """Retrieve the status and, once available, the result for a submitted query."""
    record = store.get(query_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"No query found with id {query_id}")
    # Adapt keys for ResultsResponse
    return ResultsResponse(
        query_id=record["query_id"],
        question=record["question"],
        status=record["status"],
        created_at=record["created_at"],
        completed_at=record.get("completed_at"),
        result=record.get("result"),
        error=record.get("error"),
    )


@app.get("/api/health")
async def health_check():
    """Reports whether the API and its underlying workflow are ready to serve requests."""
    return {
        "status": "ok" if workflow is not None else "degraded",
        "workflow_initialized": workflow is not None,
        "workflow_error": workflow_init_error,
        "active_queries": len(store._data),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Static frontend (must be mounted AFTER API routes)
# ---------------------------------------------------------------------------
if FRONTEND_DIR.exists():
    @app.get("/", response_class=HTMLResponse)
    async def root():
        index_path = FRONTEND_DIR / "index.html"
        return HTMLResponse(content=index_path.read_text(encoding="utf-8"))

    app.mount("/css", StaticFiles(directory=str(FRONTEND_DIR / "css")), name="css")
    app.mount("/js", StaticFiles(directory=str(FRONTEND_DIR / "js")), name="js")
    
    # Mount outputs for chart images (create if missing so StaticFiles doesn't crash)
    outputs_dir = Path("outputs")
    outputs_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/outputs", StaticFiles(directory=str(outputs_dir)), name="outputs")
        
    logger.info("Static frontend mounted from %s", FRONTEND_DIR)
else:
    logger.warning("Frontend directory %s not found — static files will not be served", FRONTEND_DIR)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
