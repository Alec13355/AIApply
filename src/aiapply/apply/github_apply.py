from __future__ import annotations

import time

from playwright.sync_api import Page

from ..azure_client import AzureAIClient
from ..config import Profile
from ..discovery.base import JobPosting
from ..paths import SCREENSHOTS_DIR
from ..resume import ParsedResume
from ._captcha import is_captcha_challenge_visible
from .base import ApplicationResult, CaptchaBlocked, NeedsManualReview

# GitHub's apply flow (job page -> "Apply" link -> iCIMS login/consent gate)
# is only partially verified. Every automated attempt during development hit
# an hCaptcha challenge right at the gate, before any application form was
# ever observed -- so unlike greenhouse_apply.py/lever_apply.py, this module
# never reaches a generic per-label filling stage (no _form_filler/answers.py
# usage) and, as shipped, EVERY real run terminates in CaptchaBlocked or
# NeedsManualReview, never "success". That's intentional: guessing at
# unverified post-gate form structure risks silently mis-filling or
# mis-submitting a real application with no human review step in this
# pipeline. Finishing this flow requires a --dry-run --headed session against
# a live posting to observe what's past the gate, per CLAUDE.md's own
# documented practice for building/debugging apply flows.
#
# Guardrail: never interact with any frame whose URL contains "hcaptcha.html"
# (e.g. its own internal "Verify" button) -- that belongs to the CAPTCHA
# widget itself, and touching it would mean attempting to pass the CAPTCHA,
# which this project must never do. All form interaction below stays inside
# the iCIMS content frame (matched via "in_iframe=1" in its URL) only.
#
# Unlike the other boards, this flow opens its own browser context instead of
# using the Page handed in by run.py: GitHub's careers site serves a
# stripped-down page (no Apply link at all, confirmed live) to Playwright's
# default headless UA, which self-identifies as "HeadlessChrome" in both the
# HTTP header and navigator.userAgent. A normal desktop Chrome UA string
# renders the page fully. This changes nothing about automation fingerprints
# that matter for CAPTCHA risk-scoring (navigator.webdriver, CDP artifacts,
# etc. are untouched) -- it only affects whether ordinary page content
# renders at all, which is a prerequisite for even reaching the CAPTCHA gate.

_CONTINUE_BUTTON_NAMES = ["Continue", "Next", "Submit"]

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)


def _screenshot(page: Page, posting: JobPosting, suffix: str) -> str:
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    path = SCREENSHOTS_DIR / f"github_{posting.external_id}_{suffix}_{int(time.time())}.png"
    page.screenshot(path=str(path), full_page=True)
    return str(path)


def _find_content_frame(page: Page):
    for frame in page.frames:
        if "hcaptcha.html" in frame.url:
            continue
        if "in_iframe=1" in frame.url:
            return frame
    return None


def apply(
    page: Page,
    posting: JobPosting,
    resume: ParsedResume,
    resume_path,
    profile: Profile,
    client: AzureAIClient,
    *,
    dry_run: bool = False,
) -> ApplicationResult:
    fields_filled: dict = {}

    context = page.context.browser.new_context(user_agent=_USER_AGENT)
    try:
        gh_page = context.new_page()
        gh_page.goto(posting.url, timeout=30000)
        gh_page.wait_for_load_state("domcontentloaded")
        gh_page.wait_for_timeout(1500)

        # The Apply link renders on a variable delay, so use Playwright's
        # auto-waiting click (not an immediate .count() check, which doesn't
        # wait) to avoid racing the page's own async rendering.
        apply_link = gh_page.get_by_role("link", name="Apply", exact=True)
        try:
            apply_link.first.click(timeout=10000)
        except Exception:
            apply_link = gh_page.get_by_text("Apply", exact=True)
            try:
                apply_link.first.click(timeout=10000)
            except Exception:
                raise NeedsManualReview(f"No Apply link found on {posting.url}")
        gh_page.wait_for_load_state("domcontentloaded")
        gh_page.wait_for_timeout(3000)

        if is_captcha_challenge_visible(gh_page):
            screenshot = _screenshot(gh_page, posting, "captcha_blocked")
            raise CaptchaBlocked(
                f"CAPTCHA challenge blocked the iCIMS application gate for {posting.url}; "
                f"screenshot: {screenshot}"
            )

        content_frame = _find_content_frame(gh_page)
        if content_frame is None:
            screenshot = _screenshot(gh_page, posting, "no_content_frame")
            raise NeedsManualReview(
                f"Could not locate the iCIMS content iframe for {posting.url}; screenshot: {screenshot}"
            )

        email_field = content_frame.get_by_label("Email", exact=False)
        if email_field.count() == 0:
            email_field = content_frame.locator('input[type="email"]')
        if email_field.count() > 0:
            email_field.first.fill(resume.email)
            fields_filled["email"] = resume.email

        consent_checkbox = content_frame.get_by_role("checkbox")
        if consent_checkbox.count() == 1:
            consent_checkbox.first.check()
            fields_filled["consent"] = True

        if dry_run:
            screenshot = _screenshot(gh_page, posting, "dry_run")
            return ApplicationResult(
                status="success",
                fields_filled=fields_filled,
                screenshot_path=screenshot,
                error_message="dry_run: reached iCIMS email/consent step, continue control not clicked",
            )

        continue_button = None
        for name in _CONTINUE_BUTTON_NAMES:
            candidate = content_frame.get_by_role("button", name=name, exact=False)
            if candidate.count() == 1:
                continue_button = candidate.first
                break

        if continue_button is None:
            screenshot = _screenshot(gh_page, posting, "continue_not_found")
            raise NeedsManualReview(
                "iCIMS continue control not found/verified for "
                f"{posting.url} -- needs a headed session to identify it; screenshot: {screenshot}"
            )

        continue_button.click()
        gh_page.wait_for_timeout(2000)

        if is_captcha_challenge_visible(gh_page):
            screenshot = _screenshot(gh_page, posting, "captcha_blocked_after_continue")
            raise CaptchaBlocked(
                f"CAPTCHA challenge blocked submission after continue for {posting.url}; "
                f"screenshot: {screenshot}"
            )

        screenshot = _screenshot(gh_page, posting, "unverified_form")
        raise NeedsManualReview(
            "Reached past the iCIMS CAPTCHA gate and email/consent step for "
            f"{posting.url}, but the application form structure beyond that has not been "
            "verified yet -- run --dry-run --headed against a real posting to observe it "
            f"and extend this flow; screenshot: {screenshot}"
        )
    finally:
        context.close()
