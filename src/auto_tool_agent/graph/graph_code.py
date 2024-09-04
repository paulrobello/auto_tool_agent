"""Code related nodes for graph agent."""

from __future__ import annotations

from pathlib import Path

from git import Repo

from langchain_core.language_models import BaseChatModel

from auto_tool_agent.graph.graph_sandbox import sync_venv
from auto_tool_agent.graph.graph_shared import (
    build_chat_model,
    save_state,
    load_existing_tools,
    git_actor,
    UserAbortError,
)
from auto_tool_agent.app_logging import agent_log, console
from auto_tool_agent.graph.graph_state import (
    GraphState,
    ToolDescription,
    DependenciesNeededResponse,
    CodeReviewResponse,
)
from auto_tool_agent.lib.output_utils import format_diff
from auto_tool_agent.lib.session import session
from auto_tool_agent.opts import opts
from auto_tool_agent.tool_data import tool_data
from auto_tool_agent.tui.code_review import CodeReviewApp

# * If a tools results are a list it should enable limiting the number of results by having a parameter named "limit" of type "Optional[int]" and it should default to None meaning no limit.
CODE_RULES = """
* Code must be well formatted, have typed arguments and have a doc string in the function body describing it and its arguments.
* A tools return type should be "Tuple[Optional[str], RESULT_TYPE]".
* Code must use "except Exception as error:" and return the error message as the first element.
* Tool must be annotated with "@tool" from langchain_core.tools import tool.
* There should be only one function that has a @tool decorator.
* Tools should be reusable by adding parameters to configure the tool.
* Do not output markdown tags such as "```" or "```python".
"""


def code_tool(tool_desc: ToolDescription) -> None:
    """Code the tool."""
    console.log(f"[bold green]Creating tool: [bold yellow]{tool_desc.name}")
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
    tool_desc.code = str(code_result.content)
    if opts.verbose > 1:
        console.log("Tool code:", code_result.content)

    console.log(
        f"[bold green]Evaluating dependencies for tool: [bold yellow]{tool_desc.name}"
    )
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


def load_function_code(state: GraphState, tool_name: str) -> str:
    """Load function code."""
    tool_path = Path(state["sandbox_dir"]) / "src" / "sandbox" / (tool_name + ".py")
    return tool_path.read_text(encoding="utf-8")


# pylint: disable=too-many-branches,too-many-statements
def review_tools(state: GraphState):
    """Ensure that the tool is correct."""
    repo = Repo(state["sandbox_dir"])

    system_prompt = f"""
# You are a Python code review expert.
Your job is to examine a python file and determine if its syntax and logic are correct.
Below are the rules for the code:
{CODE_RULES}
* Only update the tool if it is incorrect.
* If you update a tool ensure you follow these instructions:
    * Write it in Python following the above rules for code.
    * Ensure that it implements the functionality described in the doc string.
    * Do not output markdown tags such as "```" or "```python"
"""
    model: BaseChatModel = build_chat_model(temperature=0.25)
    structure_model = model.with_structured_output(CodeReviewResponse)
    any_updated: bool = False
    for tool_def in state["needed_tools"]:
        if tool_def.needs_review:
            tool_def.existing = True
            tool_def.format_code()

            if opts.interactive:
                user_review = CodeReviewApp(tool_def).run()
                tool_def.format_code()

                if user_review == "Accept":
                    any_updated = True
                elif user_review == "Reject":
                    continue
                elif user_review == "Abort":
                    raise UserAbortError("Aborted review")
                if not tool_def.needs_review:
                    continue
            console.log(f"[bold green]Reviewing tool: [bold yellow]{tool_def.name}")

            tool_def.needs_review = False
            error_msg = ""
            if tool_def.name in tool_data.bad_tools:
                error_msg = (
                    "\n"
                    + "=" * 50
                    + "\nThe tool had the following exception:\n"
                    + str(tool_data.bad_tools[tool_def.name])
                )

            result: CodeReviewResponse = structure_model.with_config(
                {"run_name": "Review Tool"}
            ).invoke(
                [
                    ("system", system_prompt),
                    (
                        "user",
                        f"""
{tool_def.code}
{error_msg}
""",
                    ),
                ]
            )  # type: ignore

            if result.tool_updated and result.updated_tool_code:
                console.log(
                    f"[bold red]Tool review did not pass: [bold yellow]{tool_def.name}"
                )
                console.log(f"[bold red]{result.tool_issues}")

                any_updated = True

                tool_def.needs_review = True
                tool_def.code = result.updated_tool_code
                tool_def.save()

                diff = format_diff(repo, tool_def.tool_path)
                console.log(diff)
                repo.index.add([tool_def.tool_path, tool_def.metadata_path])

                if opts.interactive:
                    user_review = CodeReviewApp(tool_def, result, diff).run()
                    if user_review == "Accept":
                        any_updated = True
                    elif user_review == "Reject":
                        continue
                    elif user_review == "Abort":
                        raise UserAbortError("Aborted review")

                repo.index.commit(
                    f"Session: {session.id} - Revised Tool: {tool_def.name}\n{result.tool_issues}",
                    author=git_actor,
                    committer=git_actor,
                )
                console.log(f"[bold green]Tool corrected: [bold yellow]{tool_def.name}")
            else:
                console.log(
                    f"[bold green]Tool review passed: [bold yellow]{tool_def.name}"
                )

    if any_updated:
        load_existing_tools()
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
        console.log("[bold green]Dependencies changed...")
        state["dependencies"] = list(needed_deps)
        sync_venv(state["dependencies"])
        return True
    return False


def build_tool(state: GraphState):
    """Build the tool."""
    repo = Repo(state["sandbox_dir"])

    needed_tools = state["needed_tools"]
    for tool_def in needed_tools:
        if not tool_def.existing:
            if opts.verbose > 1:
                agent_log.info("Building tool... %s", tool_def.name)
            code_tool(tool_def)
            tool_def.existing = True
            tool_def.needs_review = True
            tool_def.save()
            repo.index.add([tool_def.tool_path, tool_def.metadata_path])
            repo.index.commit(
                f"Session: {session.id} - New Tool: {tool_def.name}",
                author=git_actor,
                committer=git_actor,
            )
    extra_calls = []
    if sync_deps_if_needed(state):
        if opts.verbose > 1:
            agent_log.info("Updated dependencies: %s", state["dependencies"])
        extra_calls.append("sync_venv")
    save_state(state)

    return {
        "needed_tools": needed_tools,
        "dependencies": state["dependencies"],
        "call_stack": ["build_tool", "sync_deps_if_needed", *extra_calls],
    }
