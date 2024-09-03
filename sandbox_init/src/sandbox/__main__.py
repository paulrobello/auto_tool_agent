"""Agent system using langgraph."""

from __future__ import annotations

from pathlib import Path

from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.language_models import BaseChatModel
from langgraph.checkpoint.memory import MemorySaver
from langgraph.constants import END
from langgraph.graph import StateGraph
from rich.markdown import Markdown

from sandbox.graph_state import GraphState, FinalResultResponse, ToolDescription
from sandbox.lib.output_utils import highlight_json, csv_to_table
from sandbox.opts import console, opts
from sandbox.graph_shared import build_chat_model, load_existing_tools, UserAbortError
from sandbox.session import session
from sandbox.tool_data import tool_data


# Define the nodes
def get_results(state: GraphState):
    """Use tools to get results."""
    console.log("[bold green]Getting results...")
    console.log("needed_tools:", state["needed_tools"])
    console.log("ai_tools:", tool_data)
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
* Return all information provided by the tools unless asked otherwise.
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
        agent=agent,
        tools=tools,
        verbose=False,
        return_intermediate_steps=True,  # pyright: ignore [reportArgumentType]
    )
    ret = agent_executor.invoke(
        {
            "chat_history": [],
            "input": state["user_request"],
            "bad_tools": "\n".join(tool_data.bad_tools[:1]),
        }
    )
    # for step in ret["intermediate_steps"]:
    #     (tool, tool_return) = step
    #     console.print(f"[bold green]Tool: {tool.tool}[/bold green]\n", tool_return)
    output = ret["output"]
    # console.log("output: ============\n", output)
    try:
        if isinstance(output, str):
            final_result_response = FinalResultResponse.model_validate_json(output)
        else:
            final_result_response = FinalResultResponse.model_validate(output)
    except Exception as _:  # pylint: disable=broad-except
        # TODO dump output for user intervention
        final_result_response = FinalResultResponse(final_result=output)
    return {
        "call_stack": ["get_results"],
        "final_result": final_result_response,
    }


def get_output_format_prompt(output_format: str) -> str:
    """Get the output format prompt."""
    preamble = """Use the data from the user and follow the following instructions for output:"""
    if output_format == "markdown":
        return f"""
{preamble}
    * Output properly formatted Markdown.
    * Use table / list formatting when applicable or requested.
"""
    if output_format == "json":
        return f"""
{preamble}
    * Output proper JSON.
    * Use a schema if provided.
    * Only output JSON. Do not include any other text / markdown or formatting such as ```json
"""
    if output_format == "csv":
        return f"""
{preamble}
    * Output proper CSV format.
    * Ensure you use double quotes on fields containing line breaks or commas.
    * Include a header with names of the fields.
    * Only output the CSV header and data.
    * Do not include any other text / Markdown such as ```csv
"""
    if output_format == "text":
        return f"""
{preamble}
    * Output plain text without formatting, do not include any other formatting such as markdown.
"""
    return ""


def format_output(state: GraphState):
    """Format output."""
    console.log("[bold green]Formatting output...")
    if not state["final_result"] or not state["final_result"].final_result:
        console.log("[bold red]No final_result to format!")
        return {
            "call_stack": ["format_output"],
            "final_result": state["final_result"],
        }

    model: BaseChatModel = build_chat_model(temperature=0)
    system_prompt = get_output_format_prompt(opts.output_format)
    format_result = model.with_config({"run_name": "Output Formatter"}).invoke(
        [
            ("system", system_prompt),
            ("user", "Original User Request: " + state["user_request"]),
            ("user", "Data: \n" + str(state["final_result"].final_result)),
        ]
    )  # pyright: ignore

    state["final_result"].final_result = str(format_result.content)
    return {
        "call_stack": ["format_output"],
        "final_result": state["final_result"],
    }


# Create the graph
def create_graph():
    """Create the graph."""

    workflow = StateGraph(GraphState)

    # Add nodes to the graph
    workflow.add_node("get_results", get_results)
    workflow.add_node("format_output", format_output)

    # Define the edges
    workflow.set_entry_point("get_results")
    workflow.add_edge("get_results", "format_output")
    workflow.add_edge("format_output", END)

    return workflow


def main() -> None:
    """Main function."""
    console.log(opts)

    # Create the graph
    graph = create_graph()

    checkpointer = MemorySaver()

    # Compile the graph
    app = graph.compile(checkpointer=checkpointer)

    initial_state: GraphState = {
        "sandbox_dir": opts.sandbox_dir,
        "user_request": opts.user_request,
        "needed_tools": [],
        "final_result": None,
    }
    load_existing_tools(initial_state)
    needed_tools: list[ToolDescription] = []
    tools = [t.strip() for t in opts.tools.split(",") if t.strip()]
    for tool in tool_data.ai_tools.values():
        if tool.name not in tools:
            continue
        tool_desc = ToolDescription(name=tool.name, description=tool.description)
        needed_tools.append(tool_desc)
    initial_state["needed_tools"] = needed_tools
    if len(needed_tools) != len(tools):
        console.log("[bold red]One ore more tools were not found!")
        return
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

    output_file = Path("./final_result.md")
    if opts.output_file:
        output_file = opts.output_file
    output_file.write_text(final_state["final_result"].final_result, encoding="utf-8")
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
    else:
        console.print("[bold red]No output was generated!")


if __name__ == "__main__":
    main()
