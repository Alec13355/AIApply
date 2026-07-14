from __future__ import annotations

import re

from playwright.sync_api import Page

from ..azure_client import AzureAIClient
from ..config import Profile
from ..discovery.base import JobPosting
from ..resume import ParsedResume
from . import answers as answers_mod
from .base import NeedsManualReview

DECLINE_PATTERNS = ["decline to self-identify", "prefer not", "don't wish", "choose not to"]

# Trailing "required" markers ATSs render after a label: ASCII "*", the
# Unicode heavy-asterisk variants Lever uses, and any whitespace/newlines
# around them.
_TRAILING_REQUIRED_MARKER = re.compile(r"[\s*✱✲✳]+$")


def normalize_label(text: str) -> str:
    return _TRAILING_REQUIRED_MARKER.sub("", text).strip()


def _pick_decline_option(choice_texts: list[str]) -> str | None:
    for text in choice_texts:
        if any(p in text.lower() for p in DECLINE_PATTERNS):
            return text
    return None


def _best_matching_choice(answer: str, choice_texts: list[str]) -> str | None:
    low_answer = answer.strip().lower()
    for text in choice_texts:
        if text.strip().lower() == low_answer:
            return text
    for text in choice_texts:
        if low_answer in text.lower() or text.lower() in low_answer:
            return text
    return None


def resolve_answer(
    label_text: str,
    choice_texts: list[str] | None,
    *,
    profile: Profile,
    client: AzureAIClient,
    resume: ParsedResume,
    posting: JobPosting,
) -> str | None:
    """Returns the text to enter/select, or None to leave the field untouched.
    Raises NeedsManualReview if a sensitive question has no configured answer."""
    category = answers_mod.classify_question(label_text)

    if category == "demographic":
        return _pick_decline_option(choice_texts) if choice_texts else None

    if category == "sensitive":
        configured = answers_mod.screening_answer(label_text, profile)
        if configured is None:
            raise NeedsManualReview(f"No screening_answers entry for: {label_text!r}")
        if choice_texts:
            matched = _best_matching_choice(configured, choice_texts)
            if matched is None:
                raise NeedsManualReview(
                    f"screening_answers value {configured!r} doesn't match any option "
                    f"for {label_text!r}: {choice_texts}"
                )
            return matched
        return configured

    # open-ended
    if choice_texts:
        prompt_choices = "\n".join(f"- {c}" for c in choice_texts)
        result = answers_mod.generate_open_answer(
            client,
            f"{label_text}\n\nChoose exactly one of these options (respond with the "
            f"option text verbatim):\n{prompt_choices}",
            resume,
            posting,
        )
        matched = _best_matching_choice(result, choice_texts)
        if matched is None:
            raise NeedsManualReview(
                f"Could not confidently pick an option for {label_text!r} from {choice_texts}"
            )
        return matched

    return answers_mod.generate_open_answer(client, label_text, resume, posting)


def fill_labeled_field(
    page: Page,
    label_text: str,
    *,
    profile: Profile,
    client: AzureAIClient,
    resume: ParsedResume,
    posting: JobPosting,
    answers_out: dict,
) -> None:
    """Best-effort fill of a single labeled control by its accessible label."""
    control = page.get_by_label(label_text, exact=True)
    if control.count() != 1:
        control = page.get_by_label(label_text, exact=False)
    if control.count() != 1:
        return  # ambiguous or not found -- leave untouched, not worth guessing

    tag = control.evaluate("el => el.tagName")

    if tag == "SELECT":
        choice_texts = [t.strip() for t in control.locator("option").all_inner_texts() if t.strip()]
        answer = resolve_answer(
            label_text, choice_texts, profile=profile, client=client, resume=resume, posting=posting
        )
        if answer is None:
            return
        control.select_option(label=answer)
        answers_out[label_text] = answer
        return

    if tag in ("INPUT", "TEXTAREA"):
        input_type = control.evaluate("el => el.type || ''")
        if input_type in ("checkbox", "radio", "file", "hidden"):
            return  # handled elsewhere / not applicable to plain fill

        role = control.evaluate("el => el.getAttribute('role') || ''")
        choice_texts: list[str] | None = None
        if role == "combobox":
            # Custom-select widgets (e.g. Greenhouse's react-select Yes/No
            # questions) render as a text input but are really a constrained
            # choice -- open it and read the real options rather than typing
            # blind, so we don't record an answer that never actually gets
            # selected in the underlying controlled state.
            control.click()
            options = page.get_by_role("option")
            try:
                options.first.wait_for(state="visible", timeout=1500)
                choice_texts = [t.strip() for t in options.all_inner_texts() if t.strip()]
            except Exception:
                choice_texts = None

        answer = resolve_answer(
            label_text, choice_texts, profile=profile, client=client, resume=resume, posting=posting
        )
        if answer is None:
            return

        if choice_texts:
            option = page.get_by_role("option", name=answer, exact=False)
            if option.count() == 0:
                raise NeedsManualReview(
                    f"Resolved answer {answer!r} for {label_text!r} doesn't match any "
                    f"listbox option: {choice_texts}"
                )
            option.first.click()
            answers_out[label_text] = answer
            return

        control.click()
        control.fill(answer)

        # Some ATS custom questions render as a plain text input that still
        # opens a listbox once text is typed (typeahead) -- if a matching
        # option now appears, click it so the underlying controlled value
        # actually registers instead of sitting as unselected typed text.
        option = page.get_by_role("option", name=answer, exact=False)
        try:
            option.first.wait_for(state="visible", timeout=1500)
            option.first.click()
        except Exception:
            pass

        answers_out[label_text] = answer
