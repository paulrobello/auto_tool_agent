"""Output nodes and functions for graph agent."""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel

from auto_tool_agent.app_logging import console
from auto_tool_agent.graph.graph_shared import build_chat_model, save_state
from auto_tool_agent.graph.graph_state import GraphState
from auto_tool_agent.opts import opts


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
    save_state(state)
    return {
        "call_stack": ["format_output"],
        "final_result": state["final_result"],
    }
