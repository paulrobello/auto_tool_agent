"""Tool Module Loader"""

from __future__ import annotations

import importlib
import importlib.util
import logging
import os
import time

from argparse import Namespace
from langchain_core.tools import BaseTool
from watchdog.events import FileSystemEventHandler

from auto_tool_agent.tool_data import tool_data

MODULE_LOADER_PREFIX = "[purple]\\[module_loader][/purple]"
ml_log = logging.getLogger(MODULE_LOADER_PREFIX)


class ModuleLoader(FileSystemEventHandler):
    """Load modules on startup and when they are created / modified."""

    def __init__(self, folder_path: str, opts: Namespace) -> None:
        """Initialize the event handler."""
        super().__init__()
        self.opts = opts
        self.load_existing_modules(os.path.join(opts.data_dir, "tools"))
        self.load_existing_modules(
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "tools")
        )
        self.folder_path = folder_path
        # the folder to watch
        self.load_existing_modules(self.folder_path)
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
        self.load_module(str(module_path))
        self.last_loaded_modules[module_path] = current_time

    def load_module(self, module_path: str) -> None:
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
                new_tools: list[BaseTool] = self.discover_tools(module)
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
                if self.opts.verbose > 1:
                    ml_log.info("Ignoring non-Python file: %s", module_path)
        except Exception as e:  # pylint: disable=broad-except
            tool_data.add_bad_tool(module_name)
            ml_log.exception(
                "[red]Error[/red]: loading module %s: %s", module_path, str(e)
            )

    def load_existing_modules(self, folder_path: str) -> None:
        """Load any existing modules in the folder."""
        if not os.path.exists(folder_path):
            ml_log.info("Folder does not exist: %s", folder_path)
            return
        for filename in os.listdir(folder_path):
            module_path = os.path.join(folder_path, filename)
            self.load_module(module_path)

    def discover_tools(self, module) -> list[BaseTool]:
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
                if self.opts.verbose > 1:
                    ml_log.info("found tool: %s", name)
                tools.append(func)
                tool_data.last_tool_load = time.time()
        return tools
