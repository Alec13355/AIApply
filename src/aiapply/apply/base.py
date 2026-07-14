from __future__ import annotations

from dataclasses import dataclass, field


class NeedsManualReview(Exception):
    """A required field can't be safely auto-answered (no screening_answers
    entry for a sensitive question, or an unrecognized widget). The
    application is not submitted when this is raised."""


class CaptchaBlocked(Exception):
    """A CAPTCHA challenge appeared and blocked submission. We never attempt
    to solve or bypass it -- this always ends the attempt."""


@dataclass
class ApplicationResult:
    status: str  # "success" | "captcha_blocked" | "needs_manual_review" | "failure"
    fields_filled: dict = field(default_factory=dict)
    answers: dict = field(default_factory=dict)
    error_message: str | None = None
    screenshot_path: str | None = None
