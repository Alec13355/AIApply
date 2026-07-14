from __future__ import annotations

import time
from pathlib import Path

from playwright.sync_api import Page

from ..azure_client import AzureAIClient
from ..config import Profile
from ..discovery.base import JobPosting
from ..paths import SCREENSHOTS_DIR
from ..resume import ParsedResume
from ._captcha import is_captcha_challenge_visible
from ._form_filler import fill_labeled_field, normalize_label
from .base import ApplicationResult, CaptchaBlocked, NeedsManualReview

HANDLED_LABELS = {
    "Full name", "Email", "Phone", "Current company", "Current location",
    "Resume/CV", "LinkedIn URL", "Github URL", "Other Website URL", "Video Link URL",
}


def _screenshot(page: Page, posting: JobPosting, suffix: str) -> str:
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    path = SCREENSHOTS_DIR / f"lever_{posting.external_id}_{suffix}_{int(time.time())}.png"
    page.screenshot(path=str(path), full_page=True)
    return str(path)


def apply(
    page: Page,
    posting: JobPosting,
    resume: ParsedResume,
    resume_path: Path,
    profile: Profile,
    client: AzureAIClient,
    *,
    dry_run: bool = False,
) -> ApplicationResult:
    fields_filled: dict = {}
    answers_out: dict = {}

    page.goto(posting.url, timeout=30000)
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(1500)

    if not page.url.rstrip("/").endswith("/apply"):
        apply_link = page.get_by_role("link", name="Apply for this job", exact=False)
        if apply_link.count() == 0:
            apply_link = page.get_by_role("link", name="Apply", exact=False)
        apply_link.first.click()
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(1500)

    page.get_by_label("Full name", exact=False).fill(resume.name)
    page.get_by_label("Email", exact=False).fill(resume.email)
    fields_filled.update({"name": resume.name, "email": resume.email})

    phone_field = page.get_by_label("Phone", exact=False)
    if phone_field.count() > 0 and resume.phone:
        phone_field.fill(resume.phone)
        fields_filled["phone"] = resume.phone

    org_field = page.get_by_label("Current company", exact=False)
    if org_field.count() > 0:
        current_company = resume.experience[0].company if resume.experience else ""
        org_field.fill(current_company)
        fields_filled["org"] = current_company

    location_field = page.get_by_label("Current location", exact=False)
    if location_field.count() > 0 and resume.location:
        location_field.fill(resume.location)
        fields_filled["location"] = resume.location

    link_fields = {
        "LinkedIn URL": resume.links.linkedin,
        "Github URL": resume.links.github,
        "Other Website URL": resume.links.portfolio,
    }
    for label, value in link_fields.items():
        if not value:
            continue
        field_locator = page.get_by_label(label, exact=False)
        if field_locator.count() > 0:
            field_locator.fill(value)
            fields_filled[label] = value

    resume_input = page.locator("#resume-upload-input")
    if resume_input.count() > 0:
        resume_input.set_input_files(str(resume_path))
        fields_filled["resume"] = str(resume_path)

    # Radio/checkbox groups (pronouns, EEO gender/race/veteran/disability) are
    # intentionally left untouched by the generic filler below -- see
    # apply/_form_filler.py. They're all optional self-identification fields
    # on Lever; leaving them blank is the safe default.

    try:
        label_texts = {normalize_label(t) for t in page.locator("label").all_inner_texts()}
    except Exception:
        label_texts = set()

    for label_text in sorted(label_texts):
        if not label_text or label_text in HANDLED_LABELS:
            continue
        try:
            fill_labeled_field(
                page,
                label_text,
                profile=profile,
                client=client,
                resume=resume,
                posting=posting,
                answers_out=answers_out,
            )
        except NeedsManualReview:
            raise
        except Exception:
            continue

    if dry_run:
        screenshot = _screenshot(page, posting, "dry_run")
        return ApplicationResult(
            status="success",
            fields_filled=fields_filled,
            answers=answers_out,
            screenshot_path=screenshot,
            error_message="dry_run: form filled, submit button not clicked",
        )

    submit_button = page.get_by_role("button", name="Submit application", exact=False)
    if submit_button.count() == 0:
        submit_button = page.get_by_role("button", name="Submit", exact=False)
    submit_button.first.click()
    page.wait_for_timeout(2000)

    if is_captcha_challenge_visible(page):
        screenshot = _screenshot(page, posting, "captcha_blocked")
        raise CaptchaBlocked(
            f"CAPTCHA challenge blocked submission for {posting.url}; screenshot: {screenshot}"
        )

    page.wait_for_timeout(3000)
    success = page.get_by_text("Thank you", exact=False).count() > 0 or page.get_by_text(
        "successfully submitted", exact=False
    ).count() > 0

    if not success:
        screenshot = _screenshot(page, posting, "unconfirmed")
        return ApplicationResult(
            status="failure",
            fields_filled=fields_filled,
            answers=answers_out,
            screenshot_path=screenshot,
            error_message="No confirmation detected after submit",
        )

    return ApplicationResult(status="success", fields_filled=fields_filled, answers=answers_out)
