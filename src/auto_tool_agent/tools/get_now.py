"""Get current date and time in UTC tool"""

from datetime import UTC, datetime

from langchain_core.tools import tool


@tool
def get_now(query: str) -> str:  # pylint: disable=unused-argument
    """
    Get current date and time

    Args:
        query (str): ignored

    Returns:
        str: The current date and time
    """

    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%SZ")
