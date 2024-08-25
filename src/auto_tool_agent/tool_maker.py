"""AI that makes its own tools"""

from __future__ import annotations
import asyncio
import importlib
import importlib.util
import logging
import os
import time
from argparse import Namespace
from dataclasses import dataclass, field
from typing import Union
from rich import print  # pylint: disable=redefined-builtin
from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain_core.prompts import MessagesPlaceholder, ChatPromptTemplate
from langchain_core.tools import BaseTool

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from auto_tool_agent.ai_tools import (
    list_files,
    read_file,
    write_file,
    rename_file,
)
from auto_tool_agent.lib.llm_config import LlmConfig
from auto_tool_agent.lib.llm_providers import LlmProvider
from auto_tool_agent.sandboxing import sandbox_base, session

AGENT_PREFIX = "[green]\\[agent][/green]"
FOLDER_MONITOR_PREFIX = "[cyan]\\[folder_monitor][/cyan]"
MODULE_LOADER_PREFIX = "[purple]\\[module_loader][/purple]"

agent_log = logging.getLogger(AGENT_PREFIX)
fm_log = logging.getLogger(FOLDER_MONITOR_PREFIX)
ml_log = logging.getLogger(MODULE_LOADER_PREFIX)


@dataclass
class TooData:
    """Tool data."""

    last_tool_load: float = 0
    ai_tools: dict[str, BaseTool] = field(default_factory=dict)
    bad_tools: list[str] = field(default_factory=list)

    def add_good_tool(self, name: str, tool: BaseTool) -> None:
        """Add a good tool."""
        if name in self.bad_tools:
            self.bad_tools.remove(name)
        self.ai_tools[name] = tool

    def add_bad_tool(self, name: str) -> None:
        """Add a bad tool."""
        if name in self.ai_tools:
            del self.ai_tools[name]
        if name not in self.bad_tools:
            self.bad_tools.append(name)


tool_data = TooData()


def discover_tools(module) -> list[BaseTool]:
    """
    Discovers and builds a list of functions annotated with "@tool" in the given module.

    Args:
        module (module): A Python module to inspect.

    Returns:
        set: A set of functions annotated with "@tool".
    """
    tools: list[BaseTool] = []
    for name in dir(module):
        func = getattr(module, name)
        if isinstance(func, BaseTool):
            ml_log.info("found tool: %s", name)
            tools.append(func)
            tool_data.last_tool_load = time.time()
    return tools


class ModuleLoader(FileSystemEventHandler):
    """Load modules when they are modified."""

    def __init__(self, folder_path) -> None:
        """Initialize the event handler."""
        super().__init__()
        self.folder_path = folder_path
        # the folder to watch
        self.load_existing_modules()
        # load any existing modules
        self.last_loaded_modules = {}
        # used to avoid loading modules too often

    def on_modified(self, event):
        """Load the modified module."""
        current_time = time.time()
        module_path = event.src_path
        if (
            module_path in self.last_loaded_modules
            and current_time - self.last_loaded_modules[module_path] < 1
        ):
            return
        self.load_module(module_path)
        self.last_loaded_modules[module_path] = current_time

    @staticmethod
    def load_module(module_path: str) -> None:
        """Load the specified module."""
        module_path = module_path.replace("\\", "/")
        module_name = module_path[:-3]  # remove .py extension

        try:
            if (
                not os.path.isfile(module_path)
                or module_path.endswith("~")
                or "__init__" in module_path
            ):
                return
            if module_path.endswith(".py"):
                spec = importlib.util.spec_from_file_location(module_name, module_path)
                if not spec:
                    ml_log.error(
                        "[red]Error[/red]: unable to load module %s", module_name
                    )
                    return
                module = importlib.util.module_from_spec(spec)
                if spec.loader is None:
                    ml_log.error(
                        "[red]Error[/red]: unable to find loader for module %s",
                        module_name,
                    )
                    return
                # ml_log.info("Attempting to load module: %s", module_name)
                spec.loader.exec_module(module)
                ml_log.info("Loaded module: %s", module_name)
                new_tools: list[BaseTool] = discover_tools(module)
                # ml_log.info("New tools found: %d", len(new_tools))
                if len(new_tools) != 1:
                    ml_log.error(
                        "[red]Error[/red]: found %d != 1 new tools for module %s",
                        len(new_tools),
                        module_name,
                    )
                    tool_data.add_bad_tool(module_name)
                    return
                tool_data.add_good_tool(module_name, new_tools[0])
            else:
                ml_log.info("Ignoring non-Python file: %s", module_path)
        except Exception as e:  # pylint: disable=broad-except
            tool_data.add_bad_tool(module_name)
            ml_log.exception(
                "[red]Error[/red]: loading module %s: %s", module_path, str(e)
            )

    def load_existing_modules(self) -> None:
        """Load any existing modules in the folder."""
        for filename in os.listdir(self.folder_path):
            module_path = os.path.join(self.folder_path, filename)
            self.load_module(module_path)


class FolderMonitor:
    """Monitor the specified folder for changes and load new modules."""

    def __init__(self, folder_path: str) -> None:
        """Initialize the folder monitor."""
        self.folder_path = folder_path
        if not os.path.exists(self.folder_path):
            raise ValueError(f"Folder {self.folder_path} does not exist.")
        self.observer = Observer()
        self.event_handler = ModuleLoader(folder_path)

    async def start(self) -> None:
        """Start the folder monitor."""
        fm_log.info("Starting up: %s", self.folder_path)
        self.observer.schedule(self.event_handler, self.folder_path, recursive=True)
        self.observer.start()
        while True:
            await asyncio.sleep(1)

    async def stop(self) -> None:
        """Stop the folder monitor."""
        fm_log.info("Shutting down:  %s", self.folder_path)
        self.observer.stop()
        self.observer.join()


def get_output_format_prompt(output_format: str) -> str:
    """Get the output format prompt."""
    if output_format == "markdown":
        return """
        * When presenting your final answer use properly formatted Markdown.
        * Use table / list formatting when applicable or requested.
        * Return the output do not save it to a file.
        """
    if output_format == "json":
        return """
        * When presenting your final answer use proper JSON formatting. 
        * Only output JSON. Do not include any other text / markdown or formatting.
        * Return the output do not save it to a file.
        """
    if output_format == "csv":
        return """
        * When presenting your final answer use proper CSV formatting.
            * Include a header with names of the fields.
            * Ensure you use double quotes on fields containing line breaks or commas.
        * Only output CSV. Do not include any other text / markdown or formatting.
        * Return the output do not save it to a file.
        """
    if output_format == "text":
        return """
        * When presenting your final answer use plain text without formatting, do not include any other formatting such as markdown.
        * Return the output do not save it to a file.
        """
    return ""


async def create_agent(opts: Namespace) -> Union[str, bool]:
    """Create an agent."""
    opts.user_request = opts.user_request.strip()
    agent_log.info("Creating agent with task: %s", opts.user_request)
    with open(opts.system_prompt, "rt", encoding="utf-8") as f:
        system_prompt = f.read()
    system_prompt = system_prompt.strip() + get_output_format_prompt(opts.output_format)
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ]
    )

    llm = LlmConfig(
        provider=LlmProvider.OPENAI,
        model_name=os.environ.get("OPENAI_MODEL_NAME", "gpt-4o"),
        temperature=0.1
    ).build_chat_model()
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
            agent_log.error("Took to long for tools to load.")
            return False
        agent_log.info("Waiting for tools load...")
        await asyncio.sleep(3)
    agent_log.info("AI tools found: %d", len(tool_data.ai_tools))

    tools += tool_data.ai_tools.values()
    agent = create_tool_calling_agent(llm, tools, prompt)
    agent_executor = AgentExecutor(
        agent=agent, tools=tools, verbose=True  # pyright: ignore [reportArgumentType]
    )
    agent_executor.verbose = False
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
        agent_log.info("[yellow]{output}[/yellow]")
        return True
    if "Fixed tool:" in output:
        agent_log.info("[yellow]{output}[/yellow]")
        return True
    return output


async def agent_loop(opts: Namespace) -> None:
    """Run the agent loop."""
    num_iterations = 0
    loop_last_tool_load = tool_data.last_tool_load
    while (
        (output := await create_agent(opts))
        and num_iterations < opts.max_iterations
        and not isinstance(output, str)
    ):
        num_iterations += 1
        agent_log.info("New tool was created looping")
        max_tool_load_loops = 5
        tool_load_loops = 0
        while (
            tool_load_loops < max_tool_load_loops
            and loop_last_tool_load == tool_data.last_tool_load
        ):
            tool_load_loops += 1
            agent_log.info("Waiting for new tool to load")
            await asyncio.sleep(3)

    if opts.output_file and isinstance(output, str):
        with open(opts.output_file, "wt", encoding="utf-8") as f:
            f.write(output)

    agent_log.info("=" * 20)
    agent_log.info(output)
    print(output)
    agent_log.info("=" * 20)

    # tool_monitor_task.cancel()
    # try:
    #     await tool_monitor_task
    # except asyncio.CancelledError:
    #     print("tool_monitor_task was cancelled")


async def agent_main(opts: Namespace) -> asyncio.Task:
    """Start the agent."""
    return asyncio.create_task(agent_loop(opts))


async def tool_main(opts: Namespace) -> asyncio.Task:  # pylint: disable=unused-argument
    """Start the folder monitor."""
    folder_path = str(os.path.join(sandbox_base, session.id))
    monitor = FolderMonitor(folder_path)
    # Start the task but don't await it.
    # This way the agent creation can happen even if the folder monitor is not yet finished.
    return asyncio.create_task(monitor.start())
