from __future__ import annotations

from ..config import SitesConfig
from .base import JobPosting
from . import greenhouse, lever, web_search, github_careers

_FETCHERS = {
    "greenhouse": greenhouse.fetch_postings,
    "lever": lever.fetch_postings,
    "github": github_careers.fetch_postings,
}


def discover_whitelisted(sites: SitesConfig) -> list[JobPosting]:
    """Postings from whitelisted company boards -- these are auto-apply eligible."""
    postings: list[JobPosting] = []
    for entry in sites.whitelist:
        fetch = _FETCHERS[entry.board]
        postings.extend(fetch(entry.slug, auto_apply_eligible=True))
    return postings


def discover_surfaced(sites: SitesConfig) -> list[JobPosting]:
    """Postings outside the whitelist -- report-only, never auto-applied."""
    if not sites.discovery.web_search.enabled:
        return []
    return web_search.fetch_postings(sites.discovery.web_search.extra_queries)
