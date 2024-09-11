"""Parse command line arguments."""

from __future__ import annotations

import os
from pathlib import Path
import sys
from typing import Literal, cast

from argparse import ArgumentParser
from dotenv import load_dotenv
from auto_tool_agent import __application_binary__, __application_title__, __version__
from auto_tool_agent.app_logging import log

from auto_tool_agent.lib.llm_providers import (
    provider_default_models,
    get_llm_provider_from_str,
)

OutputFormats = Literal["none", "text", "markdown", "csv", "json"]

output_formats: list[OutputFormats] = ["none", "text", "markdown", "csv", "json"]
format_to_extension: dict[OutputFormats, str] = {
    "none": "",
    "text": ".txt",
    "markdown": ".md",
    "csv": ".csv",
    "json": ".json",
}


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
        default=1,
        help="Output additional information. Higher numbers are more verbose.",
        choices=[0, 1, 2, 3],
    )

    parser.add_argument(
        "-p",
        "--provider",
        dest="provider",
        # choices=["OpenAI", "Anthropic", "Bedrock", "Google", "Groq", "Ollama"]
        choices=["OpenAI", "Anthropic", "Bedrock"],
        default="Bedrock",
        help="The LLM provider to use.",
    )

    parser.add_argument(
        "-n",
        "--model-name",
        dest="model_name",
        type=str,
        help="The model name to user from the provider. If no specified, a default will be used.",
    )

    parser.add_argument(
        "-u",
        "--user_prompt",
        dest="user_prompt",
        type=Path,
        help="The user prompt file name to use for user_request. Use - to read from stdin.",
    )

    parser.add_argument(
        "-i",
        "--interactive",
        dest="interactive",
        action="store_true",
        help="Prompt user at various stages for feedback.",
    )

    parser.add_argument(
        "-m",
        "--max_iterations",
        dest="max_iterations",
        type=int,
        default=25,
        help="The maximum number of iterations to run before stopping.",
    )

    parser.add_argument(
        "-o",
        "--output file",
        dest="output_file",
        type=Path,
        help="The file to write the final response to.",
    )

    parser.add_argument(
        "-f",
        "--format",
        dest="output_format",
        type=str,
        choices=output_formats,
        default="markdown",
        help="Specifies the output format that the AI should generate. Default is markdown.",
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
        type=Path,
        default=Path(
            os.environ.get("AUTO_TOOL_AGENT_DATA_DIR") or "~/.config/auto_tool_agent"
        ).expanduser(),
        help="The directory to store data and generated tools. Default is ~/.config/auto_tool_agent.",
    )

    parser.add_argument(
        "--sandbox_dir",
        dest="sandbox_dir",
        type=Path,
        help="The directory to sandbox agent. defaults to DATA_DIR/sandbox.",
    )

    parser.add_argument(
        "--clear_sandbox",
        dest="clear_sandbox",
        action="store_true",
        help="Clear the sandbox directory before running.",
    )

    parser.add_argument(
        "--generate_graph",
        dest="generate_graph",
        action="store_true",
        help="Generate only graph diagram and exit.",
    )

    parser.add_argument(
        "-r",
        "--review-tools",
        dest="review_tools",
        action="store_true",
        help="Re-review tools before running.",
    )

    parser.add_argument(
        "-b",
        "--branch",
        type=str,
        help="Create or checkout a branch before running.",
    )

    args = parser.parse_args()

    data_dir = (
        Path(args.data_dir).expanduser() or Path.home() / ".config" / "auto_tool_agent"
    )
    args.data_dir = data_dir

    config_file = data_dir / ".env"
    args.sandbox_dir = (
        args.sandbox_dir and args.sandbox_dir.expanduser()
    ) or data_dir / "sandbox"
    data_dir.mkdir(parents=True, exist_ok=True)
    args.sandbox_dir.mkdir(parents=True, exist_ok=True)
    if config_file.exists():
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
        args.user_request = cast(Path, args.user_prompt).read_text(encoding="utf-8")
    if args.user_request is not None:
        args.user_request = args.user_request.strip()
    if not args.user_prompt and not args.user_request and not args.generate_graph:
        parser.error(
            "Either --user_prompt or --user_request or --generate_graph must be specified."
        )

    args.model_name = (
        args.model_name
        or provider_default_models[get_llm_provider_from_str(args.provider)]
    )
    return args


opts = parse_args()
