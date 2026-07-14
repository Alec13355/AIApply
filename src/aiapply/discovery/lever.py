from __future__ import annotations

import httpx

from ._html import strip_html
from .base import JobPosting

BASE_URL = "https://api.lever.co/v0/postings/{slug}"


def fetch_postings(slug: str, *, auto_apply_eligible: bool = True) -> list[JobPosting]:
    """Fetch open postings from a company's public Lever job board."""
    resp = httpx.get(
        BASE_URL.format(slug=slug), params={"mode": "json"}, timeout=30
    )
    resp.raise_for_status()
    data = resp.json()

    postings = []
    for job in data:
        categories = job.get("categories") or {}
        description = job.get("descriptionPlain") or strip_html(job.get("description", ""))
        postings.append(
            JobPosting(
                board="lever",
                company=slug,
                external_id=str(job["id"]),
                title=job.get("text", ""),
                location=categories.get("location", ""),
                url=job.get("hostedUrl", ""),
                description_text=description,
                auto_apply_eligible=auto_apply_eligible,
            )
        )
    return postings
