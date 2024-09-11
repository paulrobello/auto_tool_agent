"""Shared functions for the graph agent."""

from __future__ import annotations

from pathlib import Path

import simplejson as json
from git import Repo
from git.util import Actor
from langchain_core.language_models import BaseChatModel

from auto_tool_agent.app_logging import agent_log, console
from auto_tool_agent.graph.graph_state import GraphState
from auto_tool_agent.lib.llm_config import LlmConfig
from auto_tool_agent.lib.llm_providers import (
    get_llm_provider_from_str,
    provider_default_models,
)
from auto_tool_agent.lib.module_loader import ModuleLoader
from auto_tool_agent.opts import opts, format_to_extension
from auto_tool_agent.lib.session import session


def commit_leftover_changes(
    sandbox_dir: Path, commit_message: str = "Adding all changes"
) -> None:
    """Commit all untracked files and changes."""
    repo = Repo(sandbox_dir)

    leftovers = repo.untracked_files + [item.a_path for item in repo.index.diff(None)]
    if len(leftovers) > 0:
        console.log("[bold green]Commiting all changes...")
        repo.index.add(leftovers)
        repo.index.commit(
            f"Session: {session.id} - {commit_message}",
            author=git_actor,
            committer=git_actor,
        )


def build_chat_model(*, temperature: float = 0.5) -> BaseChatModel:
    """Build the chat model."""
    provider = get_llm_provider_from_str(opts.provider)
    llm_config = LlmConfig(
        provider=provider,
        model_name=opts.model_name or provider_default_models[provider],
        temperature=temperature,
    )
    if opts.verbose > 2:
        agent_log.info(llm_config)
    return llm_config.build_chat_model()


def save_state(state: GraphState):
    """Save the state."""
    with open("state.json", "wt", encoding="utf-8") as f:
        json.dump(state, f, indent=2, default=str)
    if state["final_result"]:
        if opts.output_file:
            with open(opts.output_file, "wt", encoding="utf-8") as f:
                f.write(state["final_result"].final_result)
        else:
            with open(
                f"final_result{format_to_extension[opts.output_format]}",
                "wt",
                encoding="utf-8",
            ) as f:
                f.write(state["final_result"].final_result)
    return {"call_stack": ["save_state"]}


def load_existing_tools():
    """Load existing tools."""
    ModuleLoader(opts.sandbox_dir / "src" / "sandbox")
    # print(tool_data)


class AutoToolAgentError(Exception):
    """Auto tool agent error."""


class UserAbortError(AutoToolAgentError):
    """User abort error."""


git_actor = Actor("Auto Agent", "auto_agent@pardev.net")
