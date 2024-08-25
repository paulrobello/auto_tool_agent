"""The main entry point for the application."""

from __future__ import annotations

import asyncio
import os
import sys
import logging
from argparse import ArgumentParser

from rich.console import Console
from rich.logging import RichHandler

from dotenv import load_dotenv

from auto_tool_agent import __application_binary__, __application_title__, __version__

from auto_tool_agent.tool_maker import tool_main, agent_main

load_dotenv()
load_dotenv("../.env")

logPath = os.path.join(os.path.abspath(os.path.dirname(__file__)), "logs")
os.makedirs(logPath, exist_ok=True)
logFormatter = logging.Formatter(
    "%(asctime)s[%(levelname)-5.5s] %(name)s - %(message)s"
)
fileHandler = logging.FileHandler(f"{logPath}/agent_run.log")
fileHandler.setFormatter(logFormatter)

# FORMAT = "%(message)s"
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


def parse_args():
    """Parse command line arguments."""
    parser = ArgumentParser(
        prog=__application_binary__,
        description=f"{__application_title__}",
        epilog=f"v{__version__}",
    )

    parser.add_argument(
        "--version",
        help="Show version information.",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        help="Output additional information.",
        action="append",
    )

    parser.add_argument(
        "-r",
        "--region",
        dest="regions",
        action="append",
        type=str,
        help="The AWS region to run in. Can be specified multiple times for multiple regions.",
    )
    parser.add_argument(
        "-s",
        "--system_prompt",
        dest="system_prompt",
        type=str,
        default="aws.md",
        help="The system prompt file name with default of aws.md.",
    )
    parser.add_argument(
        "-u",
        "--user_prompt",
        dest="user_prompt",
        type=str,
        help="The user prompt file name to use for user_request. Use - to read from stdin.",
    )
    parser.add_argument(
        "-m",
        "--max_iterations",
        dest="max_iterations",
        type=int,
        default=5,
        help="The maximum number of iterations to run before stopping.",
    )

    parser.add_argument(
        "-o",
        "--output file",
        dest="output_file",
        type=str,
        help="The file to write the final response to.",
    )

    parser.add_argument(
        "user_request",
        type=str,
        nargs="*",
        help="The user request to fulfill. Required if --user_prompt is not specified.",
    )
    parser.add_argument(
        "-d",
        "--data_dir",
        dest="data_dir",
        type=str,
        default=os.environ.get("AUTO_TOOL_AGENT_DATA_DIR")
        or "~/.config/auto_tool_agent",
        help="The directory to store data and generated tools. Default is ~/.config/auto_tool_agent.",
    )
    parser.add_argument(
        "-f",
        "--format",
        dest="output_format",
        type=str,
        choices=["none", "text", "markdown", "csv", "json"],
        default="Markdown",
        help="Specifies the output format that the AI should generate. Default is markdown.",
    )

    args = parser.parse_args()

    if not args.user_prompt and not args.user_request:
        parser.error("Either --user_prompt or user_request must be specified.")

    config_dir = os.path.expanduser(args.data_dir) or os.path.join(
        os.path.expanduser("~/"), ".config", "auto_tool_agent"
    )
    os.makedirs(os.path.join(config_dir, "sandbox"), exist_ok=True)
    config_file = os.path.join(config_dir, ".env")
    if os.path.exists(config_file):
        log.info("Loading config file: %s", config_file)
        load_dotenv(config_file)
    args.user_request = " ".join(args.user_request)

    if args.user_prompt == "-":
        args.user_prompt = None
        log.info("Reading user request from stdin...")
        args.user_request = sys.stdin.read()
        if not args.user_request:
            parser.error("No user request provided.")

    if args.user_prompt:
        with open(args.user_prompt, "rt", encoding="utf-8") as f:
            args.user_request = f.read()

    return args


async def main() -> None:
    """Main entry point for the application."""
    opts = parse_args()
    log.info(opts)
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
        raise FileNotFoundError(f"User prompt file {opts.user_prompt} does not exist.")

    opts.system_prompt = system_prompt_path
    # exit(0)
    tool_monitor_task = tool_main(opts)
    agent_task = agent_main(opts)
    await asyncio.gather(tool_monitor_task, agent_task)


if __name__ == "__main__":
    asyncio.run(main())
