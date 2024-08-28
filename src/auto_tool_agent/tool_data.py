"""Tool data."""

from __future__ import annotations

from dataclasses import dataclass, field

from langchain_core.tools import BaseTool


@dataclass
class ToolData:
    """Tool data."""

    last_tool_load: float = 0
    ai_tools: dict[str, BaseTool] = field(default_factory=dict)
    bad_tools: list[str] = field(default_factory=list)

    def add_good_tool(self, name: str, tool: BaseTool) -> None:
        """Add a good tool."""
        if name in self.bad_tools:
            self.bad_tools.remove(name)
        self.ai_tools[name] = tool

    def add_bad_tool(self, name: str) -> None:
        """Add a bad tool."""
        if name in self.ai_tools:
            del self.ai_tools[name]
        if name not in self.bad_tools:
            self.bad_tools.append(name)


tool_data = ToolData()
