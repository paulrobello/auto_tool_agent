"""Agent system using langgraph."""

from __future__ import annotations

import logging
import os
from typing import Literal, List
from rich import print  # pylint: disable=redefined-builtin

from langchain_core.tools import tool
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph, MessagesState
from langgraph.prebuilt import ToolNode
from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel
from tomlkit import parse as parse_toml

from auto_tool_agent.graph_state import GraphState, ToolNeededResponse, ToolDescription
from auto_tool_agent.lib.execute_command import execute_command
from auto_tool_agent.opts import opts
from auto_tool_agent.lib.llm_config import LlmConfig
from auto_tool_agent.lib.llm_providers import (
    get_llm_provider_from_str,
    provider_default_models,
)

AGENT_PREFIX = "[green]\\[agent][/green]"

agent_log = logging.getLogger(AGENT_PREFIX)


def entrypoint(state: GraphState):
    """Entrypoint."""
    sandbox_dir = state["sandbox_dir"]
    if not os.path.exists(sandbox_dir):
        agent_log.info("Sandbox path not found, creating...")
        os.makedirs(sandbox_dir)

    agent_log.info("Sandbox path: %s", sandbox_dir)
    return {
        "call_stack": ["entrypoint"],
        "sandbox_dir": sandbox_dir,
    }


def sync_venv(state: GraphState):
    """Sync the venv."""
    agent_log.info("Syncing venv...")
    sandbox_dir = os.path.expanduser(state["sandbox_dir"])
    project_config = os.path.join(sandbox_dir, "pyproject.toml")
    existing_deps = []
    if not os.path.exists(project_config):
        agent_log.info("Project config not found, creating...")
        config = {"command": "uv", "params": ["init"], "folder": sandbox_dir}
        result = execute_command(config)
        if result["exit_code"] != 0:
            agent_log.info(result)
            raise ValueError("Failed to create project config.")
    else:
        with open(project_config, "rt", encoding="utf-8") as f:
            project_toml = parse_toml(f.read())
        existing_deps = project_toml["project"].get("dependencies") or []
        existing_deps = [
            dep.split(">")[0].split("<")[0].split("=")[0].split("[")[0].strip()
            for dep in existing_deps
        ]
        existing_deps.sort()
        agent_log.info(f"Existing deps: %s", existing_deps)

    if len(state["dependencies"]) > 0:
        requested_deps = state["dependencies"]
        requested_deps.sort()
        agent_log.info(f"Requested deps: %s", requested_deps)
        to_install = [dep for dep in requested_deps if dep not in existing_deps]
        if len(to_install) > 0:
            config = {
                "command": "uv",
                "params": ["add"] + to_install,
                "folder": sandbox_dir,
            }
            result = execute_command(config)
            if result["exit_code"] != 0:
                agent_log.info(result)
                raise ValueError("Failed to add dependencies to project config.")
        else:
            agent_log.info("Dependencies already installed.")

        to_remove = [dep for dep in existing_deps if dep not in requested_deps]
        if len(to_remove) > 0:
            config = {
                "command": "uv",
                "params": ["remove"] + to_remove,
                "folder": sandbox_dir,
            }
            result = execute_command(config)
            if result["exit_code"] != 0:
                agent_log.info(result)
                raise ValueError("Failed to remove dependencies from project config.")
    return {
        "call_stack": ["sync_venv"],
        "sandbox_dir": sandbox_dir,
    }


def plan_project(state: GraphState):
    """Check if a tool is needed."""
    provider = get_llm_provider_from_str(opts.provider)
    llm_config = LlmConfig(
        provider=provider,
        model_name=opts.model_name or provider_default_models[provider],
        temperature=0.1,
    )
    agent_log.info(llm_config)
    system_prompt = """
# You are an application architect.
You job is to examine the users request and determine what tools will be needed.
Examine the list of available tools and if they are relevant to the users request include them in the needed_tools list and set existing to True.
Do not call the tools only examine if the existing tools are needed to fulfill the users request.
If additional tools are needed give them a name consisting only of letters and underscores and detailed description and include them in the needed_tools list and set existing to False.
    """
    model: BaseChatModel = llm_config.build_chat_model()
    structure_model = model.with_structured_output(ToolNeededResponse)
    result = structure_model.invoke(
        [
            ("system", system_prompt),
            ("user", state["user_request"]),
        ]
    )
    return {
        "call_stack": ["plan_project"],
        "needed_tools": result.needed_tools,
    }


def is_tool_needed(state: GraphState) -> Literal["build_tool", END]:
    """Check if a tool is needed."""
    needed_tools = state["needed_tools"]
    for tool in needed_tools:
        if not tool.existing:
            return "build_tool"
    return END


def code_tool(tool_desc: ToolDescription) -> str:
    """Code the tool."""
    agent_log.info("Code tool... %s", tool_desc.name)
    provider = get_llm_provider_from_str(opts.provider)
    llm_config = LlmConfig(
        provider=provider,
        model_name=opts.model_name or provider_default_models[provider],
        temperature=0.1,
    )
    agent_log.info(llm_config)
    model: BaseChatModel = llm_config.build_chat_model()

    system_prompt = """
# You are an expert in programming tools with Python.
You must follow all instructions below:
* Code should be well formatted, have typed arguments and have a doc string in the function body describing it and its arguments.
* Must use "catch Exception as error" to catch all exceptions and return an error message as a string.
* Must be annotated with "@tool" from langchain_core.tools import tool.
* Only output the code. Do not include any other text / markdown or formatting.
* Do not output ```python
The user will provide the name and description of the tool.
    """
    result = model.invoke(
        [
            ("system", system_prompt),
            (
                "user",
                f"""
Tool Name: {tool_desc.name}
Tool Description: {tool_desc.description}
""",
            ),
        ]
    )
    print(result.content)
    return str(result.content)


def build_tool(state: GraphState):
    """Build the tool."""
    needed_tools = state["needed_tools"]
    for tool in needed_tools:
        if not tool.existing:
            agent_log.info("Building tool... %s", tool.name)
            code = code_tool(tool)
            tool_path = os.path.join(
                state["sandbox_dir"], "src", "sandbox", tool.name + ".py"
            )
            open(tool_path, "wt", encoding="utf-8").write(code)
            tool.existing = True
    return {
        "call_stack": ["build_tool"],
    }


#
# tools = [search]
#
# tool_node = ToolNode(tools)
#
# provider = get_llm_provider_from_str(opts.provider)
# llm_config = LlmConfig(
#     provider=provider,
#     model_name=opts.model_name or provider_default_models[provider],
#     temperature=0.1,
# )
# agent_log.info(llm_config)
# model = llm_config.build_chat_model()
#
#
# # Define the function that determines whether to continue or not
# def should_continue(state: MessagesState) -> Literal["tools", END]:
#     """Determine whether to continue or not."""
#     messages = state["messages"]
#     last_message = messages[-1]
#     # If the LLM makes a tool call, then we route to the "tools" node
#     if last_message.tool_calls:
#         return "tools"
#     # Otherwise, we stop (reply to the user)
#     return END
#
#
# # Define the function that calls the model
# def call_model(state: MessagesState):
#     """Call the model."""
#     messages = state["messages"]
#     response = model.bind_tools(tools).invoke(messages)
#     # We return a list, because this will get added to the existing list
#     return {"messages": [response]}


# Define a new graph
workflow = StateGraph(GraphState)
# workflow = StateGraph(MessagesState)

workflow.add_node("entrypoint", entrypoint)
workflow.add_node("sync_venv", sync_venv)
workflow.add_node("plan_project", plan_project)
workflow.add_node("build_tool", build_tool)

# workflow.add_node("agent", call_model)
# workflow.add_node("tools", tool_node)

# Set the entrypoint as `agent`
# This means that this node is the first one called
workflow.add_edge(START, "entrypoint")
workflow.add_edge("entrypoint", "sync_venv")
workflow.add_edge("sync_venv", "plan_project")
workflow.add_conditional_edges("plan_project", is_tool_needed)
workflow.add_conditional_edges("build_tool", is_tool_needed)


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
            # "sandbox_dir": "~/.config/auto_tool_agent/sandbox",
            "sandbox_dir": opts.sandbox_dir,
            "dependencies": ["requests", "rich", "asyncio"],
            "user_request": opts.user_request,
            "needed_tools": [],
        },
        config={"configurable": {"thread_id": 42}},
    )
    # print(final_state["messages"][-1].content)
    print(final_state)
