from src.crawlers.news.base import RSSNewsAdapter


class MITTechnologyReviewNewsAdapter(RSSNewsAdapter):
    def __init__(self, http_client):
        super().__init__("mit_technology_review_ai", "MIT Technology Review AI", "https://www.technologyreview.com/topic/artificial-intelligence/feed/", http_client)
