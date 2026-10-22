from __future__ import annotations

import json
import logging
from typing import Any , Protocol

from prompts.orchestrator_prompt import (
    ORCHESTRATOR_SYSTEM_PROMPT,
)
from agents_schema.orchestrator import TaskSpec
from services.groq_service import GroqService


logger = logging.getLogger(__name__)


class LLMClient(Protocol):
    """
    Minimal interface required from the shared LLM service.

    GroqService satisfies this interface because it provides
    generate(system_prompt, user_prompt).
    """

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        """Return the model's text response."""
        ...



class OrchestratorAgent:
    """
    Orchestrator Agent.

    Converts a user's natural-language request into a validated
    TaskSpec that can be passed to the downstream agents.

    The Orchestrator is responsible for planning and task decomposition.

    It does NOT:
        - execute SQL
        - access the database
        - analyze data
        - generate charts
        - generate reports
    """

    def __init__(self, llm_client: LLMClient) -> None:
        """
        Initialize the Orchestrator.

        Parameters
        ----------
        llm_client:
            Shared LLM client used to communicate with Groq.
        """

        self.llm_client = llm_client

    def run(
        self,
        user_question: str,
        requested_formats: list[str] | None = None,
        context: dict[str, Any] | None = None,
    ) -> TaskSpec:
        """
        Convert a user request into a validated TaskSpec.

        Parameters
        ----------
        user_question:
            The user's natural-language data-analysis question.

        requested_formats:
            Optional formats requested by the user, such as
            ["table", "chart", "report"].

        context:
            Optional additional context available to the Orchestrator.

        Returns
        -------
        TaskSpec
            A validated structured plan for downstream agents.

        Raises
        ------
        ValueError
            If the LLM returns invalid JSON or an invalid TaskSpec.
        """

        if not user_question or not user_question.strip():
            raise ValueError(
                "user_question cannot be empty."
            )

        logger.info(
            "Orchestrator started processing user request."
        )

        user_prompt = self._build_user_prompt(
            user_question=user_question,
            requested_formats=requested_formats,
            context=context,
        )

        raw_response = self.llm_client.generate(
            system_prompt=ORCHESTRATOR_SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )

        task_spec = self._parse_response(raw_response)

        logger.info(
            "Orchestrator successfully created TaskSpec."
        )

        return task_spec

    def _build_user_prompt(
        self,
        user_question: str,
        requested_formats: list[str] | None,
        context: dict[str, Any] | None,
    ) -> str:
        """
        Build the user-side prompt sent to the LLM.
        """

        request_data = {
            "user_question": user_question,
            "requested_formats": requested_formats or [],
            "context": context or {},
        }

        return (
            "Analyze the following user request and create a "
            "structured TaskSpec.\n\n"
            "USER REQUEST:\n"
            f"{json.dumps(request_data, indent=2, default=str)}\n\n"
            "Return ONLY valid JSON matching the TaskSpec schema."
        )

    def _parse_response(
        self,
        raw_response: str,
        user_question: str = "",
        requested_formats: list[str] | None = None,
        request_id: str = "",
    ) -> TaskSpec:
        """Parse the LLM response and validate it against TaskSpec."""
        cleaned_response = self._clean_json(raw_response)

        try:
            response_data = json.loads(cleaned_response)
        except json.JSONDecodeError as exc:
            logger.error("Orchestrator returned invalid JSON: %s", raw_response)
            raise ValueError("Orchestrator LLM response was not valid JSON.") from exc

        # Ensure required top-level metadata fields are present
        response_data.setdefault("request_id", request_id or "N/A")
        response_data.setdefault("original_question", user_question)
        response_data.setdefault("requested_formats", requested_formats or [])

        # Flatten data_requirements if the LLM returned dictionaries instead of strings
        if "data_requirements" in response_data and isinstance(response_data["data_requirements"], list):
            flattened_reqs = []
            for item in response_data["data_requirements"]:
                if isinstance(item, dict):
                    # Extract the main description or convert dict to string summary
                    desc = item.get("description") or json.dumps(item)
                    flattened_reqs.append(desc)
                elif isinstance(item, str):
                    flattened_reqs.append(item)
            response_data["data_requirements"] = flattened_reqs

        try:
            return TaskSpec.model_validate(response_data)
        except Exception as exc:
            logger.error(
                "Orchestrator response failed TaskSpec validation: %s",
                response_data,
            )
            raise ValueError(
                "Orchestrator response does not match TaskSpec schema."
            ) from exc

    @staticmethod
    def _clean_json(
        response: str,
    ) -> str:
        """
        Remove Markdown code fences if the LLM accidentally
        wraps the JSON response in them.
        """

        cleaned = response.strip()

        if cleaned.startswith("```json"):
            cleaned = cleaned[len("```json"):].strip()

        elif cleaned.startswith("```"):
            cleaned = cleaned[len("```"):].strip()

        if cleaned.endswith("```"):
            cleaned = cleaned[:-3].strip()

        return cleaned