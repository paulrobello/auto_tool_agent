"""Application logging."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from rich.console import Console, RenderableType
from rich.logging import RichHandler
from rich.status import Status

console = Console()

logPath = Path(os.path.abspath(os.path.dirname(__file__))) / "logs"
logPath.mkdir(parents=True, exist_ok=True)

logFormatter = logging.Formatter("%(asctime)s[%(levelname)-5.5s] %(name)s - %(message)s")
fileHandler = logging.FileHandler(logPath / "agent_run.log")
fileHandler.setFormatter(logFormatter)

FORMAT = "%(name)s - %(message)s"

logging.basicConfig(
    level=logging.CRITICAL,
    format=FORMAT,
    datefmt="[%X]",
    handlers=[
        RichHandler(
            show_time=False,
            rich_tracebacks=True,
            markup=True,
            console=Console(stderr=True),
        ),
        fileHandler,
    ],
)

log = logging.getLogger("[white]app[/white]")
log.setLevel(logging.INFO)

MODULE_LOADER_PREFIX = "[purple]\\[module_loader][/purple]"
ml_log = logging.getLogger(MODULE_LOADER_PREFIX)
ml_log.setLevel(logging.INFO)

AGENT_PREFIX = "[green]\\[agent][/green]"
agent_log = logging.getLogger(AGENT_PREFIX)
agent_log.setLevel(logging.INFO)
FOLDER_MONITOR_PREFIX = "[cyan]\\[folder_monitor][/cyan]"
fm_log = logging.getLogger(FOLDER_MONITOR_PREFIX)


class GlobalVars:
    """Global variables."""

    status: Status | None

    def __init__(self) -> None:
        """Initialize the global variables."""
        self.log = log
        self.ml_log = ml_log
        self.agent_log = agent_log
        self.fm_log = fm_log
        self.status = None

    def status_update(self, new_status: RenderableType) -> None:
        """Update the status."""
        console.log(new_status)
        if self.status is not None:
            self.status.update(new_status)

    def status_start(self) -> None:
        """Start the status."""
        if self.status is not None:
            self.status.start()

    def status_stop(self) -> None:
        """Stop the status."""
        if self.status is not None:
            self.status.stop()


global_vars = GlobalVars()
