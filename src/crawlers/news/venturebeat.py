from src.crawlers.news.base import RSSNewsAdapter


class VentureBeatNewsAdapter(RSSNewsAdapter):
    def __init__(self, http_client):
        super().__init__("venturebeat_ai", "VentureBeat AI", "https://venturebeat.com/category/ai/feed/", http_client)
