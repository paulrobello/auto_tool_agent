from typing import Optional

from .main import dotenv_values, find_dotenv, get_key, load_dotenv, set_key, unset_key


def get_cli_string(
    path: str | None = None,
    action: str | None = None,
    key: str | None = None,
    value: str | None = None,
    quote: str | None = None,
):
    """Returns a string suitable for running as a shell script.

    Useful for converting a arguments passed to a fabric task
    to be passed to a `local` or `run` command.
    """
    command = ["dotenv"]
    if quote:
        command.append(f"-q {quote}")
    if path:
        command.append(f"-f {path}")
    if action:
        command.append(action)
        if key:
            command.append(key)
            if value:
                if " " in value:
                    command.append(f'"{value}"')
                else:
                    command.append(value)

    return " ".join(command).strip()


__all__ = [
    "get_cli_string",
    "load_dotenv",
    "dotenv_values",
    "get_key",
    "set_key",
    "unset_key",
    "find_dotenv",
]
