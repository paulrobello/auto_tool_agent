"""Monitor the specified folder for changes and load new modules."""

from __future__ import annotations

import asyncio
import logging
import os
from argparse import Namespace

from watchdog.observers import Observer

from auto_tool_agent.module_loader import ModuleLoader

FOLDER_MONITOR_PREFIX = "[cyan]\\[folder_monitor][/cyan]"
fm_log = logging.getLogger(FOLDER_MONITOR_PREFIX)


class FolderMonitor:
    """Monitor the specified folder for changes and load new modules."""

    def __init__(self, folder_path: str, opts: Namespace) -> None:
        """Initialize the folder monitor."""
        self.folder_path = folder_path
        if not os.path.exists(self.folder_path):
            raise ValueError(f"Folder {self.folder_path} does not exist.")
        self.opts = opts
        self.observer = Observer()
        self.event_handler = ModuleLoader(folder_path, opts)

    async def start(self) -> None:
        """Start the folder monitor."""
        if self.opts.verbose > 0:
            fm_log.info("Starting up: %s", self.folder_path)
        self.observer.schedule(self.event_handler, self.folder_path, recursive=True)
        self.observer.start()
        while True:
            try:
                await asyncio.sleep(1)
            except Exception as _:  # pylint: disable=broad-except
                break

    async def stop(self) -> None:
        """Stop the folder monitor."""
        if self.opts.verbose > 0:
            fm_log.info("Shutting down:  %s", self.folder_path)
        self.observer.stop()
        self.observer.join()
