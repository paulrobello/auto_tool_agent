from typing import List, Dict, Tuple, Optional
import os
from langchain_core.tools import tool


@tool
def get_env_vars(var_names: List[str]) -> Tuple[Optional[str], Dict[str, str]]:
    """
    Retrieve values for specified environment variables.

    Args:
        var_names (List[str]): A list of environment variable names to retrieve.

    Returns:
        Tuple[Optional[str],Dict[str, str]]: First element is an error message if an error occurred, second element is a dictionary of environment variable names and their values.
    """
    try:
        env_vars = {name: os.getenv(name, "") for name in var_names}
        return None, env_vars
    except Exception as error:  # pylint: disable=broad-except
        return str(error), {}
