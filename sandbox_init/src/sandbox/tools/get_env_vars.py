from typing import List, Dict, Union
import os
from langchain_core.tools import tool


@tool
def get_env_vars(var_names: List[str]) -> Union[str, Dict[str, str]]:
    """
    Takes a list of environment variable names and returns a dictionary with the names and values of the environment variables.
    Uses an empty string as the default value for variables that do not exist.

    Args:
    var_names (List[str]): List of environment variable names to retrieve.

    Returns:
    Union[str, Dict[str, str]]: Dictionary with environment variable names and their values or an error message as a string.
    """
    try:
        env_vars = {name: os.getenv(name, "") for name in var_names}
        return env_vars
    except Exception as error:  # pylint: disable=broad-except
        return str(error)
