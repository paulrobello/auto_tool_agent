"""Agent system using langgraph."""

from __future__ import annotations

import os
from typing import Literal, Any
import simplejson as json

from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables.graph import NodeStyles
from langchain_core.language_models import BaseChatModel
from rich import print  # pylint: disable=redefined-builtin
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from auto_tool_agent.graph.graph_code import (
    review_tools,
    sync_deps_if_needed,
    build_tool,
)
from auto_tool_agent.graph.graph_output import format_output
from auto_tool_agent.graph.graph_planner import plan_project
from auto_tool_agent.graph.graph_sandbox import setup_sandbox, sync_venv
from auto_tool_agent.graph.graph_shared import (
    build_chat_model,
    agent_log,
    save_state,
    load_existing_tools,
)
from auto_tool_agent.graph.graph_state import (
    GraphState,
    FinalResultResponse,
)
from auto_tool_agent.opts import opts

from auto_tool_agent.tool_data import tool_data


def is_tool_needed(state: GraphState) -> Literal["build_tool", "get_results_pre_check"]:
    """Check if a tool is needed."""
    # return "save_state"
    needed_tools = state["needed_tools"]
    for tool_def in needed_tools:
        if not tool_def.existing:
            return "build_tool"

    if sync_deps_if_needed(state):
        agent_log.info("Updated dependencies: %s", state["dependencies"])

    return "get_results_pre_check"


def get_results_pre_check(_: GraphState):
    """Check if a tool is needed."""
    return {"call_stack": ["get_results_pre_check"]}


def has_needed_tools(state: GraphState) -> Literal["plan_project", "get_results"]:
    """Check if a tool is needed."""
    needed_tools = state["needed_tools"]
    for tool_def in needed_tools:
        if tool_def.name not in tool_data.ai_tools:
            return "plan_project"

    return "get_results"


def get_results(state: GraphState):
    """Use tools to get results."""

    agent_log.info("needed_tools: %s", state["needed_tools"])
    load_existing_tools(state)
    agent_log.info("ai_tools: %s", tool_data)
    tools = []
    for tool_def in state["needed_tools"]:
        if tool_def.name in tool_data.ai_tools:
            tools.append(tool_data.ai_tools[tool_def.name])
    if len(tools) == 0:
        raise ValueError("No tools found")
    system_prompt = """
# You are data analyst.
Your job is get the requested information using the tools provided.
You must follow all instructions below:
* Use tools available to you.
* Do not make up information.
* If a tool returns an error, return the tool name and the error message
* Return the results in the following JSON format. Do not include markdown or formatting such as ```json:
{{
    "final_result": "string",
    "error": {{
        "tool_name": "string",
        "error_message": "error_message"
    }}
}}"
"""
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ]
    )
    model: BaseChatModel = build_chat_model(temperature=0.5)
    agent = create_tool_calling_agent(model, tools, prompt).with_config(
        {"run_name": "Get Results"}
    )
    agent_executor = AgentExecutor(
        agent=agent, tools=tools, verbose=True  # pyright: ignore [reportArgumentType]
    )
    ret = agent_executor.invoke(
        {
            "chat_history": [],
            "input": state["user_request"],
            "bad_tools": "\n".join(tool_data.bad_tools[:1]),
        }
    )
    output = ret["output"]
    agent_log.info("output: ============\n%s\n===========", output)
    if isinstance(output, str):
        final_result_response = FinalResultResponse.model_validate_json(output)
    else:
        final_result_response = FinalResultResponse.model_validate(output)
    return {
        "call_stack": ["get_results"],
        "final_result": final_result_response,
    }


def ask_human(_: GraphState):
    """Ask human."""
    return {
        "call_stack": ["ask_human"],
        "user_feedback": input("Enter your request: "),
    }


# Define a new graph
workflow = StateGraph(GraphState)

workflow.add_node("setup_sandbox", setup_sandbox)
workflow.add_node("sync_venv", sync_venv)
workflow.add_node("plan_project", plan_project)
workflow.add_node("build_tool", build_tool)
workflow.add_node("review_tools", review_tools)
workflow.add_node("get_results_pre_check", get_results_pre_check)
workflow.add_node("get_results", get_results)
workflow.add_node("format_output", format_output)
workflow.add_node("save_state", save_state)

workflow.add_edge(START, "setup_sandbox")
workflow.add_edge("setup_sandbox", "sync_venv")
workflow.add_edge("sync_venv", "plan_project")
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
    if opts.generate_graph:
        return
    old_state: dict[str, Any] = {}
    if os.path.exists("state.json"):
        with open("state.json", "rt", encoding="utf-8") as state_file:
            old_state = json.load(state_file)

    initial_state: GraphState = {
        "clean_run": opts.clear_sandbox,
        "sandbox_dir": opts.sandbox_dir,
        "dependencies": old_state.get(
            "dependencies",
            [
                "requests",
                "rich",
                "asyncio",
                "langchain",
                "langchain-core",
                "pytest",
                "moto[all]",
            ],
        ),
        "user_request": opts.user_request,
        "needed_tools": [],
        "call_stack": [],
        "final_result": None,
        "user_feedback": "",
    }

    # Use the Runnable
    final_state = app.invoke(
        initial_state,
        config={"configurable": {"thread_id": 42}},
    )
    print(final_state)
