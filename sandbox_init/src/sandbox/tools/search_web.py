"""Web Search"""

from __future__ import annotations

import os

from typing import Union, List, Any
from urllib.parse import quote
import requests

from langchain_core.tools import tool


@tool
def search_web(query: str) -> Union[str, List[Any]]:
    """
    Search the web using google search

    Args:
        query (str): The search query

    Returns:
        Union[str, List[Any]]: List of search results or error message
    """

    try:
        if not (os.getenv("GOOGLE_CSE_API_KEY") and os.getenv("GOOGLE_CSE_ID")):
            raise ValueError("GOOGLE_CSE_API_KEY or GOOGLE_CSE_ID not set")

        url = f"https://customsearch.googleapis.com/customsearch/v1?c2coff=1&key={os.getenv('GOOGLE_CSE_API_KEY')}&cx={os.getenv('GOOGLE_CSE_ID')}&hl=english&safe=off&num=3&q={quote(query, safe='')}"

        response = requests.get(url, stream=True, timeout=10)
        response.raise_for_status()
        return response.json()["items"]
    except Exception as error:  # pylint: disable=broad-except
        return str(error)
