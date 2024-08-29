"""State for the graph"""

from __future__ import annotations

from typing import TypedDict, Annotated, List
from pydantic import BaseModel, Field


class ToolDescription(BaseModel):
    """Tool description."""

    name: str
    description: str
    existing: bool = Field(
        description="Set to True if this tool already exists or False if it needs to be built."
    )


class ToolNeededResponse(BaseModel):
    """Tool needed response."""

    needed_tools: List[ToolDescription]


def add_node_call(left: list[str], right: list[str]) -> list[str]:
    """Add a node call."""
    return left + right


class GraphState(TypedDict):
    """Graph state."""

    call_stack: Annotated[list[str], add_node_call]
    sandbox_dir: str
    dependencies: list[str]
    user_request: str
    needed_tools: List[ToolDescription]
