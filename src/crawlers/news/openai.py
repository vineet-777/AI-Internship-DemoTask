from src.crawlers.news.base import RSSNewsAdapter


class OpenAINewsAdapter(RSSNewsAdapter):
    def __init__(self, http_client):
        super().__init__("openai_news", "OpenAI News", "https://openai.com/news/rss.xml", http_client)
