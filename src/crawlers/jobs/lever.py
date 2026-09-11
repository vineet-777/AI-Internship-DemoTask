from src.crawlers.jobs.base import RSSJobAdapter


class LeverJobsAdapter(RSSJobAdapter):
    def __init__(self, http_client):
        super().__init__("lever_ai", "Lever AI Jobs", "https://jobs.lever.co/rss", http_client)
