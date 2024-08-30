"""The main entry point for the application."""

from __future__ import annotations

import asyncio

import auto_tool_agent.opts
from auto_tool_agent.app_logging import log, console
from auto_tool_agent.dotenv import load_dotenv

from auto_tool_agent.graph.graph_agent import run_graph
from auto_tool_agent.opts import opts


load_dotenv()
load_dotenv("../.env")


async def async_main() -> None:
    """Main entry point for the application."""
    try:
        auto_tool_agent.opts.opts = opts
        if opts.verbose > 1:
            log.info(opts)
        with console.status("[bold green]Working on tasks..."):
            run_graph()
    except Exception as e:  # pylint: disable=broad-except
        log.exception(e)


def main() -> None:
    """Main entry point for the application."""
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
