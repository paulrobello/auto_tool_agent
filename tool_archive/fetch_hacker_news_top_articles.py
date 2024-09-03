from typing import Optional, Union

from langchain_core.tools import tool
import requests


@tool
def fetch_hacker_news_top_articles(
    limit: Optional[int] = 5,
) -> Union[str, dict[str, str]]:
    """
    Fetch the  articles from Hacker News.

    :arg limit: The number of articles to fetch or None to fetch all. Defaults to 5
    :returns: A list of articles or an error message
    """
    try:
        response = requests.get(
            "https://hacker-news.firebaseio.com/v0/topstories.json", timeout=10
        )
        response.raise_for_status()
        top_story_ids = response.json()

        if limit is not None:
            top_story_ids = top_story_ids[:limit]

        articles = []
        for story_id in top_story_ids:
            story_response = requests.get(
                f"https://hacker-news.firebaseio.com/v0/item/{story_id}.json"
            )
            story_response.raise_for_status()
            story = story_response.json()
            articles.append({"title": story["title"], "url": story["url"]})

        return {"results": articles}
    except Exception as error:
        return str(error)
