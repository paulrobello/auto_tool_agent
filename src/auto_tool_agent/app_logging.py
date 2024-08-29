"""Application logging."""

from __future__ import annotations

import logging
import os

from rich.console import Console
from rich.logging import RichHandler

# FORMAT = "%(message)s"


logPath = os.path.join(os.path.abspath(os.path.dirname(__file__)), "logs")
logFormatter = logging.Formatter(
    "%(asctime)s[%(levelname)-5.5s] %(name)s - %(message)s"
)
fileHandler = logging.FileHandler(f"{logPath}/agent_run.log")
FORMAT = "%(name)s - %(message)s"

logging.basicConfig(
    level=logging.INFO,
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
