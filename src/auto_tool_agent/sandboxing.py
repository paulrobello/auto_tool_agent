"""AI Sandboxing TOOLS"""

from __future__ import annotations

import shutil
from pathlib import Path

from auto_tool_agent.opts import opts
from auto_tool_agent.lib.session import session


def clear_output_folder() -> None:
    """
    Clear the output folder
    """
    output_dir = opts.sandbox_dir / session.id
    if output_dir.exists():
        shutil.rmtree(output_dir)
        output_dir.mkdir()


def create_session_folder() -> bool:
    """
    Create session folder inside of output folder

    Returns:
        bool: True if successful, False otherwise
    """
    folder_name = opts.sandbox_dir / session.id
    folder_name.makedirs(parents=True, exist_ok=True)
    return True


def read_env_file(filename: Path) -> dict[str, str]:
    """
    Read environment variables from a file into a dictionary

    Args:
        filename (str): The name of the file to read

    Returns:
        Dict[str, str]: A dictionary containing the environment variables
    """
    env_vars = {}
    if not filename.exists():
        return env_vars
    with open(filename, "rt", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or not "=" in line:
                continue
            try:
                key, value = line.split("=", 1)
                env_vars[key.strip()] = value.strip()
            except Exception as e:  # pylint: disable=broad-except
                print(f"Error: {e} --- line {line}")
    return env_vars
