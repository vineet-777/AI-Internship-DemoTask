from src.crawlers.jobs.base import RSSJobAdapter


class RemoteOKJobsAdapter(RSSJobAdapter):
    def __init__(self, http_client):
        super().__init__("remoteok_ai", "Remote OK AI Jobs", "https://remoteok.com/remote-ai-jobs.rss", http_client)
