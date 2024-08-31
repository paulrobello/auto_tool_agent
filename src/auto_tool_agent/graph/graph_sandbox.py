"""Sandbox related nodes for graph agent."""

from __future__ import annotations

import shutil
from typing import cast
from pathlib import Path
from git import Repo

import tomlkit
from tomlkit.items import Table, Array

from auto_tool_agent.graph.graph_shared import load_existing_tools
from auto_tool_agent.app_logging import agent_log, console
from auto_tool_agent.graph.graph_state import GraphState
from auto_tool_agent.lib.execute_command import execute_command
from auto_tool_agent.opts import opts


def setup_sandbox(state: GraphState):
    """Entrypoint."""
    console.log("[bold green]Checking sandbox...")
    sandbox_dir = state["sandbox_dir"].expanduser()

    if state["clean_run"] and sandbox_dir.exists():
        console.log("[bold green]Removing old sandbox...")
        if opts.verbose > 1:
            agent_log.info("Removing old sandbox: %s", sandbox_dir)
        shutil.rmtree(sandbox_dir)

    if not sandbox_dir.exists():
        console.log("[bold green]Sandbox path not found, creating...")
        if opts.verbose > 1:
            agent_log.info("Sandbox path not found, creating...")
        sandbox_dir.mkdir(parents=True, exist_ok=True)

    if opts.verbose > 1:
        agent_log.info("Sandbox path: %s", sandbox_dir)
    return {
        "call_stack": ["entrypoint"],
        "sandbox_dir": sandbox_dir,
    }


# pylint: disable=too-many-statements, too-many-branches
def sync_venv(state: GraphState):
    """Sync the venv."""
    console.log("[bold green]Checking venv...")
    if opts.verbose > 1:
        agent_log.info("Syncing venv...")

    sandbox_dir = state["sandbox_dir"]
    project_config = sandbox_dir / "pyproject.toml"

    if not project_config.exists():
        console.log("[bold green]Project config not found, creating...")
        if opts.verbose > 1:
            agent_log.info("Project config not found, creating...")
        config = {"command": "uv", "params": ["init"], "folder": sandbox_dir}
        result = execute_command(config)
        if result["exit_code"] != 0:
            agent_log.error(result)
            raise ValueError("Failed to create project config.")

        # Update project
        project_toml = tomlkit.parse(project_config.read_text(encoding="utf-8"))
        project = cast(Table, project_toml["project"])
        project["description"] = "AI Auto Tool Agent"

        # Add package section
        project["packages"] = cast(Array, tomlkit.array())
        tab = tomlkit.inline_table()
        tab.add("include", "src/")
        project["packages"].insert(0, tab)  # pyright: ignore
        tab = tomlkit.inline_table()
        tab.add("include", "src/**/*.py")
        project["packages"].insert(1, tab)  # pyright: ignore

        project_config.write_text(tomlkit.dumps(project_toml))

    project_toml = tomlkit.parse(project_config.read_text(encoding="utf-8"))
    project = cast(Table, project_toml["project"])
    existing_deps = project.get("dependencies") or []
    existing_deps = [
        dep.split(">")[0].split("<")[0].split("=")[0].strip().split("^")[0].strip()
        for dep in existing_deps
    ]
    existing_deps.sort()
    if opts.verbose > 1:
        agent_log.info("Existing deps: %s", existing_deps)

    if len(state["dependencies"]) > 0:
        requested_deps = state["dependencies"]
        requested_deps.sort()
        if opts.verbose > 1:
            agent_log.info("Requested deps: %s", requested_deps)
        to_install = [dep for dep in requested_deps if dep not in existing_deps]
        if len(to_install) > 0:
            console.log("[bold green]Installing missing deps...")
            config = {
                "command": "uv",
                "params": ["add"] + to_install,
                "folder": sandbox_dir,
            }
            result = execute_command(config)
            if result["exit_code"] != 0:
                agent_log.error(result)
                raise ValueError("Failed to add dependencies to project config.")
        else:
            if opts.verbose > 1:
                agent_log.info("Dependencies already installed.")

        to_remove = [dep for dep in existing_deps if dep not in requested_deps]
        if len(to_remove) > 0:
            console.log("[bold green]Removing unused deps...")
            if opts.verbose > 1:
                agent_log.info("Removing dependencies: %s", to_remove)
            config = {
                "command": "uv",
                "params": ["remove"] + to_remove,
                "folder": sandbox_dir,
            }
            result = execute_command(config)
            if result["exit_code"] != 0:
                agent_log.error(result)
                raise ValueError("Failed to remove dependencies from project config.")

    load_existing_tools(state)
    shutil.copytree(Path("./sandbox_init"), sandbox_dir, dirs_exist_ok=True)
    # (state["sandbox_dir"] / ".gitignore").write_text(
    #     Path("./sandbox.gitignore").read_text(encoding="utf-8")
    # )
    if (state["sandbox_dir"] / ".git").exists():
        repo = Repo(state["sandbox_dir"])  # type: ignore
    else:
        console.log("[bold green]Initializing git...")
        repo = Repo.init(state["sandbox_dir"])  # type: ignore
        repo.index.add(repo.untracked_files)
        repo.index.commit("Initial commit")

    return {
        "call_stack": ["sync_venv"],
        "sandbox_dir": sandbox_dir,
    }
