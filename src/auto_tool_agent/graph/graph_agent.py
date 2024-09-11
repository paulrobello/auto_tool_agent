"""Agent system using langgraph."""

from __future__ import annotations

from typing import Any
from pathlib import Path

from langchain_core.runnables.graph import NodeStyles
from rich import print  # pylint: disable=redefined-builtin
from rich.markdown import Markdown

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from auto_tool_agent.app_logging import console, global_vars
from auto_tool_agent.graph.graph_code import (
    review_tools,
    build_tool,
)
from auto_tool_agent.graph.graph_output import format_output
from auto_tool_agent.graph.graph_planner import plan_project
from auto_tool_agent.graph.graph_results import (
    is_tool_needed,
    get_results_pre_check,
    has_needed_tools,
    get_results,
)
from auto_tool_agent.graph.graph_sandbox import setup_sandbox
from auto_tool_agent.graph.graph_shared import (
    save_state,
    UserAbortError,
)
from auto_tool_agent.graph.graph_state import (
    GraphState,
)
from auto_tool_agent.lib.output_utils import csv_to_table, highlight_json
from auto_tool_agent.lib.session import session
from auto_tool_agent.opts import opts

# Define a new graph
workflow = StateGraph(GraphState)

workflow.add_node("setup_sandbox", setup_sandbox)
workflow.add_node("plan_project", plan_project)
workflow.add_node("build_tool", build_tool)
workflow.add_node("review_tools", review_tools)
workflow.add_node("get_results_pre_check", get_results_pre_check)
workflow.add_node("get_results", get_results)
workflow.add_node("format_output", format_output)
workflow.add_node("save_state", save_state)

workflow.add_edge(START, "setup_sandbox")
workflow.add_edge("setup_sandbox", "plan_project")
workflow.add_conditional_edges("plan_project", is_tool_needed)
workflow.add_edge("build_tool", "review_tools")
workflow.add_edge("review_tools", "get_results_pre_check")
workflow.add_conditional_edges("get_results_pre_check", has_needed_tools)
workflow.add_edge("get_results", "format_output")
workflow.add_edge("format_output", "save_state")
workflow.add_edge("save_state", END)


# Initialize memory to persist state between graph runs
checkpointer = MemorySaver()

# This compiles the workflow into a LangChain Runnable,
# meaning you can use it as you would any other runnable.
# Note that we're (optionally) passing the memory when compiling the graph
app = workflow.compile(checkpointer=checkpointer)


def generate_graph_viz():
    """Generate graphviz."""
    global_vars.status_update("Creating graph viz...")
    # Draw the graph via mermaid
    with open("graph.mermaid", "wt", encoding="utf-8") as mermaid_file:
        mermaid_file.write(
            app.get_graph().draw_mermaid(
                node_colors=NodeStyles(
                    default="fill: #333", first="fill: #353", last="fill: #533"
                )
            )
        )


def run_graph():
    """Run the graph."""

    generate_graph_viz()

    if opts.generate_graph:
        return

    old_state: dict[str, Any] = {}
    state_file = Path("state.json")
    if state_file.exists():
        pass
        # old_state = json.loads(state_file.read_text(encoding="utf-8"))

    initial_state: GraphState = {
        "clean_run": opts.clear_sandbox,
        "sandbox_dir": opts.sandbox_dir,
        "dependencies": old_state.get(
            "dependencies",
            [
                "asyncio",
                "boto3>=1.34.0",
                "langchain",
                "langchain-core",
                "langchain-community",
                "langchain-ollama",
                "langchain-openai",
                "langchain-anthropic",
                "langchain-google-genai",
                "langchain-groq",
                "langchain-aws>=0.1.18",
                "langgraph",
                "markdownify",
                "pydantic",
                "pydantic-core",
                "requests",
                "rich",
                "black",
                "watchdog",
                "python-dotenv>=1.0.1",
                "simplejson",
            ],
        ),
        "user_request": opts.user_request,
        "needed_tools": [],
        "call_stack": [],
        "final_result": None,
        "user_feedback": "",
    }

    console.log(
        f"[bold green]Invoking graph request: [bold cyan]{initial_state['user_request']}"
    )
    try:
        final_state = app.invoke(
            initial_state,
            config={
                "configurable": {
                    "thread_id": session.id,
                    "recursion_limit": opts.max_iterations,
                }
            },
        )
    except UserAbortError as user_abort:
        console.log(f"[bold red]{user_abort}")
        return

    if opts.verbose > 2:
        print(final_state)

    tool_list = ",".join([tool.name for tool in final_state["needed_tools"]])
    module_folder = opts.sandbox_dir / "src" / "sandbox"
    tool_file = module_folder / "tools.txt"
    tool_file.write_text(tool_list, encoding="utf-8")
    prompt_file = module_folder / "prompt.md"
    prompt_file.write_text(final_state["user_request"], encoding="utf-8")
    print("[bold yellow]Sandbox command:")
    print(
        f"clear;uv run python -m sandbox -t {tool_list} \"{final_state['user_request']}\""
    )

    output_file = Path("./final_result.md")
    if opts.output_file:
        output_file = opts.output_file

    if output_file.exists() and output_file.stat().st_size > 2:
        data = output_file.read_text(encoding="utf-8")

        if opts.output_format == "markdown":
            console.print(Markdown(data))
        elif opts.output_format == "json":
            console.print(highlight_json(data))
        elif opts.output_format == "csv":
            console.print(csv_to_table(data))
        elif opts.output_format == "text":
            console.print(data)
        else:
            console.print(data)
