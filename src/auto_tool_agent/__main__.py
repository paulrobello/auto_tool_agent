"""The main entry point for the application."""

from __future__ import annotations

import asyncio
import os
import sys
import logging
from argparse import ArgumentParser, Namespace
from dataclasses import dataclass
from typing import Optional
from uuid import uuid4

from rich.console import Console
from rich.logging import RichHandler

from auto_tool_agent.dotenv import load_dotenv

from auto_tool_agent import __application_binary__, __application_title__, __version__
from auto_tool_agent.lib.llm_providers import (
    provider_default_models,
    get_llm_provider_from_str,
)

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


@dataclass
class Session:
    """Session"""

    id: str
    opts: Namespace

    def __init__(
        self,
        id: Optional[str] = None,  # pylint: disable=redefined-builtin
    ) -> None:
        self.id = id or str(uuid4())


session = Session(id="tools_tests")


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
        type=int,
        default=2,
        help="Output additional information. Higher numbers are more verbose.",
        choices=[0, 1, 2, 3],
    )

    parser.add_argument(
        "-p",
        "--provider",
        dest="provider",
        choices=["OpenAI", "Anthropic", "Google", "Groq", "Ollama"],
        default="OpenAI",
        help="The LLM provider to use.",
    )

    parser.add_argument(
        "-m",
        "--model-name",
        dest="model_name",
        type=str,
        help="The model name to user from the provider. If no specified, a default will be used.",
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
        "-i",
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

    parser.add_argument(
        "--sandbox_dir",
        dest="sandbox_dir",
        type=str,
        help="The directory to sandbox agent. defaults to data_dir/sandbox.",
    )

    args = parser.parse_args()

    data_dir = os.path.expanduser(args.data_dir) or os.path.join(
        os.path.expanduser("~/"), ".config", "auto_tool_agent"
    )

    config_file = os.path.join(data_dir, ".env")
    args.sandbox_dir = os.path.expanduser(args.sandbox_dir or "") or os.path.join(
        data_dir, "sandbox"
    )
    os.makedirs(data_dir, exist_ok=True)
    os.makedirs(args.sandbox_dir, exist_ok=True)
    if os.path.exists(config_file):
        if args.verbose > 0:
            log.info("Loading config file: %s", config_file)
        load_dotenv(config_file)
    args.user_request = " ".join(args.user_request)

    if args.user_prompt == "-":
        args.user_prompt = None
        if args.verbose > 1:
            log.info("Reading user request from stdin...")
        args.user_request = sys.stdin.read()
        if not args.user_request:
            parser.error("No user request provided.")

    if args.user_prompt:
        with open(args.user_prompt, "rt", encoding="utf-8") as f:
            args.user_request = f.read()
    if args.user_request is not None:
        args.user_request = args.user_request.strip()
    if not args.user_prompt and not args.user_request:
        parser.error("Either --user_prompt or --user_request must be specified.")

    args.model_name = (
        args.model_name
        or provider_default_models[get_llm_provider_from_str(args.provider)]
    )
    return args


async def async_main() -> None:
    """Main entry point for the application."""
    try:
        opts = parse_args()
        session.opts = opts
        if opts.verbose > 1:
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
            raise FileNotFoundError(
                f"User prompt file {opts.user_prompt} does not exist."
            )

        opts.system_prompt = system_prompt_path

        tool_monitor_task = tool_main(opts)
        agent_task = agent_main(opts, tool_monitor_task)
        await asyncio.gather(tool_monitor_task, agent_task, return_exceptions=True)
    except Exception as e:  # pylint: disable=broad-except
        log.exception(e)


def main() -> None:
    """Main entry point for the application."""
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
