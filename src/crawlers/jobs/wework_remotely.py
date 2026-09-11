from src.crawlers.jobs.base import RSSJobAdapter


class WeWorkRemotelyJobsAdapter(RSSJobAdapter):
    def __init__(self, http_client):
        super().__init__("wework_remotely_ai", "We Work Remotely AI Jobs", "https://weworkremotely.com/categories/remote-programming-jobs.rss", http_client)
