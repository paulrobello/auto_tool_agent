"""Planner related nodes for graph agent."""

from __future__ import annotations

import ast
import os

from langchain_core.language_models import BaseChatModel

from auto_tool_agent.graph.graph_shared import build_chat_model
from auto_tool_agent.graph.graph_state import GraphState, ToolNeededResponse
from auto_tool_agent.tool_data import tool_data


def get_available_tool_descriptions_old(state: GraphState) -> str:
    """Get available tool descriptions."""
    tools = []
    src_dir = os.path.join(state["sandbox_dir"], "src", "sandbox")
    for file in os.listdir(src_dir):
        if not file.endswith(".py") or file.startswith("_") or file.startswith("."):
            continue
        with open(os.path.join(src_dir, file), "rt", encoding="utf-8") as f:
            data = f.read()
            try:
                module = ast.parse(data)
                func = next(
                    (n for n in module.body if isinstance(n, ast.FunctionDef)), None
                )
                docstring = ast.get_docstring(func) if func else ""
            except SyntaxError:
                docstring = ""
            tools.append({"file_name": file, "file": docstring or data})
    result = ""
    for tool_desc in tools:
        result += "Tool_Name: " + tool_desc["file_name"][:-3] + "\n"
        result += "Description: " + tool_desc["file"] + "\n\n"

    return result


def get_available_tool_descriptions() -> str:
    """Get available tool descriptions."""
    result = ""
    for name, tool in tool_data.ai_tools.items():
        result += f"Tool_Name: {name}\n"
        result += f"Description: {tool.description}\n\n"

    return result


def plan_project(state: GraphState):
    """Check if a tool is needed."""

    available_tools = get_available_tool_descriptions()
    system_prompt = """
# You are an application architect.
Your job is to examine the users request and determine what tools will be needed.
You must follow all instructions below:
* Examine the list of available tools and if they are relevant to the users request include them in the needed_tools list.
* Existing tools should have the existing field set to True.
* Do not call the tools only examine if the existing tools are needed to fulfill the users request.
* If additional tools are needed follow the instructions below:
    * Give the new tools a name that is a valid Python identifier in snake_case
    * Provide a detailed description
    * Include them in the needed_tools list.
    * Set the field "existing" to False.
    * Dependencies will be filled in later do not include them.
    """
    model: BaseChatModel = build_chat_model(temperature=0.5)
    structure_model = model.with_structured_output(ToolNeededResponse)

    result: ToolNeededResponse = structure_model.with_config(
        {"run_name": "Project Planner"}
    ).invoke(
        [
            ("system", system_prompt),
            ("user", state["user_request"]),
            (
                "user",
                f"""Available tools:
{available_tools}
""",
            ),
        ]
    )  # type: ignore
    return {
        "call_stack": ["plan_project"],
        "needed_tools": result.needed_tools,
    }
