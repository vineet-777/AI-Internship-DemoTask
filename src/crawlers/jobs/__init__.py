"""Job-board source adapters."""

from src.crawlers.jobs.base import JobCandidate, RSSJobAdapter
from src.crawlers.jobs.ai_jobs import AIJobsAdapter
from src.crawlers.jobs.greenhouse import GreenhouseJobsAdapter
from src.crawlers.jobs.lever import LeverJobsAdapter
from src.crawlers.jobs.remoteok import RemoteOKJobsAdapter
from src.crawlers.jobs.wework_remotely import WeWorkRemotelyJobsAdapter

__all__ = [
    "JobCandidate",
    "RSSJobAdapter",
    "AIJobsAdapter",
    "GreenhouseJobsAdapter",
    "LeverJobsAdapter",
    "RemoteOKJobsAdapter",
    "WeWorkRemotelyJobsAdapter",
]
