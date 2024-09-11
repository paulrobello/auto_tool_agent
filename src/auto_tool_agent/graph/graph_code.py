"""Code related nodes for graph agent."""

from __future__ import annotations

from pathlib import Path

from git import Repo

from langchain_core.language_models import BaseChatModel

from auto_tool_agent.graph.graph_sandbox import sync_venv
from auto_tool_agent.graph.graph_shared import (
    build_chat_model,
    save_state,
    git_actor,
    UserAbortError,
    commit_leftover_changes,
    AgentAbortError,
)
from auto_tool_agent.app_logging import agent_log, console, global_vars
from auto_tool_agent.graph.graph_state import (
    GraphState,
    ToolDescription,
    DependenciesNeededResponse,
    CodeReviewResponse,
    PlanProjectResponse,
)
from auto_tool_agent.lib.output_utils import format_diff
from auto_tool_agent.lib.session import session
from auto_tool_agent.opts import opts
from auto_tool_agent.tool_data import tool_data
from auto_tool_agent.tui.code_review import CodeReviewApp

CODE_RULES = """
1. Function Structure:
   - Use well-formatted Python code with typed arguments.
   - Include a docstring in the function body describing the function and its arguments.
   - Annotate the main function with "@tool" from langchain_core.tools import tool.
   - Only one function should have the @tool decorator.

2. Return Type:
   - Use "Tuple[Optional[str], RESULT_TYPE]" as the return type.
   - The first element should be an error message (if any), the second the actual result.

3. Error Handling:
   - Use "except Exception as error:" for catching exceptions.
   - Return the error message as the first element of the tuple.

4. Tool Design:
   - Make tools reusable by adding configurable parameters.
   - If a tool's results are a list, include an optional "limit" parameter:
     - Use "limit: Optional[int] = None" in the function signature.
     - When None, it means no limit.
   - If the "requests" module is used ensure a timeout of 10 seconds is set.

5. Code Output:
   - Do not include any markdown formatting (e.g., ``` or ```python).
   - Output only the Python code for the tool.
"""


def evaluate_dependencies(tool_desc: ToolDescription) -> None:
    """Evaluate dependencies."""
    global_vars.status_update(
        f"[bold green]Evaluating dependencies for tool: [bold yellow]{tool_desc.name}"
    )
    model = build_chat_model()

    structure_model = model.with_structured_output(DependenciesNeededResponse)

    system_prompt = """
ROLE: You are an expert in programming with Python.
* Determine the 3rd party dependencies that are needed based on the list of imports provided by the user.
* Return the list of package names. Ensure you transform underscores to hyphens.
"""
    tool_imports = "\n".join(
        line for line in tool_desc.code.split("\n") if "import" in line
    )
    deps_result: DependenciesNeededResponse = structure_model.with_config(
        {"run_name": "Dependency Evaluator"}
    ).invoke(
        [
            ("system", system_prompt),
            (
                "user",
                tool_imports,
            ),
        ]
    )  # pyright: ignore

    deps_result.dependencies.sort()
    tool_desc.dependencies = deps_result.dependencies


def code_tool(tool_desc: ToolDescription, plan: PlanProjectResponse) -> None:
    """Code the tool."""
    global_vars.status_update(f"Building tool: {tool_desc.name}")

    model = build_chat_model()
    structure_model = model.with_structured_output(ToolDescription)

    system_prompt = f"""
ROLE: You are an expert Python programmer.

TASK: Create a Python tool based on the provided name and description.

PROJECT PLAN: {plan.explanation}

INSTRUCTIONS:
1. Follow ALL rules below:
{CODE_RULES}
2. Output ONLY the code. No markdown or additional formatting.
3. Efficiently implement the functionality described in the Tool_Description.
4. Output any 3rd party dependencies that are needed.
IMPORTANT: The user will provide the tool name and description. Your job is to code it precisely as specified.
"""
    code_result: ToolDescription = structure_model.with_config(
        {"run_name": f"Tool Coder {tool_desc.name}"}
    ).invoke(
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
    )  # pyright: ignore
    tool_desc.code = code_result.code
    tool_desc.dependencies = code_result.dependencies
    if opts.verbose > 2:
        console.log("Tool dependencies:", code_result.dependencies)
        console.log("Tool code:", code_result.code)
    # evaluate_dependencies(tool_desc)


def load_function_code(state: GraphState, tool_name: str) -> str:
    """Load function code."""
    tool_path = Path(state["sandbox_dir"]) / "src" / "sandbox" / (tool_name + ".py")
    return tool_path.read_text(encoding="utf-8")


# pylint: disable=too-many-branches,too-many-statements
def review_tools(state: GraphState):
    """Ensure that the tool is correct."""
    global_vars.status_update("Reviewing tools...")
    repo = Repo(state["sandbox_dir"])
    if not state["plan"]:
        raise AgentAbortError("Aborted review due to empty plan")

    system_prompt = f"""
ROLE: You are a Python code review expert.

TASK: Examine the provided Python file and assess its syntax and logic for correctness.

PROJECT PLAN: {state["plan"].explanation}

RULES:
{CODE_RULES}

REVIEW INSTRUCTIONS:
1. ONLY update the tool if it is incorrect or the PROJECT PLAN requests it.
2. If an update is needed:
   a. Write in Python following the above rules.
   b. Ensure it implements the functionality described in the docstring.
   c. DO NOT use markdown tags (e.g., ``` or ```python).

IMPORTANT: Focus on correctness and adherence to the specified functionality. Only suggest changes if absolutely necessary.
"""
    model: BaseChatModel = build_chat_model(temperature=0.25)
    structure_model = model.with_structured_output(CodeReviewResponse)
    for tool_def in state["needed_tools"]:
        if tool_def.needs_review:
            tool_def.format_code()

            user_review = CodeReviewResponse()
            if opts.interactive:
                user_response = CodeReviewApp(tool_def, user_review).run()
                tool_def.format_code()

                if user_response == "Accept":
                    pass
                elif user_response == "Reject":
                    continue
                elif user_response == "Abort":
                    raise UserAbortError("Aborted review")
                if not tool_def.needs_review:
                    continue

            global_vars.status_update(
                f"[bold green]Reviewing tool: [bold yellow]{tool_def.name}"
            )

            tool_def.needs_review = False

            if user_review.tool_issues:
                user_msg = f"The user would also like the following changes or issues addressed:\n{user_review.tool_issues}\n\n"
            else:
                user_msg = ""

            error_msg = ""
            if tool_def.name in tool_data.bad_tools:
                error_msg = (
                    "\n"
                    + "=" * 50
                    + "\nThe tool had the following exception:\n"
                    + str(tool_data.bad_tools[tool_def.name])
                )

            result: CodeReviewResponse = structure_model.with_config(
                {"run_name": f"Review Tool {tool_def.name}"}
            ).invoke(
                [
                    ("system", system_prompt),
                    (
                        "user",
                        f"""
{tool_def.code}
{error_msg}
{user_msg}
""",
                    ),
                ]
            )  # type: ignore
            if not result:
                raise AgentAbortError("Aborted review due to empty response")
            if result.tool_updated and result.updated_tool_code:
                console.log(
                    f"[bold red]Tool review did not pass: [bold yellow]{tool_def.name}"
                )
                console.log(f"[bold red]{result.tool_issues}")
                evaluate_dependencies(tool_def)

                tool_def.needs_review = True
                tool_def.code = result.updated_tool_code
                tool_def.save()

                diff = format_diff(repo, tool_def.tool_path)
                console.log(diff)
                repo.index.add([tool_def.tool_path, tool_def.metadata_path])

                if opts.interactive:
                    user_response = CodeReviewApp(tool_def, result, diff).run()
                    if user_response == "Accept":
                        pass
                    elif user_response == "Reject":
                        continue
                    elif user_response == "Abort":
                        raise UserAbortError("Aborted review")
                commit_leftover_changes(
                    state["sandbox_dir"],
                    f"Revised Tool: {tool_def.name}\n{result.tool_issues}",
                )
                console.log(f"[bold green]Tool corrected: [bold yellow]{tool_def.name}")
            else:
                console.log(
                    f"[bold green]Tool review passed: [bold yellow]{tool_def.name}"
                )

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
    global_vars.status_update("Building tools...")

    if not state["plan"]:
        raise AgentAbortError("Aborted tool build due to empty plan")

    repo = Repo(state["sandbox_dir"])

    needed_tools = state["needed_tools"]
    for tool_def in needed_tools:
        if not tool_def.existing:
            code_tool(tool_def, state["plan"])
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
