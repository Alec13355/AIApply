from __future__ import annotations

from .base import JobPosting


def fetch_postings(queries: list[str]) -> list[JobPosting]:
    """Broader discovery outside the whitelist, for surfacing only (never auto-applied).

    Not wired to a search API yet -- no key/provider has been chosen. When
    run interactively through Claude Code, ask it to do this step live with
    its own WebSearch tool instead of relying on this stub.
    """
    return []
