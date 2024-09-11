"""Agent node to get results using tools."""

from __future__ import annotations

from typing import Literal
import simplejson as json

from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from auto_tool_agent.app_logging import console, agent_log, global_vars
from auto_tool_agent.graph.graph_code import sync_deps_if_needed
from auto_tool_agent.graph.graph_shared import (
    load_existing_tools,
    build_chat_model,
    commit_leftover_changes,
    AgentAbortError,
)
from auto_tool_agent.graph.graph_state import (
    GraphState,
    FinalResultResponse,
)
from auto_tool_agent.opts import opts
from auto_tool_agent.tool_data import tool_data


def is_tool_needed(
    state: GraphState,
) -> Literal["build_tool", "review_tools", "get_results_pre_check"]:
    """Check if a tool is needed."""
    # return "save_state"
    needed_tools = state["needed_tools"]
    for tool_def in needed_tools:
        if not tool_def.existing:
            console.log(
                f"[bold green]New tool needed: [bold yellow]{tool_def.name}. [/bold yellow]Building tool..."
            )
            return "build_tool"
        if tool_def.needs_review:
            console.log(
                f"[bold green]Tool review needed: [bold yellow]{tool_def.name}. [/bold yellow]Reviewing tool..."
            )
            return "review_tools"

    if sync_deps_if_needed(state):
        if opts.verbose > 1:
            agent_log.info("Updated dependencies: %s", state["dependencies"])

    return "get_results_pre_check"


def get_results_pre_check(state: GraphState):
    """Check if a tool is needed."""
    global_vars.status_update("Get results pre check...")
    console.log(
        f"[bold green]Ensuring needed tools are available: [bold yellow]{[tool.name for tool in state['needed_tools']]}"
    )
    sync_deps_if_needed(state)
    return {
        "call_stack": ["get_results_pre_check"],
        "dependencies": state["dependencies"],
    }


def has_needed_tools(
    state: GraphState,
) -> Literal["plan_project", "get_results", "review_tools"]:
    """Check if a tool is needed."""
    load_existing_tools()
    needed_tools = state["needed_tools"]
    for tool_def in needed_tools:
        if tool_def.needs_review:
            console.log(
                f"[bold green]Tool needs review: [bold yellow]{tool_def.name}. [/bold yellow]Reviewing..."
            )
            return "review_tools"
    for tool_def in needed_tools:
        if tool_def.name not in tool_data.ai_tools:
            console.log(
                f"[bold red]Missing tool: [bold yellow]{tool_def.name}. [/bold yellow]Returning to planner..."
            )
            return "plan_project"

    return "get_results"


def check_results(
    state: GraphState,
) -> Literal["review_tools", "format_output", "save_state"]:
    """Check if results contain errors that need review."""
    final_result = state["final_result"]
    if not final_result:
        raise AgentAbortError("Aborted check_results due to empty final_result")

    if final_result.error:
        if final_result.error.error_classifier == "authentication":
            console.log("[bold red]Authentication error. Exiting...")
            return "save_state"
        console.log(
            f"[bold red]Error returned from tool: [bold yellow]{final_result.error.tool_name}. [/bold yellow]Reviewing..."
        )
        return "review_tools"
    return "format_output"


def get_results(state: GraphState):
    """Use tools to get results."""
    global_vars.status_update("Getting results...")

    commit_leftover_changes(state["sandbox_dir"], f"Request: {state['user_request']}")
    if opts.verbose > 1:
        console.log("needed_tools:", [tool.name for tool in state["needed_tools"]])
        console.log("ai_tools:", [tool.name for tool in tool_data.ai_tools.values()])
    tools = []
    for tool_def in state["needed_tools"]:
        if tool_def.name in tool_data.ai_tools:
            tools.append(tool_data.ai_tools[tool_def.name])
        else:
            raise ValueError(f"Missing tool: {tool_def.name}")

    system_prompt = """
ROLE: You are data analyst.

TASK: Get the requested information using the tools provided.

INSTRUCTIONS:
* Use tools available to you.
* Return all information provided by the tools unless asked otherwise.
* Do not make up information.
* If a tool returns an error, *ONLY* return the `tool_name`, `error_message`, `needs_review` and `error_classifier`.
* Only set `needs_review` to True if error is not related to authentication, profile or token.
* Ensure you classify errors as one of `authentication`, `syntax`, `parameter`, `parsing`.
* Do not include a preamble, apology or markdown formatting such as ```json
* Results *MUST* be in the following JSON format:
{{
    "final_result": "string",
    "next_step": "string",
    "error": {{
        "tool_name": "string",
        "error_message": "error_message",
        "needs_review": bool,
        error_classifier: Literal["authentication", "syntax", "parameter", "parsing"]
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
        agent=agent,
        tools=tools,
        verbose=False,
        handle_parsing_errors=False,
        return_intermediate_steps=False,  # pyright: ignore [reportArgumentType]
    )
    ret = agent_executor.invoke({"chat_history": [], "input": state["user_request"]})
    # console.print("= RES =" * 10)
    # console.print(ret)
    ret = ret["output"]
    if isinstance(ret, list):
        ret = ret[0]
    if isinstance(ret, dict) and "text" in ret:
        ret = ret["text"]
    if isinstance(ret, str):
        try:
            final_result_response = FinalResultResponse(**json.loads(ret))
            if final_result_response.error:
                tool_name = (
                    final_result_response.error.tool_name  # pylint: disable=no-member
                )
                for tool_def in state["needed_tools"]:
                    if tool_def.name == tool_name:
                        tool_def.needs_review = True
                        tool_data.bad_tools[tool_name] = (
                            final_result_response.error.error_message  # pylint: disable=no-member
                        )

            return {
                "call_stack": ["get_results"],
                "final_result": final_result_response,
                "needed_tools": state["needed_tools"],
            }
        except Exception as _:  # pylint: disable=broad-except
            pass
            # console.print(f"Error parsing JSON: {e}")

    structure_model = build_chat_model(temperature=0).with_structured_output(
        FinalResultResponse
    )

    chat_history = [
        (
            "system",
            """
        ROLE: You are a data analyst.
        TASK: Get results and errors from the JSON portion of the user message and call tool PlanProjectResponse
        """,
        ),
        ("user", ret),
    ]
    final_result_response: FinalResultResponse = structure_model.with_config(
        {"run_name": "Results output formatter"}
    ).invoke(
        chat_history
    )  # type: ignore
    # console.print("= RES FMT =" * 10)
    # console.print(final_result_response)
    # for step in ret["intermediate_steps"]:
    #     (tool, tool_return) = step
    #     console.print(f"[bold green]Tool: {tool.tool}[/bold green]\n", tool_return)
    return {
        "call_stack": ["get_results"],
        "final_result": final_result_response,
        "needed_tools": state["needed_tools"],
    }
