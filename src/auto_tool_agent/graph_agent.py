"""Agent system using langgraph."""

from __future__ import annotations

import logging
import os
from typing import Annotated, Literal, TypedDict
from rich import print  # pylint: disable=redefined-builtin

from langchain_core.messages import HumanMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph, MessagesState
from langgraph.prebuilt import ToolNode

from tomlkit import parse as parse_toml

from auto_tool_agent.lib.execute_command import execute_command
from auto_tool_agent.opts import opts
from auto_tool_agent.lib.llm_config import LlmConfig
from auto_tool_agent.lib.llm_providers import (
    get_llm_provider_from_str,
    provider_default_models,
)

AGENT_PREFIX = "[green]\\[agent][/green]"

agent_log = logging.getLogger(AGENT_PREFIX)


@tool
def search(query: str) -> str:
    """Call to surf the web."""
    # This is a placeholder, but don't tell the LLM that...
    if "sf" in query.lower() or "san francisco" in query.lower():
        return "It's 60 degrees and foggy."
    return "It's 90 degrees and sunny."


def entrypoint(state: GraphState):
    """Entrypoint."""
    sandbox_path = os.path.join(
        os.path.abspath(os.path.dirname(__file__)), state["sandbox_path"]
    )
    if not os.path.exists(sandbox_path):
        print("Sandbox path not found, creating...")
        os.makedirs(sandbox_path)

    print("Sandbox path: ", sandbox_path)
    return {
        "call_stack": ["entrypoint"],
        "sandbox_path": sandbox_path,
    }


def sync_venv(state: GraphState):
    """Sync the venv."""
    print("Syncing venv...")
    sandbox_path = state["sandbox_path"]
    project_config = os.path.join(sandbox_path, "pyproject.toml")
    if not os.path.exists(project_config):
        print("Project config not found, creating...")
        config = {"command": "uv", "params": ["init"], "folder": sandbox_path}
        result = execute_command(config)
        if result["exit_code"] != 0:
            print(result)
            raise ValueError("Failed to create project config.")
    else:
        with open(project_config, "rt", encoding="utf-8") as f:
            project_toml = parse_toml(f.read())
        existing_deps = project_toml["project"]["dependencies"]
        existing_deps = [
            dep.split(">")[0].split("<")[0].split("=")[0].split("[")[0].strip()
            for dep in existing_deps
        ]
        existing_deps.sort()
        print(f"Existing deps: {existing_deps}")

    if len(state["dependencies"]) > 0:
        requested_deps = state["dependencies"]
        requested_deps.sort()
        print(f"Requested deps: {requested_deps}")
        to_install = [dep for dep in requested_deps if dep not in existing_deps]
        if len(to_install) > 0:
            config = {
                "command": "uv",
                "params": ["add"] + to_install,
                "folder": sandbox_path,
            }
            result = execute_command(config)
            if result["exit_code"] != 0:
                print(result)
                raise ValueError("Failed to add dependencies to project config.")
        else:
            print("Dependencies already installed.")

        to_remove = [dep for dep in existing_deps if dep not in requested_deps]
        if len(to_remove) > 0:
            config = {
                "command": "uv",
                "params": ["remove"] + to_remove,
                "folder": sandbox_path,
            }
            result = execute_command(config)
            if result["exit_code"] != 0:
                print(result)
                raise ValueError("Failed to remove dependencies from project config.")
    return {
        "call_stack": ["sync_venv"],
        "sandbox_path": sandbox_path,
    }


tools = [search]

tool_node = ToolNode(tools)

provider = get_llm_provider_from_str(opts.provider)
llm_config = LlmConfig(
    provider=provider,
    model_name=opts.model_name or provider_default_models[provider],
    temperature=0.1,
)
agent_log.info(llm_config)
model = llm_config.build_chat_model()


# Define the function that determines whether to continue or not
def should_continue(state: MessagesState) -> Literal["tools", END]:
    """Determine whether to continue or not."""
    messages = state["messages"]
    last_message = messages[-1]
    # If the LLM makes a tool call, then we route to the "tools" node
    if last_message.tool_calls:
        return "tools"
    # Otherwise, we stop (reply to the user)
    return END


# Define the function that calls the model
def call_model(state: MessagesState):
    """Call the model."""
    messages = state["messages"]
    response = model.bind_tools(tools).invoke(messages)
    # We return a list, because this will get added to the existing list
    return {"messages": [response]}


def add_node_call(left: list[str], right: list[str]) -> list[str]:
    """Add a node call."""
    return left + right


class GraphState(TypedDict):
    """Graph state."""

    call_stack: Annotated[list[str], add_node_call]
    sandbox_path: str
    dependencies: list[str]


# Define a new graph
workflow = StateGraph(GraphState)
# workflow = StateGraph(MessagesState)

workflow.add_node("entrypoint", entrypoint)
workflow.add_node("sync_venv", sync_venv)
# workflow.add_node("agent", call_model)
# workflow.add_node("tools", tool_node)

# Set the entrypoint as `agent`
# This means that this node is the first one called
workflow.add_edge(START, "entrypoint")
workflow.add_edge("entrypoint", "sync_venv")
workflow.add_edge("sync_venv", END)

# workflow.add_edge("sync_venv", "agent")

# We now add a conditional edge
# workflow.add_conditional_edges(
#     # First, we define the start node. We use `agent`.
#     # This means these are the edges taken after the `agent` node is called.
#     "agent",
#     # Next, we pass in the function that will determine which node is called next.
#     should_continue,
# )
#
# # We now add a normal edge from `tools` to `agent`.
# # This means that after `tools` is called, `agent` node is called next.
# workflow.add_edge("tools", "agent")

# Initialize memory to persist state between graph runs
checkpointer = MemorySaver()

# Finally, we compile it!
# This compiles it into a LangChain Runnable,
# meaning you can use it as you would any other runnable.
# Note that we're (optionally) passing the memory when compiling the graph
app = workflow.compile(checkpointer=checkpointer)


def run_graph():
    """Run the graph."""
    # Use the Runnable
    final_state = app.invoke(
        # {"messages": [HumanMessage(content="what is the weather in sf")]},
        {
            "sandbox_path": "sandbox",
            "dependencies": ["requests", "rich", "asyncio"],
        },
        config={"configurable": {"thread_id": 42}},
    )
    # print(final_state["messages"][-1].content)
    print(final_state)
