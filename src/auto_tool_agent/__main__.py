"""The main entry point for the application."""

from __future__ import annotations

import asyncio
import os
import auto_tool_agent.opts
from auto_tool_agent.app_logging import logPath, logFormatter, fileHandler, log
from auto_tool_agent.dotenv import load_dotenv

from auto_tool_agent.graph.graph_agent import run_graph
from auto_tool_agent.opts import opts

from auto_tool_agent.tool_maker import tool_main, agent_main

load_dotenv()
load_dotenv("../.env")

os.makedirs(logPath, exist_ok=True)
fileHandler.setFormatter(logFormatter)


async def async_main_old() -> None:
    """Main entry point for the application."""
    try:
        auto_tool_agent.opts.opts = opts
        if opts.verbose > 1:
            log.info(opts)
        system_prompt_path = os.path.join(
            os.path.abspath(opts.data_dir),
            "system_prompts",
            str(opts.system_prompt),
        )
        if not os.path.exists(system_prompt_path):
            system_prompt_path = os.path.join(
                os.path.abspath(os.path.dirname(__file__)),
                "system_prompts",
                str(opts.system_prompt),
            )

        if not os.path.exists(system_prompt_path):
            raise FileNotFoundError(
                f"System prompt file {opts.system_prompt} does not exist in system_prompts folder."
            )
        if opts.user_prompt and not os.path.exists(opts.user_prompt):
            raise FileNotFoundError(
                f"User prompt file {opts.user_prompt} does not exist."
            )

        opts.system_prompt = system_prompt_path

        tool_monitor_task = tool_main(opts)
        agent_task = agent_main(opts, tool_monitor_task)
        await asyncio.gather(tool_monitor_task, agent_task, return_exceptions=True)
    except Exception as e:  # pylint: disable=broad-except
        log.exception(e)


async def async_main() -> None:
    """Main entry point for the application."""
    try:
        auto_tool_agent.opts.opts = opts
        if opts.verbose > 1:
            log.info(opts)
        run_graph()
    except Exception as e:  # pylint: disable=broad-except
        log.exception(e)


def main() -> None:
    """Main entry point for the application."""
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
