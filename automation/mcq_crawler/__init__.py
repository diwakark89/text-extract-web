"""MCQ crawler package."""

from .config import RunConfig, load_selector_profile


async def run_crawl(config: RunConfig):
	from .runner import run_crawl as _run_crawl

	return await _run_crawl(config)

__all__ = ["RunConfig", "load_selector_profile", "run_crawl"]
