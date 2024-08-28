"""AI that makes its own tools"""

from __future__ import annotations
import asyncio
import logging
import os
from argparse import Namespace
from typing import Union
from rich import print  # pylint: disable=redefined-builtin
from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain_core.prompts import MessagesPlaceholder, ChatPromptTemplate
from langchain_core.tools import BaseTool

from auto_tool_agent.folder_monitor import FolderMonitor
from auto_tool_agent.tool_data import tool_data
from auto_tool_agent.session import session
from auto_tool_agent.ai_tools import (
    list_files,
    read_file,
    write_file,
    rename_file,
)
from auto_tool_agent.lib.llm_config import LlmConfig
from auto_tool_agent.lib.llm_providers import get_llm_provider_from_str

from auto_tool_agent.lib.llm_providers import provider_default_models

AGENT_PREFIX = "[green]\\[agent][/green]"

agent_log = logging.getLogger(AGENT_PREFIX)


def get_output_format_prompt(output_format: str) -> str:
    """Get the output format prompt."""
    preamble = """* When presenting your final answer follow the following instructions. These instructions are only for the final answer. If a tool was created or modified respond using the instructions already given:"""
    outro = """* Return the answer do not save it to a file."""
    if output_format == "markdown":
        return f"""
{preamble}
    * Output properly formatted Markdown.
    * Use table / list formatting when applicable or requested.
    {outro}
        """
    if output_format == "json":
        return f"""
{preamble}
    * Output proper JSON.
    * Use a schema if provided.
    * Only output JSON. Do not include any other text / markdown or formatting.
    * Do not include ```json
    {outro}
        """
    if output_format == "csv":
        return f"""
{preamble}
    * Output proper CSV format.
    * Ensure you use double quotes on fields containing line breaks or commas.
    * Include a header with names of the fields.
    * Only output the CSV header and data.
    * Do not include any other text / Markdown.
    * Do not include ```csv
    {outro}
        """
    if output_format == "text":
        return f"""
{preamble}
    * Output plain text without formatting, do not include any other formatting such as markdown.
    {outro}
        """
    return ""


async def create_agent(opts: Namespace) -> Union[str, bool]:
    """Create an agent."""
    opts.user_request = opts.user_request.strip()
    if opts.verbose > 0:
        agent_log.info("Creating agent with task: %s", opts.user_request)
    with open(opts.system_prompt, "rt", encoding="utf-8") as f:
        system_prompt = f.read()
    system_prompt = system_prompt.strip() + get_output_format_prompt(opts.output_format)
    if opts.verbose > 1:
        agent_log.info(
            "System prompt: \n=============\n%s\n=============", system_prompt
        )
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ]
    )
    provider = get_llm_provider_from_str(opts.provider)
    llm_config = LlmConfig(
        provider=provider,
        model_name=opts.model_name or provider_default_models[provider],
        temperature=0.1,
    )
    llm = llm_config.build_chat_model()
    agent_log.info(llm_config)
    tools: list[BaseTool] = [  # pyright: ignore [reportAssignmentType]
        list_files,
        read_file,
        write_file,
        rename_file,
    ]
    num_waits = 0
    while tool_data.last_tool_load == 0:
        num_waits += 1
        if num_waits > 10:
            agent_log.error("Took too long for tools to load.")
            return False
        agent_log.info("Waiting for tools load...")
        await asyncio.sleep(3)
    if opts.verbose > 1:
        agent_log.info("AI tools found: %d", len(tool_data.ai_tools))

    tools += tool_data.ai_tools.values()
    agent = create_tool_calling_agent(llm, tools, prompt)
    agent_executor = AgentExecutor(
        agent=agent, tools=tools, verbose=True  # pyright: ignore [reportArgumentType]
    )
    agent_executor.verbose = False
    if opts.verbose > 0:
        agent_log.info("Executing agent...")
    ret = agent_executor.invoke(
        {
            "chat_history": [],
            "input": opts.user_request,
            "bad_tools": "\n".join(tool_data.bad_tools[:1]),
        }
    )
    output = ret["output"]
    if "New tool created:" in output:
        if opts.verbose > 0:
            agent_log.info("[yellow]{output}[/yellow]")
        return True
    if "Fixed tool:" in output:
        if opts.verbose > 0:
            agent_log.info("[yellow]{output}[/yellow]")
        return True
    return output


async def agent_loop(opts: Namespace, tool_monitor_task: asyncio.Task) -> None:
    """Run the agent loop."""
    try:
        num_iterations = 0
        loop_last_tool_load = tool_data.last_tool_load
        while (
            (output := await create_agent(opts))
            and num_iterations < opts.max_iterations
            and not isinstance(output, str)
        ):
            num_iterations += 1
            if opts.verbose > 0:
                agent_log.info("New tool was created looping")
            max_tool_load_loops = 5
            tool_load_loops = 0
            while (
                tool_load_loops < max_tool_load_loops
                and loop_last_tool_load == tool_data.last_tool_load
            ):
                tool_load_loops += 1
                if opts.verbose > 0:
                    agent_log.info("Waiting for new tool to load")
                await asyncio.sleep(3)

        if opts.output_file and isinstance(output, str):
            with open(opts.output_file, "wt", encoding="utf-8") as f:
                f.write(output)

        if opts.verbose > 0:
            agent_log.info("=" * 20)
            agent_log.info(output)
        print(output)
        if opts.verbose > 0:
            agent_log.info("=" * 20)
    except Exception as e:  # pylint: disable=broad-exception-caught
        agent_log.exception(e)
    finally:
        try:
            tool_monitor_task.cancel()
        except Exception as _:  # pylint: disable=broad-exception-caught
            print("tool_monitor_task was cancelled")


def agent_main(opts: Namespace, tool_monitor_task: asyncio.Task) -> asyncio.Task:
    """Start the agent."""
    return asyncio.create_task(agent_loop(opts, tool_monitor_task))


def tool_main(opts: Namespace) -> asyncio.Task:
    """Start the folder monitor."""
    folder_path = str(os.path.join(opts.sandbox_dir, session.id))
    monitor = FolderMonitor(folder_path, opts)
    # Start the task but don't await it.
    # This way the agent creation can happen even if the folder monitor is not yet finished.
    return asyncio.create_task(monitor.start())
