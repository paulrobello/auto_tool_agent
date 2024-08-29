"""Agent system using langgraph."""

from __future__ import annotations

import ast
import logging
import os
import shutil
from typing import Literal, Any, cast
import simplejson as json

from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables.graph import NodeStyles
from langchain_core.language_models import BaseChatModel
from rich import print  # pylint: disable=redefined-builtin
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
import tomlkit
from tomlkit.items import Table, Array

from auto_tool_agent.graph_state import (
    GraphState,
    ToolNeededResponse,
    ToolDescription,
    DependenciesNeededResponse,
    CodeReviewResponse,
)
from auto_tool_agent.lib.execute_command import execute_command
from auto_tool_agent.lib.module_loader import ModuleLoader
from auto_tool_agent.opts import opts
from auto_tool_agent.lib.llm_config import LlmConfig
from auto_tool_agent.lib.llm_providers import (
    get_llm_provider_from_str,
    provider_default_models,
)
from auto_tool_agent.tool_data import tool_data

AGENT_PREFIX = "[green]\\[agent][/green]"

agent_log = logging.getLogger(AGENT_PREFIX)


def load_existing_tools(state: GraphState):
    """Load existing tools."""
    ModuleLoader(os.path.join(state["sandbox_dir"], "src", "sandbox"))
    print(tool_data)


def build_deps_list(state: GraphState) -> list[str]:
    """Build list of all dependencies."""
    needed_tools = state["needed_tools"]
    current_deps = set(state["dependencies"])
    for tool_def in needed_tools:
        current_deps.update(tool_def.dependencies)
    return list(current_deps)


def setup_sandbox(state: GraphState):
    """Entrypoint."""
    sandbox_dir = os.path.expanduser(state["sandbox_dir"]).replace("\\", "/")

    if state["clean_run"] and os.path.exists(sandbox_dir):
        agent_log.info("Removing old sandbox: %s", sandbox_dir)
        shutil.rmtree(sandbox_dir)

    if not os.path.exists(sandbox_dir):
        agent_log.info("Sandbox path not found, creating...")
        os.makedirs(sandbox_dir)

    agent_log.info("Sandbox path: %s", sandbox_dir)
    return {
        "call_stack": ["entrypoint"],
        "sandbox_dir": sandbox_dir,
    }


# pylint: disable=too-many-statements
def sync_venv(state: GraphState):
    """Sync the venv."""
    agent_log.info("Syncing venv...")
    sandbox_dir = state["sandbox_dir"]
    project_config = os.path.join(sandbox_dir, "pyproject.toml")

    if not os.path.exists(project_config):
        agent_log.info("Project config not found, creating...")
        config = {"command": "uv", "params": ["init"], "folder": sandbox_dir}
        result = execute_command(config)
        if result["exit_code"] != 0:
            agent_log.error(result)
            raise ValueError("Failed to create project config.")

        # Update project
        with open(project_config, "rt", encoding="utf-8") as f:
            project_toml = tomlkit.parse(f.read())
        project = cast(Table, project_toml["project"])
        project["description"] = "AI Auto Tool Agent"

        # Add package section
        project["packages"] = cast(Array, tomlkit.array())
        tab = tomlkit.inline_table()
        tab.add("include", "src/")
        project["packages"].insert(0, tab)  # pyright: ignore
        tab = tomlkit.inline_table()
        tab.add("include", "src/**/*.py")
        project["packages"].insert(1, tab)  # pyright: ignore

        with open(project_config, "wt", encoding="utf-8") as f:
            f.write(tomlkit.dumps(project_toml))

    with open(project_config, "rt", encoding="utf-8") as f:
        project_toml = tomlkit.parse(f.read())
    project = cast(Table, project_toml["project"])
    existing_deps = project.get("dependencies") or []
    existing_deps = [
        dep.split(">")[0].split("<")[0].split("=")[0].strip().split("^")[0].strip()
        for dep in existing_deps
    ]
    existing_deps.sort()
    agent_log.info("Existing deps: %s", existing_deps)

    if len(state["dependencies"]) > 0:
        requested_deps = state["dependencies"]
        requested_deps.sort()
        agent_log.info("Requested deps: %s", requested_deps)
        to_install = [dep for dep in requested_deps if dep not in existing_deps]
        if len(to_install) > 0:
            config = {
                "command": "uv",
                "params": ["add"] + to_install,
                "folder": sandbox_dir,
            }
            result = execute_command(config)
            if result["exit_code"] != 0:
                agent_log.error(result)
                raise ValueError("Failed to add dependencies to project config.")
        else:
            agent_log.info("Dependencies already installed.")

        to_remove = [dep for dep in existing_deps if dep not in requested_deps]
        if len(to_remove) > 0:
            agent_log.info("Removing dependencies: %s", to_remove)
            config = {
                "command": "uv",
                "params": ["remove"] + to_remove,
                "folder": sandbox_dir,
            }
            result = execute_command(config)
            if result["exit_code"] != 0:
                agent_log.error(result)
                raise ValueError("Failed to remove dependencies from project config.")

    load_existing_tools(state)

    return {
        "call_stack": ["sync_venv"],
        "sandbox_dir": sandbox_dir,
    }


def sync_deps_if_needed(state: GraphState) -> bool:
    """Sync dependencies if needed."""
    current_deps = set(state["dependencies"])
    needed_deps = set(build_deps_list(state))
    if current_deps != needed_deps:
        sync_venv(state)
        return True
    return False


def get_available_tool_descriptions(state: GraphState):
    """Get available tools."""
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
        result += "Tool_Name: " + tool_desc["file_name"] + "\n"
        result += "Description: " + tool_desc["file"] + "\n\n"

    return result


def plan_project(state: GraphState):
    """Check if a tool is needed."""
    provider = get_llm_provider_from_str(opts.provider)
    llm_config = LlmConfig(
        provider=provider,
        model_name=opts.model_name or provider_default_models[provider],
        temperature=0.5,
    )
    agent_log.info(llm_config)
    available_tools = get_available_tool_descriptions(state)
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
    model: BaseChatModel = llm_config.build_chat_model()
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
    )  # pyright: ignore
    return {
        "call_stack": ["plan_project"],
        "needed_tools": result.needed_tools,
    }


def is_tool_needed(state: GraphState) -> Literal["build_tool", "get_results"]:
    """Check if a tool is needed."""
    # return "save_state"
    needed_tools = state["needed_tools"]
    for tool_def in needed_tools:
        if not tool_def.existing:
            return "build_tool"

    if sync_deps_if_needed(state):
        agent_log.info("Updated dependencies: %s", state["dependencies"])

    return "get_results"


def code_tool(tool_desc: ToolDescription) -> str:
    """Code the tool."""
    agent_log.info("Code tool... %s", tool_desc.name)
    provider = get_llm_provider_from_str(opts.provider)
    llm_config = LlmConfig(
        provider=provider,
        model_name=opts.model_name or provider_default_models[provider],
        temperature=0.5,
    )
    agent_log.info(llm_config)
    model: BaseChatModel = llm_config.build_chat_model()

    system_prompt = """
# You are an expert in Python programming.
Please ensure you follow ALL instructions below:
* Code must be well formatted, have typed arguments and have a doc string in the function body describing it and its arguments.
* If the return type is something other than a string, it should have a return type of Union[str, THE_TYPE].
* Code must use "except Exception as error:" to catch all exceptions and return the error message as a string.
* Tool must be annotated with "@tool" from langchain_core.tools import tool.
* Only output the code. Do not include any other markdown or formatting.
* There should be only one function that has the @tool decorator.
* Do not output markdown tags such as "```" or "```python".
* The user will provide the name and description of the tool.
* You must implement the functionality described in the Tool_Description.
    """
    code_result = model.with_config({"run_name": "Tool Coder"}).invoke(
        [
            ("system", system_prompt),
            (
                "user",
                f"""
Tool_Name: {tool_desc.name}
Tool_Description: {tool_desc.description}
""",
            ),
        ]
    )
    print(code_result.content)

    structure_model = model.with_structured_output(DependenciesNeededResponse)

    system_prompt = """
# You are an expert in programming tools with Python.
* Examine the code and determine if any 3rd party dependencies are needed.
* Return the list of package names.
"""
    deps_result: DependenciesNeededResponse = structure_model.with_config(
        {"run_name": "Dependency Evaluator"}
    ).invoke(
        [
            ("system", system_prompt),
            (
                "user",
                f"""```python
{code_result.content}
```
""",
            ),
        ]
    )  # pyright: ignore
    deps_result.dependencies = [
        dep.replace("_", "-") for dep in deps_result.dependencies
    ]
    deps_result.dependencies.sort()
    tool_desc.dependencies = deps_result.dependencies

    return str(code_result.content)


def build_tool(state: GraphState):
    """Build the tool."""
    needed_tools = state["needed_tools"]
    for tool_def in needed_tools:
        if not tool_def.existing:
            agent_log.info("Building tool... %s", tool_def.name)
            code = code_tool(tool_def)
            tool_path = os.path.join(
                state["sandbox_dir"], "src", "sandbox", tool_def.name + ".py"
            )
            with open(tool_path, "wt", encoding="utf-8") as f:
                f.write(code)
            tool_def.existing = True
            tool_def.needs_review = True
    extra_calls = []
    if sync_deps_if_needed(state):
        agent_log.info("Updated dependencies: %s", state["dependencies"])
        extra_calls.append("sync_venv")
    return {
        "needed_tools": needed_tools,
        "dependencies": state["dependencies"],
        "call_stack": ["build_tool", "sync_deps_if_needed", *extra_calls],
    }


def load_function_code(state: GraphState, tool_name: str) -> str:
    """Load function code."""
    tool_path = os.path.join(state["sandbox_dir"], "src", "sandbox", tool_name + ".py")
    with open(tool_path, "rt", encoding="utf-8") as f:
        return f.read()


def review_tools(state: GraphState):
    """Ensure that the tool is correct."""
    provider = get_llm_provider_from_str(opts.provider)
    llm_config = LlmConfig(
        provider=provider,
        model_name=opts.model_name or provider_default_models[provider],
        temperature=0.25,
    )
    agent_log.info(llm_config)

    system_prompt = """
# You are a Python code review expert.
Your job is to examine a python file and determine if its syntax and logic are correct.
Below are the rules for the code:
* Code must be well formatted, have typed arguments and have a doc string in the function body describing it and its arguments.
* If the return type is something other than a string, it should have a return type of Union[str, THE_TYPE].
* Code must use "except Exception as error:" to catch all exceptions and return the error message as a string.
* Function must be annotated with "@tool" from langchain_core.tools import tool.
* There should be only one function that has the @tool decorator.
* Only update the tool if it is incorrect.
* If you update a tool ensure you follow these instructions:
    * Write it in Python following the above instructions
    * Ensure that it implements the functionality described in the doc string.
    * Only output the code. Do not include any other markdown or formatting.
    * Do not output markdown tags such as "```" or "```python"
"""
    model: BaseChatModel = llm_config.build_chat_model()
    structure_model = model.with_structured_output(CodeReviewResponse)
    any_updated: bool = False
    for tool_def in state["needed_tools"]:
        if tool_def.needs_review:
            tool_def.needs_review = False
            result: CodeReviewResponse = structure_model.with_config(
                {"run_name": "Review Tool"}
            ).invoke(
                [
                    ("system", system_prompt),
                    (
                        "user",
                        f"""
{load_function_code(state, tool_def.name)}
""",
                    ),
                ]
            )  # pyright: ignore
            agent_log.info("Review result: %s", result)
            if result.tool_updated and result.updated_tool_code:
                any_updated = True
                with open(
                    os.path.join(
                        state["sandbox_dir"], "src", "sandbox", tool_def.name + ".py"
                    ),
                    "wt",
                    encoding="utf-8",
                ) as f:
                    f.write(result.updated_tool_code)

    if any_updated:
        load_existing_tools(state)

    return {"call_stack": ["review_tools"], "needed_tools": state["needed_tools"]}


def get_results(state: GraphState):
    """Use tools to get results."""
    provider = get_llm_provider_from_str(opts.provider)
    llm_config = LlmConfig(
        provider=provider,
        model_name=opts.model_name or provider_default_models[provider],
        temperature=0,
    )
    agent_log.info(llm_config)
    agent_log.info(state["needed_tools"])
    load_existing_tools(state)
    agent_log.info(tool_data)
    tools = []
    for tool_def in state["needed_tools"]:
        if tool_def.name in tool_data.ai_tools:
            tools.append(tool_data.ai_tools[tool_def.name])
    if len(tools) == 0:
        raise ValueError("No tools found")
    system_prompt = """
# You are an application architect.
Your job is get the requested information using the tools provided.
You must follow all instructions below:
* Use tools available to you.
* Do not make up information.
"""
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ]
    )
    model: BaseChatModel = llm_config.build_chat_model()
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
    return {
        "call_stack": ["get_results"],
        "final_result": output,
    }


def ask_human(_: GraphState):
    """Ask human."""
    return {
        "call_stack": ["ask_human"],
        "user_feedback": input("Enter your request: "),
    }


def save_state(state: GraphState):
    """Save the state."""
    with open("state.json", "wt", encoding="utf-8") as f:
        json.dump(state, f, indent=2, default=str)
    with open("final_result.md", "wt", encoding="utf-8") as f:
        f.write(state["final_result"])
    return {"call_stack": ["save_state"]}


# Define a new graph
workflow = StateGraph(GraphState)

workflow.add_node("setup_sandbox", setup_sandbox)
workflow.add_node("sync_venv", sync_venv)
workflow.add_node("plan_project", plan_project)
workflow.add_node("build_tool", build_tool)
workflow.add_node("review_tools", review_tools)
workflow.add_node("get_results", get_results)
workflow.add_node("ask_human", ask_human)
workflow.add_node("save_state", save_state)

workflow.add_edge(START, "setup_sandbox")
workflow.add_edge("setup_sandbox", "sync_venv")
workflow.add_edge("sync_venv", "plan_project")
workflow.add_conditional_edges("plan_project", is_tool_needed)
workflow.add_edge("build_tool", "review_tools")
workflow.add_edge("review_tools", "get_results")
workflow.add_edge("get_results", "ask_human")
workflow.add_edge("ask_human", "save_state")
workflow.add_edge("save_state", END)


# Initialize memory to persist state between graph runs
checkpointer = MemorySaver()

# Finally, we compile it!
# This compiles it into a LangChain Runnable,
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
    old_state: dict[str, Any] = {}
    if os.path.exists("state.json"):
        with open("state.json", "rt", encoding="utf-8") as state_file:
            old_state = json.load(state_file)

    # Use the Runnable
    final_state = app.invoke(
        {
            "clean_run": False,
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
            "final_result": "",
            "user_feedback": "",
        },
        config={"configurable": {"thread_id": 42}},
    )
    print(final_state)
