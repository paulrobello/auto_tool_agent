"""Execute a command and return the result."""

from __future__ import annotations

import subprocess
import os
from rich import print  # pylint: disable=redefined-builtin


def execute_command(config: dict) -> dict:
    """Execute a command and return the result."""
    # Extract values from the config dictionary
    command = config.get("command")
    params = config.get("params", [])
    folder = config.get("folder", ".")

    # Ensure the folder exists and is a directory
    if not os.path.isdir(folder):
        raise ValueError(
            f"Specified folder '{folder}' does not exist or is not a directory."
        )

    # Change the working directory
    original_directory = os.getcwd()
    os.chdir(folder)

    try:
        # Execute the command
        result = subprocess.run(
            [command] + params, text=True, capture_output=True, check=False
        )

        # Return the result as a dictionary
        ret = {
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
        print(ret)

        return ret

    finally:
        # Change back to the original working directory
        os.chdir(original_directory)
