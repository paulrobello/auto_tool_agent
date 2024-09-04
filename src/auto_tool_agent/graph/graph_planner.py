"""Planner related nodes for graph agent."""

from __future__ import annotations

import ast
from pathlib import Path

from langchain_core.language_models import BaseChatModel

from auto_tool_agent.app_logging import console, global_vars
from auto_tool_agent.graph.graph_shared import (
    build_chat_model,
    load_existing_tools,
    UserAbortError,
)
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


# pylint: disable=too-many-branches
def plan_project(state: GraphState):
    """Check if a tool is needed."""
    global_vars.status_update("Planning project...")
    available_tools = get_available_tool_descriptions()
    system_prompt = """
ROLE: You are an application architect

TASK: Plan a project based on a user's request.

INSTRUCTIONS:
1. Analyze the user's request and create a simple, step-by-step plan to achieve the objective.
2. Each step should involve specific tool-using tasks that, when executed correctly, will yield the desired result.
3. Ensure each step contains all necessary information - do not skip or assume steps.
4. The final step should produce the final answer or result.

5. Examine the list of available tools and determine which are relevant to the user's request.
6. For each relevant tool:
   a. Include it in the needed_tools list.
   b. Set the "existing" field to True.
   c. If the tool is listed as having errors, set its "needs_review" field to True.

7. If additional tools are needed they MUST follow these instructions:
   a. Give each new tool a name that is a valid Python identifier in snake_case.
   b. Provide a detailed description for each new tool.
   c. Include them in the needed_tools list.
   d. Set the "existing" field to False for new tools.
   e. Do not include dependencies; they will be filled in later.
   f. Any HTML content that is fetched should be converted to markdown in same tool that fetched it.

8. Explain how each tool (existing and new) is relevant to the user's request.
9. Determine and explain the order in which the tools should be used.

10. Ensure your response follows the PlanProjectResponse structure, including:
    - An explanation of the project (explanation)
    - A list of steps (steps)
    - A list of needed tools (needed_tools)

Be concise yet thorough in your explanations, focusing on the practical application of tools to solve the user's request.
"""
    model: BaseChatModel = build_chat_model(temperature=0.5)
    structure_model = model.with_structured_output(PlanProjectResponse)
    console.log(
        "[bold green]All available tools: [bold yellow]",
        list(tool_data.ai_tools.keys()),
    )
    chat_history = [
        ("system", system_prompt),
        ("user", state["user_request"]),
        (
            "user",
            f"""Available tools:
    {available_tools}
    """,
        ),
    ]

    user_has_input = True
    while user_has_input:
        result: PlanProjectResponse = structure_model.with_config(
            {"run_name": "Project Planner"}
        ).invoke(
            chat_history
        )  # type: ignore

        for tool_def in result.needed_tools:
            tool_def.load()
            if tool_data.bad_tools:
                if tool_def.name in tool_data.bad_tools:
                    tool_def.needs_review = True

            if opts.review_tools:
                if not tool_def.needs_review:
                    console.log(
                        f"[bold green]Forcing review of tool:[bold yellow] {tool_def.name}"
                    )
                tool_def.needs_review = True
        console.log("[bold green]Plan explanation:")
        console.log(result.explanation)
        response_message: list[str] = ["Plan explanation:"]
        response_message.append(result.explanation)
        response_message.append("Plan Steps:")
        console.log("[bold green]Plan Steps:")
        for i, step in enumerate(result.steps):
            console.log(f"{i} - {step}")
            response_message.append(f"{i} - {step}")
        console.log("[bold green]Needed Tools:")
        for i, tool in enumerate(result.needed_tools):
            console.log(
                f"{i} - {tool.name} - Existing: {tool.existing} - Needs Review: {tool.needs_review}\n\t{tool.description}"
            )
            response_message.append(
                f"{i} - {tool.name} - Existing: {tool.existing} - Needs Review: {tool.needs_review}"
            )
        chat_history += [("ai", "\n".join(response_message))]
        if opts.interactive:
            global_vars.status_stop()
            response = (
                console.input(
                    "[bold green]Accept plan? [bold yellow][Y]es/No/Revise [bold green]: \n"
                )
                .strip()
                .lower()
            )
            global_vars.status_start()
            console.log("response", response)
            if response == "":
                response = "y"
            if response == "r":
                global_vars.status_stop()
                user_has_input = console.input(
                    "[bold green]Enter instructions for re-plan: "
                ).strip()
                global_vars.status_start()
                if user_has_input:
                    chat_history += [("user", user_has_input)]
                continue
            if response != "y":
                console.log("[bold red]Plan rejected. Aborting....")
                raise UserAbortError("Plan rejected.")
        return {
            "call_stack": ["plan_project"],
            "needed_tools": result.needed_tools,
        }
    raise ValueError("Failed to plan project.")
