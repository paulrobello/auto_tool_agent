from langchain_core.tools import tool
import requests


@tool
def fetch_hacker_news_top_articles() -> dict:
    """
    Fetch the top 3 articles from Hacker News.
    Returns a dictionary with the titles and URLs of the top 3 articles.
    """
    try:
        response = requests.get("https://hacker-news.firebaseio.com/v0/topstories.json")
        response.raise_for_status()
        top_story_ids = response.json()[:3]

        articles = []
        for story_id in top_story_ids:
            story_response = requests.get(
                f"https://hacker-news.firebaseio.com/v0/item/{story_id}.json"
            )
            story_response.raise_for_status()
            story = story_response.json()
            articles.append({"title": story["title"], "url": story["url"]})

        return {"articles": articles}
    except Exception as error:
        return {"error": str(error)}
