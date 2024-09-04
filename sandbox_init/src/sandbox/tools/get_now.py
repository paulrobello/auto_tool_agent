"""Get current date and time in UTC tool"""

from datetime import datetime, timezone
from typing import Tuple, Optional

from langchain_core.tools import tool


@tool
def get_now() -> Tuple[Optional[str], str]:
    """
    Get current date and time

    Returns:
        Tuple[Optional[str], str]: First element is an error message if an error occurred, second element is the current date and time
    """

    return None, datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
