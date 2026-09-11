from src.crawlers.news.base import RSSNewsAdapter


class GoogleAINewsAdapter(RSSNewsAdapter):
    def __init__(self, http_client):
        super().__init__("google_ai_blog", "Google AI Blog", "https://blog.google/technology/ai/rss/", http_client)
