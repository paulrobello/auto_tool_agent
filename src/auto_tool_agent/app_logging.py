"""Application logging."""

from __future__ import annotations

import logging
import os

from rich.console import Console
from rich.logging import RichHandler
from rich.status import Status
from typing_extensions import Optional

console = Console()

logPath = os.path.join(os.path.abspath(os.path.dirname(__file__)), "logs")
os.makedirs(logPath, exist_ok=True)

logFormatter = logging.Formatter(
    "%(asctime)s[%(levelname)-5.5s] %(name)s - %(message)s"
)
fileHandler = logging.FileHandler(f"{logPath}/agent_run.log")
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

    status: Optional[Status]

    def __init__(self) -> None:
        """Initialize the global variables."""
        self.log = log
        self.ml_log = ml_log
        self.agent_log = agent_log
        self.fm_log = fm_log
        self.status = None


global_vars = GlobalVars()
