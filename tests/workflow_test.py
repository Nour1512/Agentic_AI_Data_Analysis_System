import uuid
from services.groq_service import GroqService
from database.sqlserver_client import SQLServerClient

from agents.sql_agent_python_only import SQLAgentFromScratch
from agents.analysis_agent import AnalysisAgent
from agents.report_agent import ReportAgent
from agents.orchestrator.orchestrator import OrchestratorAgent
from agents.orchestrator.orchestrator_workflow import OrchestratorWorkflow
from services.visualization_service import VisualizationService
from agents_schema.orchestrator import UserRequest
import logging
import json


def create_workflow():

    # Shared services
    groq_service = GroqService()
    sql_server_client = SQLServerClient()

    # Agents
    orchestrator_agent = OrchestratorAgent(
        llm_client=groq_service,
    )

    sql_agent = SQLAgentFromScratch(
        groq_service=groq_service,
        database_client=sql_server_client,
    )

    analysis_agent = AnalysisAgent(
        llm_client=groq_service,
    )

    report_agent = ReportAgent(
        llm_client=groq_service,
    )

    # Connect agents through the workflow
    workflow = OrchestratorWorkflow(
        orchestrator_agent=orchestrator_agent,
        sql_agent=sql_agent,
        analysis_agent=analysis_agent,
        visualization_service = VisualizationService(),
        report_agent=report_agent,
    )

    return workflow


workflow = create_workflow()

request_payload = UserRequest(
    request_id=str(uuid.uuid4()),
    question="Generate a report on monthly revenue trends for 2025 across all product categories. Break down net revenue and order count by month, and include a chart recommendation to visualize our top 5 revenue-generating categories over time."
)

# workflow.run(request_payload)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

# Execute the workflow
state = workflow.run(request_payload)

# Add this to display the workflow output:
if state.final_response:
    print(json.dumps(state.final_response, indent=2, default=str))
else:
    print("Workflow completed, but state.final_response is empty.")
