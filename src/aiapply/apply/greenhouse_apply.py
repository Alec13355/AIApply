from __future__ import annotations

import tempfile
import time
from pathlib import Path

from playwright.sync_api import Page

from ..azure_client import AzureAIClient
from ..config import Profile
from ..discovery.base import JobPosting
from ..paths import SCREENSHOTS_DIR
from ..resume import ParsedResume
from . import answers as answers_mod
from ._captcha import is_captcha_challenge_visible
from ._form_filler import fill_labeled_field, normalize_label
from .base import ApplicationResult, CaptchaBlocked, NeedsManualReview

# "Country" is the dial-code picker glued to the Phone field's intl-tel-input
# widget, not a real application question -- distinct from e.g. "What is
# your current country of residence?" which IS a real question we do answer.
HANDLED_LABELS = {"First Name", "Last Name", "Email", "Phone", "Attach", "Country"}


def _screenshot(page: Page, posting: JobPosting, suffix: str) -> str:
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    path = SCREENSHOTS_DIR / f"greenhouse_{posting.external_id}_{suffix}_{int(time.time())}.png"
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

    apply_button = page.get_by_role("button", name="Apply", exact=False)
    if apply_button.count() > 0:
        apply_button.first.click()
        page.wait_for_timeout(1000)

    first_name, _, last_name = resume.name.partition(" ")
    page.get_by_label("First Name", exact=False).fill(first_name)
    page.get_by_label("Last Name", exact=False).fill(last_name or first_name)
    page.get_by_label("Email", exact=False).fill(resume.email)
    fields_filled.update({"first_name": first_name, "last_name": last_name, "email": resume.email})

    phone_field = page.get_by_label("Phone", exact=False)
    if phone_field.count() > 0 and resume.phone:
        phone_field.fill(resume.phone)
        fields_filled["phone"] = resume.phone

    resume_input = page.locator("#resume")
    if resume_input.count() > 0:
        resume_input.set_input_files(str(resume_path))
        fields_filled["resume"] = str(resume_path)

    cover_letter_input = page.locator("#cover_letter")
    if cover_letter_input.count() > 0:
        is_required = cover_letter_input.evaluate("el => el.required")
        if is_required:
            cover_letter_text = answers_mod.generate_cover_letter(client, resume, posting)
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".txt", delete=False, prefix="cover_letter_"
            ) as f:
                f.write(cover_letter_text)
                cover_letter_path = f.name
            cover_letter_input.set_input_files(cover_letter_path)
            fields_filled["cover_letter"] = cover_letter_path

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
            continue  # best-effort: skip fields we can't confidently handle

    if dry_run:
        screenshot = _screenshot(page, posting, "dry_run")
        return ApplicationResult(
            status="success",
            fields_filled=fields_filled,
            answers=answers_out,
            screenshot_path=screenshot,
            error_message="dry_run: form filled, submit button not clicked",
        )

    submit_button = page.get_by_role("button", name="Submit Application", exact=False)
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
    success = "confirmation" in page.url or page.get_by_text(
        "Thank you", exact=False
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
