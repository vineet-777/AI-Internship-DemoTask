from src.crawlers.jobs.base import RSSJobAdapter


class GreenhouseJobsAdapter(RSSJobAdapter):
    def __init__(self, http_client):
        super().__init__("greenhouse_ai", "Greenhouse AI Jobs", "https://job-boards.greenhouse.io/rss", http_client)
