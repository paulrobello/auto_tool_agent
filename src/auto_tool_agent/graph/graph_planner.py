"""Planner related nodes for graph agent."""

from __future__ import annotations

import ast
from pathlib import Path

from langchain_core.language_models import BaseChatModel

from auto_tool_agent.app_logging import console
from auto_tool_agent.graph.graph_shared import build_chat_model, load_existing_tools
from auto_tool_agent.graph.graph_state import GraphState, PlanProjectResponse
from auto_tool_agent.opts import opts
from auto_tool_agent.tool_data import tool_data


def get_available_tool_descriptions_old(state: GraphState) -> str:
    """Get available tool descriptions."""
    result = ""
    src_dir = Path(state["sandbox_dir"]) / "src" / "sandbox"

    for file in src_dir.iterdir():
        if (
            not file.name.endswith(".py")
            or file.name.startswith("_")
            or file.name.startswith(".")
        ):
            continue
        data = file.read_text(encoding="utf-8")
        try:
            module = ast.parse(data)
            func = next(
                (n for n in module.body if isinstance(n, ast.FunctionDef)), None
            )
            docstring = ast.get_docstring(func) if func else ""
        except SyntaxError:
            docstring = ""
        result += f"Tool_Name: {file.name[:-3]}\n"
        result += f"Description: {docstring or data}\n\n"

    return result


def get_available_tool_descriptions() -> str:
    """Get available tool descriptions."""
    load_existing_tools()
    result = ""
    for name, tool in tool_data.ai_tools.items():
        result += "=" * 50 + "\n"
        result += f"Tool_Name: {name}\n"
        result += f"Description: {tool.description}\n"
        result += "=" * 50 + "\n\n"

    if tool_data.bad_tools:
        result += "The following tools have errors that need to be fixed:\n"
        for name, error in tool_data.bad_tools.items():
            result += "=" * 50 + "\n"
            result += f"Tool_Name: {name}\n"
            result += f"Exception: {error}\n"
            result += "=" * 50 + "\n\n"

    return result


def plan_project(state: GraphState):
    """Check if a tool is needed."""
    console.log("[bold green]Planning project...")
    available_tools = get_available_tool_descriptions()
    system_prompt = """
# You are an application architect.
Your job is to examine the users request and determine what tools will be needed.
You must follow all instructions below:
* Examine the list of available tools and if they are relevant to the users request include them in the needed_tools list.
* Existing tools should have the existing field set to True.
* If a tool is listed as having errors it should have its needs_review field set to True.
* Reason how each tool is relevant to the users request and in what order they should be used.
* If additional tools are needed follow the instructions below:
    * Give the new tools a name that is a valid Python identifier in snake_case
    * Provide a detailed description
    * Include them in the needed_tools list.
    * Set the field "existing" to False.
    * Dependencies will be filled in later do not include them.
    """
    model: BaseChatModel = build_chat_model(temperature=0.5)
    structure_model = model.with_structured_output(PlanProjectResponse)
    console.log(
        "[bold green]All available tools: [bold yellow]",
        list(tool_data.ai_tools.keys()),
    )
    result: PlanProjectResponse = structure_model.with_config(
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
    for tool_def in result.needed_tools:
        tool_def.load()
        if opts.review_tools:
            if not tool_def.needs_review:
                console.log(
                    f"[bold green]Forcing review of tool:[bold yellow] {tool_def.name}"
                )
            tool_def.needs_review = True
    console.log("[bold green]Plan Steps:")
    for i, step in enumerate(result.steps):
        console.log(f"{i} - {step}")
    if opts.interactive:
        response = console.input(
            "[bold green]Accept plan? [bold yellow][Y]/n [bold green]: \n"
        )
        console.log("response", response)
        if response != "" and response.lower() != "y":
            console.log("[bold red]Plan rejected. Aborting....")
            raise ValueError("Plan rejected.")
    return {
        "call_stack": ["plan_project"],
        "needed_tools": result.needed_tools,
    }
