"""State for the graph"""

from __future__ import annotations

from pathlib import Path

from typing import TypedDict, Annotated, List, Optional, Any
import black

from pydantic import BaseModel, Field

from sandbox.opts import opts


class ToolDescription(BaseModel):
    """Tool description for both needed and existing tools."""

    name: str = Field(
        description="Name of the tool. Should be a valid Python identifier in snake_case."
    )
    description: str = Field(
        description="Detailed description of the tool, its parameters and output."
    )
    code: str = Field(description="Code for the tool.", default="")
    dependencies: list[str] = Field(
        description="List of 3rd party python packages required to run this tool.",
        default_factory=list,
    )
    needs_review: bool = Field(
        description="Set to True if this tool needs review otherwise or.",
        default=False,
    )

    @property
    def existing(self) -> bool:
        """Check if the tool already exists."""
        return self.tool_path.exists()

    @property
    def tool_path(self) -> Path:
        """Get the path to the tool."""
        return (
            Path(opts.sandbox_dir)
            / "src"
            / "sandbox"
            / "ai_tools"
            / (self.name + ".py")
        )

    @property
    def metadata_path(self) -> Path:
        """Get the path to the tool."""
        return (
            Path(opts.sandbox_dir)
            / "src"
            / "sandbox"
            / "ai_tools_metadata"
            / (self.name + ".json")
        )

    def format_code(self) -> bool:
        """
        Format the code if needed.

        Returns:
            bool: True if the code was changed.
        """
        old_code = self.code
        self.code = black.format_str(self.code, mode=black.Mode())
        return old_code != self.code

    def save(self) -> None:
        """Save the tool code and metadata. Creating folders if needed."""
        self.format_code()
        self.tool_path.parent.mkdir(parents=True, exist_ok=True)
        self.tool_path.write_text(self.code, encoding="utf-8")

        self.metadata_path.parent.mkdir(parents=True, exist_ok=True)
        self.metadata_path.write_text(self.model_dump_json(indent=2), encoding="utf-8")

    def load(self) -> bool:
        """Load the tool via metadata with fallback to code."""
        if not self.metadata_path.exists():
            if self.tool_path.exists():
                self.code = self.tool_path.read_text(encoding="utf-8")
                self.needs_review = False
                self.dependencies = []
                return True
            return False
        meta = ToolDescription.model_validate_json(
            self.metadata_path.read_text(encoding="utf-8")
        )
        self.dependencies = meta.dependencies
        self.code = meta.code
        self.needs_review = False
        return True

    def delete(self):
        """Delete the tool and its metadata."""
        self.tool_path.unlink(missing_ok=True)
        self.metadata_path.unlink(missing_ok=True)
        self.code = ""
        self.dependencies = []

        self.needs_review = False


class CodeReviewResponse(BaseModel):
    """Code review response."""

    tool_valid: bool = Field(
        description="Set to True if the tool is valid and False if it is not.",
        default=True,
    )
    tool_updated: bool = Field(
        description="Set to True if the tool is updated and False if it is not.",
        default=False,
    )
    tool_issues: str = Field(
        description="Describe the issues that required the tool to be updated.",
        default="",
    )
    updated_tool_code: str = Field(description="Updated tool code.", default="")


class PlanProjectResponse(BaseModel):
    """Tool needed response."""

    user_request: str = Field(
        description="The user's request.",
    )
    explanation: str = Field(
        description="Explanation of the project.",
    )
    steps: List[str] = Field(
        description="List of steps to accomplish the project in order they should be done.",
        default_factory=list,
    )
    needed_tools: List[ToolDescription] = Field(
        description="List of needed tools.",
        default_factory=list,
    )

    def to_markdown(self) -> str:
        """Convert to markdown."""
        plan: List[str] = [
            "# Project Plan",
            "",
            "## User Request",
            "",
            self.user_request,
            "",
            "## Plan Explanation",
            "",
            self.explanation,
            "",
            "## Steps",
            "",
        ] + [f"- {step}" for step in self.steps]
        plan.append("## Need Tools")
        for tool in self.needed_tools:
            plan.append(f"- {tool.name}")
            plan.append(f"  - {tool.description}")

        return "\n".join(plan) + "\n"

    def save(self, path: Optional[Path] = None) -> None:
        """Save plan to a file as markdown."""
        plan_file = Path() / "plan.md"
        plan_file.write_text(self.to_markdown(), encoding="utf-8")

        plan_file = Path(opts.sandbox_dir) / "plan.md"
        plan_file.write_text(self.to_markdown(), encoding="utf-8")

        if path:
            path.write_text(self.to_markdown(), encoding="utf-8")


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
    sandbox_dir: Path
    plan: Optional[PlanProjectResponse]
    dependencies: list[str]
    user_request: str
    needed_tools: List[ToolDescription]
    final_result: Optional[FinalResultResponse]
    user_feedback: str
