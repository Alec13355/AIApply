from __future__ import annotations

import httpx

from ._html import strip_html
from .base import JobPosting

BASE_URL = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"


def fetch_postings(slug: str, *, auto_apply_eligible: bool = True) -> list[JobPosting]:
    """Fetch open postings from a company's public Greenhouse job board."""
    resp = httpx.get(
        BASE_URL.format(slug=slug), params={"content": "true"}, timeout=30
    )
    resp.raise_for_status()
    data = resp.json()

    postings = []
    for job in data.get("jobs", []):
        postings.append(
            JobPosting(
                board="greenhouse",
                company=slug,
                external_id=str(job["id"]),
                title=job.get("title", ""),
                location=(job.get("location") or {}).get("name", ""),
                url=job.get("absolute_url", ""),
                description_text=strip_html(job.get("content", "")),
                auto_apply_eligible=auto_apply_eligible,
            )
        )
    return postings
