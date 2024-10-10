"""The main entry point for the application."""

from __future__ import annotations

import asyncio
from dotenv import load_dotenv
from auto_tool_agent.app_logging import log, console, global_vars
from auto_tool_agent.graph.graph_agent import run_graph
from auto_tool_agent.opts import opts


load_dotenv()
load_dotenv("../.env")


async def async_main() -> None:
    """Main entry point for the application."""
    try:
        if opts.verbose > 1:
            log.info(opts)
        with console.status("[bold green]Working on tasks...") as status:
            global_vars.status = status
            await run_graph()
    except Exception as e:  # pylint: disable=broad-except
        log.exception(e)


def main() -> None:
    """Main entry point for the application."""
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
