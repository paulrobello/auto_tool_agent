"""Get current date and time in UTC tool"""

from datetime import datetime, timezone

from langchain_core.tools import tool


@tool
def get_now() -> str:
    """
    Get current date and time

    Returns:
        str: The current date and time
    """

    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
