"""Sandbox related nodes for graph agent."""

from __future__ import annotations

import os
import shutil
from typing import cast

import tomlkit
from tomlkit.items import Table, Array

from auto_tool_agent.graph.graph_shared import agent_log, load_existing_tools
from auto_tool_agent.graph.graph_state import GraphState
from auto_tool_agent.lib.execute_command import execute_command


def setup_sandbox(state: GraphState):
    """Entrypoint."""
    sandbox_dir = os.path.expanduser(state["sandbox_dir"]).replace("\\", "/")

    if state["clean_run"] and os.path.exists(sandbox_dir):
        agent_log.info("Removing old sandbox: %s", sandbox_dir)
        shutil.rmtree(sandbox_dir)

    if not os.path.exists(sandbox_dir):
        agent_log.info("Sandbox path not found, creating...")
        os.makedirs(sandbox_dir)

    agent_log.info("Sandbox path: %s", sandbox_dir)
    return {
        "call_stack": ["entrypoint"],
        "sandbox_dir": sandbox_dir,
    }


# pylint: disable=too-many-statements
def sync_venv(state: GraphState):
    """Sync the venv."""
    agent_log.info("Syncing venv...")
    sandbox_dir = state["sandbox_dir"]
    project_config = os.path.join(sandbox_dir, "pyproject.toml")

    if not os.path.exists(project_config):
        agent_log.info("Project config not found, creating...")
        config = {"command": "uv", "params": ["init"], "folder": sandbox_dir}
        result = execute_command(config)
        if result["exit_code"] != 0:
            agent_log.error(result)
            raise ValueError("Failed to create project config.")

        # Update project
        with open(project_config, "rt", encoding="utf-8") as f:
            project_toml = tomlkit.parse(f.read())
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

        with open(project_config, "wt", encoding="utf-8") as f:
            f.write(tomlkit.dumps(project_toml))

    with open(project_config, "rt", encoding="utf-8") as f:
        project_toml = tomlkit.parse(f.read())
    project = cast(Table, project_toml["project"])
    existing_deps = project.get("dependencies") or []
    existing_deps = [
        dep.split(">")[0].split("<")[0].split("=")[0].strip().split("^")[0].strip()
        for dep in existing_deps
    ]
    existing_deps.sort()
    agent_log.info("Existing deps: %s", existing_deps)

    if len(state["dependencies"]) > 0:
        requested_deps = state["dependencies"]
        requested_deps.sort()
        agent_log.info("Requested deps: %s", requested_deps)
        to_install = [dep for dep in requested_deps if dep not in existing_deps]
        if len(to_install) > 0:
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
            agent_log.info("Dependencies already installed.")

        to_remove = [dep for dep in existing_deps if dep not in requested_deps]
        if len(to_remove) > 0:
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

    return {
        "call_stack": ["sync_venv"],
        "sandbox_dir": sandbox_dir,
    }
