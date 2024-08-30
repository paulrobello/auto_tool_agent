"""Code related nodes for graph agent."""

from __future__ import annotations

import os

from langchain_core.language_models import BaseChatModel
from rich import print  # pylint: disable=redefined-builtin

from auto_tool_agent.graph.graph_sandbox import sync_venv
from auto_tool_agent.graph.graph_shared import (
    agent_log,
    build_chat_model,
    save_state,
    load_existing_tools,
)
from auto_tool_agent.graph.graph_state import (
    GraphState,
    ToolDescription,
    DependenciesNeededResponse,
    CodeReviewResponse,
)

CODE_RULES = """
* Code must be well formatted, have typed arguments and have a doc string in the function body describing it and its arguments.
* If the return type is something other than a string, it should have a return type of Union[str, THE_TYPE].
* Code must use "except Exception as error:" to catch all exceptions and return the error message as a string.
* Tool must be annotated with "@tool" from langchain_core.tools import tool.
* There should be only one function that has the @tool decorator.
* Functions should be reusable by adding parameters to enable filtering or limiting the number of results.
* Result limit parameters should default to None meaning no limit.
* Do not output markdown tags such as "```" or "```python".
"""


def code_tool(tool_desc: ToolDescription) -> str:
    """Code the tool."""
    agent_log.info("Code tool... %s", tool_desc.name)
    model = build_chat_model()

    system_prompt = f"""
# You are an expert in Python programming.
Please ensure you follow ALL instructions below:
{CODE_RULES}
* Only output the code. Do not include any other markdown or formatting.
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


def load_function_code(state: GraphState, tool_name: str) -> str:
    """Load function code."""
    tool_path = os.path.join(state["sandbox_dir"], "src", "sandbox", tool_name + ".py")
    with open(tool_path, "rt", encoding="utf-8") as f:
        return f.read()


def review_tools(state: GraphState):
    """Ensure that the tool is correct."""

    system_prompt = f"""
# You are a Python code review expert.
Your job is to examine a python file and determine if its syntax and logic are correct.
Below are the rules for the code:
{CODE_RULES}
* Only update the tool if it is incorrect.
* If you update a tool ensure you follow these instructions:
    * Write it in Python following the above rules for code.
    * Ensure that it implements the functionality described in the doc string.
    * Only output the code. Do not include any other markdown or formatting.
    * Do not output markdown tags such as "```" or "```python"
"""
    model: BaseChatModel = build_chat_model(temperature=0.25)
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
            )  # type: ignore
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
    save_state(state)
    return {"call_stack": ["review_tools"], "needed_tools": state["needed_tools"]}


def build_deps_list(state: GraphState) -> list[str]:
    """Build list of all 3rd party package dependencies."""
    needed_tools = state["needed_tools"]
    current_deps = set(state["dependencies"])
    for tool_def in needed_tools:
        current_deps.update(tool_def.dependencies)
    return list(current_deps)


def sync_deps_if_needed(state: GraphState) -> bool:
    """Sync dependencies if needed."""
    current_deps = set(state["dependencies"])
    needed_deps = set(build_deps_list(state))
    if current_deps != needed_deps:
        sync_venv(state)
        return True
    return False


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
    save_state(state)
    return {
        "needed_tools": needed_tools,
        "dependencies": state["dependencies"],
        "call_stack": ["build_tool", "sync_deps_if_needed", *extra_calls],
    }
