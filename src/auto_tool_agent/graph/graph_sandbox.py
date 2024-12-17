"""Sandbox related nodes for graph agent."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import cast

import tomlkit
from git import Repo
from tomlkit.items import Table

from auto_tool_agent.app_logging import agent_log, console, global_vars
from auto_tool_agent.graph.graph_shared import (
    commit_leftover_changes,
    git_actor,
    load_existing_tools,
)
from auto_tool_agent.graph.graph_state import GraphState
from auto_tool_agent.lib.execute_command import execute_command
from auto_tool_agent.opts import opts


def create_project_if_not_exist() -> None:
    """Create sandbox project if not exists."""

    sandbox_dir = opts.sandbox_dir
    project_config = sandbox_dir / "pyproject.toml"

    if project_config.exists():
        return

    global_vars.status_update("[bold green]Project config not found, creating...")
    config = {"command": "uv", "params": ["init"], "folder": sandbox_dir}
    result = execute_command(config)
    if result["exit_code"] != 0:
        agent_log.error(result)
        raise ValueError("Failed to create project config.")
    # Remove default hello.py
    (Path(sandbox_dir) / "hello.py").unlink()
    shutil.copytree(Path("./sandbox_init"), sandbox_dir, dirs_exist_ok=True)

    # Update project
    # project_toml = tomlkit.parse(project_config.read_text(encoding="utf-8"))
    # project = cast(Table, project_toml["project"])
    # project["description"] = "AI Auto Tool Agent"
    #
    # # Add package section
    # project["packages"] = cast(Array, tomlkit.array())
    # tab = tomlkit.inline_table()
    # tab.add("include", "src/sandbox")
    # project["packages"].insert(0, tab)  # pyright: ignore
    #
    # project_config.write_text(tomlkit.dumps(project_toml))

    if not (sandbox_dir / ".git").exists():
        global_vars.status_update("[bold green]Initializing git repo...")
        Repo.init(sandbox_dir)


def sync_master_venv(dependencies: list[str]):
    """Sync the master venv."""
    global_vars.status_update("Checking master venv...")

    sandbox_dir = Path(".").absolute()

    project_config = sandbox_dir / "pyproject.toml"
    if not project_config.exists():
        raise ValueError("Master project config not found.", project_config)
    project_toml = tomlkit.parse(project_config.read_text(encoding="utf-8"))
    project = cast(Table, project_toml["project"])
    project_deps = project.get("dependencies") or []
    # existing_deps: set[str] = {
    #     dep.split(">")[0].split("<")[0].split("=")[0].strip().split("^")[0].strip()
    #     for dep in project_deps
    # }
    existing_deps = set(project_deps)
    requested_deps: set[str] = set[str](dependencies)

    if opts.verbose > 2:
        agent_log.info("Master existing deps: %s", existing_deps)
        agent_log.info("Master requested deps: %s", requested_deps)

    if requested_deps != existing_deps:
        to_install = list(requested_deps - existing_deps)
        if len(to_install) > 0:
            global_vars.status_update(f"[bold green]Master installing missing deps:[/bold green] {to_install}")
            config = {
                "command": "uv",
                "params": ["add"] + to_install,
                "folder": sandbox_dir,
            }
            result = execute_command(config)
            if result["exit_code"] != 0:
                agent_log.error(result)
                raise ValueError("Failed to add dependencies to Master project config.")

    else:
        if opts.verbose > 2:
            agent_log.info("Master dependencies already in sync.")


# pylint: disable=too-many-statements, too-many-branches
def sync_venv(dependencies: list[str]):
    """Sync the sandbox venv."""
    global_vars.status_update("Checking sandbox venv...")

    sandbox_dir = opts.sandbox_dir

    project_config = sandbox_dir / "pyproject.toml"
    project_toml = tomlkit.parse(project_config.read_text(encoding="utf-8"))
    project = cast(Table, project_toml["project"])
    project_deps = project.get("dependencies") or []
    # existing_deps: set[str] = {
    #     dep.split(">")[0].split("<")[0].split("=")[0].strip().split("^")[0].strip()
    #     for dep in project_deps
    # }
    existing_deps = set(project_deps)
    requested_deps: set[str] = set[str](dependencies)

    if opts.verbose > 1:
        agent_log.info("Sandbox existing deps: %s", existing_deps)
        agent_log.info("Sandbox requested deps: %s", requested_deps)

    if requested_deps != existing_deps:
        # to_remove = list(existing_deps - requested_deps)
        # if len(to_remove) > 0:
        #     global_vars.status_update(f"Sandbox removing unused deps: {to_remove}")
        #     config = {
        #         "command": "uv",
        #         "params": ["remove"] + to_remove,
        #         "folder": sandbox_dir,
        #     }
        #     result = execute_command(config)
        #     if result["exit_code"] != 0:
        #         agent_log.error(result)
        #         raise ValueError("Failed to remove dependencies from project config.")

        to_install = list(requested_deps - existing_deps)
        if len(to_install) > 0:
            global_vars.status_update(f"Sandbox installing missing deps: {to_install}")
            config = {
                "command": "uv",
                "params": ["add", "-U"] + to_install,
                "folder": sandbox_dir,
            }
            # console.log(config)
            result = execute_command(config)
            if result["exit_code"] != 0:
                console.log(result["stderr"])
                raise ValueError("Failed to add dependencies to project config.")

    else:
        if opts.verbose > 2:
            agent_log.info("Sandbox dependencies already in sync.")

    # exit(1)
    repo = Repo(sandbox_dir)
    # if next(repo.iter_commits(), None) is None:
    if "main" not in [head.name for head in repo.heads]:
        global_vars.status_update("Creating initial commit...")
        repo.index.add(repo.untracked_files)
        repo.index.commit("Initial commit", author=git_actor, committer=git_actor)

    commit_leftover_changes(sandbox_dir, "Adding leftovers from last run")

    branch = opts.branch or "main"
    if branch in [head.name for head in repo.heads]:
        global_vars.status_update(f"Checking out branch '{branch}'...")
        repo.git.checkout(opts.branch)
    else:
        global_vars.status_update(f"Creating branch '{branch}'...")
        if "main" in [head.name for head in repo.heads]:
            repo.git.checkout("main")
        repo.git.checkout("HEAD", b=branch)

    sync_master_venv(dependencies)
    load_existing_tools()

    return {"call_stack": ["sync_venv"]}


def setup_sandbox(state: GraphState):
    """setup_sandbox."""
    global_vars.status_update("Checking sandbox...")
    sandbox_dir = opts.sandbox_dir

    if state["clean_run"] and sandbox_dir.exists():
        global_vars.status_update("Removing old sandbox...")
        if opts.verbose > 1:
            agent_log.info("Removing old sandbox: %s", sandbox_dir)
        shutil.rmtree(sandbox_dir)

    if not sandbox_dir.exists():
        global_vars.status_update("Sandbox path not found, creating...")
        sandbox_dir.mkdir(parents=True, exist_ok=True)

    if opts.verbose > 1:
        console.log("[bold green]Sandbox path:", sandbox_dir)

    create_project_if_not_exist()
    sync_venv(state["dependencies"])

    return {"call_stack": ["setup_sandbox"]}
