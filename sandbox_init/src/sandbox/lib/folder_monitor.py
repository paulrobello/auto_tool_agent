"""Monitor the specified folder for changes and load new modules."""

from __future__ import annotations

from pathlib import Path
import asyncio
from argparse import Namespace
from watchdog.observers import Observer

from sandbox.lib.module_loader import ModuleLoader
from sandbox.opts import console


FM_PREFIX = "[cyan]\\[folder_monitor][/cyan]"


class FolderMonitor:
    """Monitor the specified folder for changes and load new modules."""

    def __init__(self, folder_path: Path, opts: Namespace) -> None:
        """Initialize the folder monitor."""
        self.folder_path = folder_path
        if not self.folder_path.exists():
            raise ValueError(f"Folder {self.folder_path} does not exist.")
        self.opts = opts
        self.observer = Observer()
        self.event_handler = ModuleLoader(folder_path)

    async def start(self) -> None:
        """Start the folder monitor."""
        if self.opts.verbose > 0:
            console.log(f"{FM_PREFIX}Starting up: %s", self.folder_path)
        self.observer.schedule(
            self.event_handler, str(self.folder_path), recursive=True
        )
        self.observer.start()
        while True:
            try:
                await asyncio.sleep(1)
            except Exception as _:  # pylint: disable=broad-except
                break

    async def stop(self) -> None:
        """Stop the folder monitor."""
        if self.opts.verbose > 0:
            console.log(f"{FM_PREFIX}Shutting down:  %s", str(self.folder_path))
        self.observer.stop()
        self.observer.join()
