"""
Centralized Groq LLM service.

This service is responsible for:
- communicating with the Groq API
- selecting the primary model
- falling back to a secondary model when appropriate
- keeping Groq-specific implementation details away from agents
"""

from __future__ import annotations

import logging
import os

from groq import Groq


logger = logging.getLogger(__name__)


class GroqService:
    """
    Shared service used by all agents that need an LLM.

    Agents should NOT communicate with Groq directly.
    They should call:

        groq_service.generate(...)

    The service handles the model selection and fallback logic.
    """

    def __init__(
        self,
        api_key: str | None = None,
        primary_model: str = "openai/gpt-oss-120b",
        fallback_model: str = "openai/gpt-oss-20b",
        temperature: float = 0,
    ) -> None:

        self.api_key = (
            api_key
            or os.getenv("GROQ_API_KEY")
        )

        if not self.api_key:
            raise ValueError(
                "GROQ_API_KEY environment variable is not set."
            )

        self.primary_model = primary_model
        self.fallback_model = fallback_model
        self.temperature = temperature

        self.client = Groq(
            api_key=self.api_key
        )

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        """
        Generate an LLM response.

        The primary model is attempted first.

        If the failure is considered recoverable,
        the fallback model is attempted.

        If the error is not recoverable, it is raised
        immediately instead of making an unnecessary
        second API call.
        """

        try:
            logger.info(
                "Calling Groq primary model: %s",
                self.primary_model,
            )

            return self._generate_with_model(
                model=self.primary_model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )

        except Exception as primary_error:

            if not self._should_fallback(primary_error):
                logger.error(
                    "Primary Groq model failed with a "
                    "non-recoverable error: %s",
                    primary_error,
                )

                raise

            logger.warning(
                "Primary Groq model failed with a recoverable "
                "error: %s. Trying fallback model.",
                primary_error,
            )

        try:
            logger.info(
                "Calling Groq fallback model: %s",
                self.fallback_model,
            )

            return self._generate_with_model(
                model=self.fallback_model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )

        except Exception as fallback_error:

            logger.exception(
                "Both Groq models failed."
            )

            raise RuntimeError(
                "Both primary and fallback Groq models failed."
            ) from fallback_error

    def _generate_with_model(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        """
        Send a single request to a specific Groq model.
        """

        response = self.client.chat.completions.create(
            model=model,

            messages=[
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": user_prompt,
                },
            ],

            temperature=self.temperature,
        )

        content = response.choices[0].message.content

        if not content:
            raise RuntimeError(
                f"Groq model '{model}' returned an empty response."
            )

        return content

    @staticmethod
    def _should_fallback(
        error: Exception,
    ) -> bool:
        """
        Determine whether the primary model failure
        is something that justifies trying the fallback.

        We currently identify recoverable errors by
        inspecting the exception status/code/message.

        This keeps the fallback logic centralized so
        individual agents do not need to understand
        Groq API errors.
        """

        status_code = getattr(
            error,
            "status_code",
            None,
        )

        error_code = getattr(
            error,
            "code",
            None,
        )

        error_message = str(error).lower()

        # HTTP 429 usually indicates rate limiting.
        if status_code == 429:
            return True

        # Common temporary/provider-side failures.
        if status_code in {
            408, 409, 500, 502, 503, 504
        }:
            return True

        # Some Groq exceptions expose an error code
        # instead of a status code.
        if error_code in {
            "rate_limit_exceeded",
            "service_unavailable",
            "internal_server_error",
        }:
            return True

        # Fallback for cases where the SDK does not expose
        # a structured status/code but the message clearly
        # indicates a temporary limit/unavailability issue.
        recoverable_keywords = [
            "rate limit",
            "rate_limit",
            "too many requests",
            "temporarily unavailable",
            "service unavailable",
            "server error",
            "internal server error",
            "timeout",
            "timed out",
        ]

        return any(
            keyword in error_message
            for keyword in recoverable_keywords
        )