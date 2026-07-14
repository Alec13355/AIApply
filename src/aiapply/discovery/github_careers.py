from __future__ import annotations

import httpx

from ._html import strip_html
from .base import JobPosting

# GitHub's own careers site (Jibe front-end over iCIMS), not a generic
# per-tenant vendor API like Greenhouse/Lever -- this module is hardcoded to
# this one company's real, verified endpoint shape, not a reusable "icims"
# integration.
API_URL = "https://www.github.careers/api/jobs"
PAGE_SIZE = 10
MAX_PAGES = 50  # defensive cap -- pagination stops earlier via totalCount in practice

# A bare/default client User-Agent gets a 403 from this endpoint; a normal
# browser UA does not.
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    )
}


def fetch_postings(slug: str, *, auto_apply_eligible: bool = True) -> list[JobPosting]:
    """Fetch open postings from GitHub's careers site.

    `slug` is accepted for interface parity with the greenhouse/lever
    fetchers (dispatch is `_FETCHERS[entry.board](entry.slug, ...)`) but is
    unused -- this module targets one hardcoded company site, not a
    per-tenant API addressed by slug.
    """
    postings = []
    page = 1
    total_count = None

    while page <= MAX_PAGES:
        resp = httpx.get(
            API_URL,
            params={"page": page, "sortBy": "relevance", "descending": "false", "internal": "false"},
            headers=_HEADERS,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        jobs = data.get("jobs", [])
        if not jobs:
            break
        total_count = data.get("totalCount", total_count)

        for job in jobs:
            d = job.get("data", {})
            postings.append(
                JobPosting(
                    board="github",
                    company="github",
                    external_id=str(d["req_id"]),
                    title=d.get("title", ""),
                    location=d.get("location_name", ""),
                    url=(d.get("meta_data") or {}).get("canonical_url", ""),
                    description_text=strip_html(d.get("description", "")),
                    auto_apply_eligible=auto_apply_eligible,
                )
            )

        if total_count is not None and page * PAGE_SIZE >= total_count:
            break
        page += 1

    return postings
