"""Tool data."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from langchain_core.tools import BaseTool


@dataclass
class ToolData:
    """Tool data."""

    last_tool_load: float = 0
    ai_tools: dict[str, BaseTool] = field(default_factory=dict)
    bad_tools: dict[str, Exception] = field(default_factory=dict)

    def add_good_tool(self, name: str, tool: BaseTool) -> None:
        """Add a good tool."""
        name = os.path.basename(name)
        if name in self.bad_tools:
            del self.bad_tools[name]
        self.ai_tools[name] = tool

    def add_bad_tool(self, name: str, error: Exception) -> None:
        """Add a bad tool."""
        name = os.path.basename(name)
        if name in self.ai_tools:
            del self.ai_tools[name]
        if name not in self.bad_tools:
            self.bad_tools[name] = error


tool_data = ToolData()
