from src.crawlers.news.base import RSSNewsAdapter


class TechCrunchNewsAdapter(RSSNewsAdapter):
    def __init__(self, http_client):
        super().__init__("techcrunch_ai", "TechCrunch AI", "https://techcrunch.com/category/artificial-intelligence/feed/", http_client)
