from src.crawlers.jobs.base import RSSJobAdapter


class AIJobsAdapter(RSSJobAdapter):
    def __init__(self, http_client):
        super().__init__("ai_jobs", "AI Jobs", "https://ai-jobs.net/rss/", http_client)
