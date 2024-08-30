"""State for the graph"""

from __future__ import annotations

from typing import TypedDict, Annotated, List, Optional, Any
from pydantic import BaseModel, Field


class ToolDescription(BaseModel):
    """Tool description for both needed and existing tools."""

    name: str = Field(
        description="Name of the tool. Should be a valid Python identifier in snake_case."
    )
    description: str = Field(
        description="Detailed description of the tool and its parameters."
    )
    dependencies: list[str] = Field(
        description="List of 3rd party pyton packages required to run this tool.",
        default_factory=list,
    )
    existing: bool = Field(
        description="Set to True if this tool already exists or False if it needs to be built."
    )
    needs_review: bool = Field(
        description="Set to True if this tool needs review or False if it does not need review."
    )


class CodeReviewResponse(BaseModel):
    """Code review response."""

    tool_valid: bool = Field(
        description="Set to True if the tool is valid and False if it is not."
    )
    tool_updated: bool = Field(
        description="Set to True if the tool is updated and False if it is not."
    )
    tool_issues: str = Field(
        description="Describe the issues that required the tool to be updated."
    )
    updated_tool_code: str = Field(description="Updated tool code.")


class ToolNeededResponse(BaseModel):
    """Tool needed response."""

    needed_tools: List[ToolDescription]


class DependenciesNeededResponse(BaseModel):
    """Needed 3rd party dependencies response."""

    dependencies: list[str] = Field(
        description="List of 3rd party pyton packages required to run this tool.",
        default_factory=list,
    )


class FinalResultErrorResponse(BaseModel):
    """Final result error response."""

    tool_name: str = Field(description="Name of the tool.")
    error_message: str = Field(
        description="Error message if the tool failed to execute."
    )


class FinalResultResponse(BaseModel):
    """Final result response."""

    final_result: Any = Field(description="Final result of the tool.")
    error: Optional[FinalResultErrorResponse] = Field(
        default=None,
        description="Error message if the tool failed to execute.",
    )


def add_node_call(left: list[str], right: list[str]) -> list[str]:
    """Add a node call."""
    return left + right


class GraphState(TypedDict):
    """Graph state."""

    call_stack: Annotated[list[str], add_node_call]
    clean_run: bool
    sandbox_dir: str
    dependencies: list[str]
    user_request: str
    needed_tools: List[ToolDescription]
    final_result: Optional[FinalResultResponse]
    user_feedback: str
