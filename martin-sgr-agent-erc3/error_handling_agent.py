"""Error handling agent for SGR agent.

This module analyzes API errors and determines:
1. What outcome should be returned to the user
2. Whether the agent should continue processing or stop
"""

from typing import Literal, Union
from openai import OpenAI
from pydantic import BaseModel, Field
from erc3 import ApiException
from erc3.erc3.dtos import Outcome

# Extend Outcome with error-specific outcome literals
ErrorOutcome = Union[
    Outcome,
    Literal[
        "ok_with_parameter_adjustment",
    ],
]

CLI_BLUE = "\x1B[34m"
CLI_CLR = "\x1B[0m"

class ErrorAnalysis(BaseModel):
    """Structured response from the error handling agent."""

    outcome: ErrorOutcome = Field(
        ...,
        description="The appropriate outcome for this error"
    )
    should_continue: bool = Field(
        ...,
        description="Whether the agent should continue processing or stop"
    )
    reasoning: str = Field(
        ...,
        description="Brief explanation of why this outcome and continuation decision were chosen"
    )
    suggested_message: str = Field(
        ...,
        description="User-friendly message to include in the response"
    )


class ErrorHandlingAgent:
    """Agent that analyzes API errors and determines how to handle them."""

    def __init__(self, client: OpenAI, model: str):
        self.client = client
        self.model = model

    def analyze_error(self, error: ApiException, context: str = "") -> ErrorAnalysis:
        """
        Analyze an API error and determine the appropriate outcome and whether to continue.

        Args:
            error: The ApiException that was raised
            context: Optional context about what the agent was trying to do

        Returns:
            ErrorAnalysis with outcome, continuation decision, and reasoning
        """
        # First, try rule-based classification for common cases
        quick_analysis = self._quick_classify(error)
        if quick_analysis:
            print(f"{CLI_BLUE}error agent{CLI_CLR}. Quick classification applied: {quick_analysis.outcome}")
            return quick_analysis

        # Fall back to LLM-based analysis for complex cases
        print(f"{CLI_BLUE}error agent{CLI_CLR}. LLM analysis invoked for complex error.")
        return self._llm_analyze(error, context)

    def _quick_classify(self, error: ApiException) -> ErrorAnalysis | None:
        """
        Quick rule-based classification for common error patterns.

        Returns None if the error requires LLM analysis.
        """
        error_msg = str(error.api_error.error).lower()
        detail = str(error.detail).lower()

        # Not found errors
        if any(pattern in error_msg or pattern in detail for pattern in [
            "not found",
            "does not exist",
            "no such",
            "cannot find",
        ]):
            return ErrorAnalysis(
                outcome="ok_not_found",
                should_continue=True,
                reasoning="Resource not found - this is expected and agent can continue with alternative approach",
                suggested_message="The requested resource was not found. This may be expected."
            )

        # Access denied / security errors
        if any(pattern in error_msg or pattern in detail for pattern in [
            "access denied",
            "forbidden",
            "unauthorized",
            "permission",
            "not allowed",
            "insufficient privileges",
        ]):
            return ErrorAnalysis(
                outcome="denied_security",
                should_continue=False,
                reasoning="Security/permission error - user lacks access, should stop and inform user",
                suggested_message="Access denied. You do not have permission to perform this action."
            )

        # Validation errors (bad parameters)
        if any(pattern in error_msg or pattern in detail for pattern in [
            "invalid",
            "validation error",
            "bad request",
            "malformed",
            "must be",
            "cannot be negative",
        ]):
            return ErrorAnalysis(
                outcome="none_clarification_needed",
                should_continue=True,
                reasoning="Validation error - agent made a mistake in parameters, can retry with corrected values",
                suggested_message="Invalid request parameters. Adjusting and retrying."
            )

        # Rate limiting / temporary issues
        if any(pattern in error_msg or pattern in detail for pattern in [
            "rate limit",
            "too many requests",
            "throttled",
            "try again",
        ]):
            return ErrorAnalysis(
                outcome="error_internal",
                should_continue=True,
                reasoning="Temporary rate limiting - agent can retry after brief pause",
                suggested_message="Service temporarily throttled. Will retry."
            )

        # Internal server errors
        if any(pattern in error_msg or pattern in detail for pattern in [
            "internal error",
            "server error",
            "500",
            "503",
        ]):
            return ErrorAnalysis(
                outcome="error_internal",
                should_continue=False,
                reasoning="Internal server error - cannot proceed, should inform user",
                suggested_message="An internal server error occurred. Unable to complete the request."
            )

        # Unsupported operation
        if any(pattern in error_msg or pattern in detail for pattern in [
            "not supported",
            "not implemented",
            "unsupported",
        ]):
            return ErrorAnalysis(
                outcome="none_unsupported",
                should_continue=False,
                reasoning="Operation not supported by the system",
                suggested_message="This operation is not supported by the system."
            )

        # If no pattern matches, return None to trigger LLM analysis
        return None

    def _llm_analyze(self, error: ApiException, context: str) -> ErrorAnalysis:
        """
        Use LLM to analyze complex errors that don't match simple patterns.
        """
        system_prompt = """You are an error analysis expert for the Aetherion business system.

Your task is to analyze API errors and determine:
1. The appropriate outcome category
2. Whether the agent should continue processing or stop
3. A clear explanation of your reasoning

Rules:
- Negative numbers for pagination errors indicate a server issue.

Outcome categories:
- ok_answer: Successful response with data
- ok_not_found: Resource not found (expected, can continue)
- denied_security: Access/permission denied (stop, inform user)
- none_clarification_needed: Invalid parameters or need clarification (can retry)
- none_unsupported: Operation not supported (stop, inform user)
- error_internal: Server/system error (usually stop)

Guidelines for should_continue:
- Continue: Not found, validation errors, temporary issues, can retry with different approach
- Stop: Security denials, internal errors, unsupported operations, unrecoverable failures
"""

        user_prompt = f"""Analyze this API error:

Error message: {error.api_error.error}
Error detail: {error.detail}
Context: {context if context else "No additional context provided"}

Determine:
1. Which outcome category best fits this error
2. Should the agent continue processing or stop
3. Reasoning for your decision
4. A user-friendly message to include in the response
"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        completion = self.client.beta.chat.completions.parse(
            model=self.model,
            messages=messages,
            response_format=ErrorAnalysis,
            max_completion_tokens=500,
        )

        return completion.choices[0].message.parsed


def create_error_response(
    analysis: ErrorAnalysis,
    links: list = None
) -> dict:
    """
    Helper function to create a properly formatted error response.

    Args:
        analysis: The ErrorAnalysis from the error handling agent
        links: Optional list of AgentLink objects to include

    Returns:
        Dictionary ready to be used as Req_ProvideAgentResponse
    """
    return {
        "tool": "/respond",
        "message": analysis.suggested_message,
        "outcome": analysis.outcome,
        "links": links or []
    }
