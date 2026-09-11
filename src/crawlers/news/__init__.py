"""News source adapters."""

from src.crawlers.news.base import NewsCandidate, RSSNewsAdapter
from src.crawlers.news.google_ai import GoogleAINewsAdapter
from src.crawlers.news.mit_technology_review import MITTechnologyReviewNewsAdapter
from src.crawlers.news.openai import OpenAINewsAdapter
from src.crawlers.news.techcrunch import TechCrunchNewsAdapter
from src.crawlers.news.venturebeat import VentureBeatNewsAdapter

__all__ = [
    "NewsCandidate",
    "RSSNewsAdapter",
    "TechCrunchNewsAdapter",
    "VentureBeatNewsAdapter",
    "MITTechnologyReviewNewsAdapter",
    "OpenAINewsAdapter",
    "GoogleAINewsAdapter",
]
