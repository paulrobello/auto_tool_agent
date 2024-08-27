"""AI Sandboxing TOOLS"""

from __future__ import annotations

import os
import shutil

from auto_tool_agent.__main__ import session


# sandbox_base = os.path.join(os.path.abspath(os.path.dirname(__file__)), "sandbox")


def clear_output_folder() -> None:
    """
    Clear the output folder
    """
    output_dir = os.path.join(session.opts.sandbox_dir, session.id)
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
        os.makedirs(output_dir)


def create_session_folder() -> bool:
    """
    Create session folder inside of output folder

    Returns:
        bool: True if successful, False otherwise
    """
    folder_name = os.path.join(session.opts.sandbox_dir, session.id)
    os.makedirs(folder_name, exist_ok=True)
    return True


def read_env_file(filename: str) -> dict[str, str]:
    """
    Read environment variables from a file into a dictionary

    Args:
        filename (str): The name of the file to read

    Returns:
        Dict[str, str]: A dictionary containing the environment variables
    """
    env_vars = {}
    if not os.path.exists(filename):
        return env_vars
    with open(filename, "r", encoding="utf-8") as f:
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
