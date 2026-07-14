from __future__ import annotations

import argparse
import traceback

from playwright.sync_api import sync_playwright

from . import discovery, matching, notify
from .apply import APPLY_FNS
from .apply.base import CaptchaBlocked, NeedsManualReview
from .azure_client import AzureAIClient
from .config import load_azure_settings, load_profile, load_sites
from .discovery.base import JobPosting
from .paths import RESUME_PATH
from .resume import parse_resume
from .store import PostingRecord, RunSummary, Store


def _to_record(posting: JobPosting, fit_score: int | None = None, fit_reasoning: str | None = None) -> PostingRecord:
    return PostingRecord(
        posting_key=posting.posting_key,
        board=posting.board,
        company=posting.company,
        title=posting.title,
        url=posting.url,
        auto_apply_eligible=posting.auto_apply_eligible,
        location=posting.location,
        fit_score=fit_score,
        fit_reasoning=fit_reasoning,
    )


def run(dry_run: bool = False, headed: bool = False) -> RunSummary:
    profile = load_profile()
    sites = load_sites()
    client = AzureAIClient(load_azure_settings())
    resume = parse_resume(client)

    store = Store()
    summary = RunSummary()

    try:
        whitelisted = discovery.discover_whitelisted(sites)
        surfaced_candidates = discovery.discover_surfaced(sites)

        eligible: list[tuple[JobPosting, int, str]] = []
        for posting in whitelisted:
            if store.is_known(posting.posting_key):
                continue
            fit = matching.score_posting(client, posting, resume, profile)
            store.upsert_posting(
                _to_record(posting, fit.fit_score, fit.reasoning),
                status="seen",
            )
            if fit.fit_score >= profile.min_fit_score:
                eligible.append((posting, fit.fit_score, fit.reasoning))

        for posting in surfaced_candidates:
            if store.is_known(posting.posting_key):
                continue
            fit = matching.score_posting(client, posting, resume, profile)
            record = _to_record(posting, fit.fit_score, fit.reasoning)
            if fit.fit_score >= profile.min_fit_score:
                store.upsert_posting(record, status="surfaced")
                summary.surfaced.append(record)
            else:
                store.upsert_posting(record, status="seen")

        applied_count = store.applied_count_today()
        consecutive_failures = 0

        if eligible:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=not headed)
                try:
                    for posting, fit_score, fit_reasoning in eligible:
                        record = _to_record(posting, fit_score, fit_reasoning)

                        if applied_count >= profile.daily_application_cap:
                            break  # left as "seen"/eligible -- picked up again next run
                        if consecutive_failures >= profile.circuit_breaker_failures:
                            summary.failed.append(
                                (record, "circuit breaker tripped -- halted remaining applications this run")
                            )
                            break

                        apply_fn = APPLY_FNS[posting.board]
                        page = browser.new_page()
                        try:
                            result = apply_fn(
                                page, posting, resume, RESUME_PATH, profile, client, dry_run=dry_run
                            )
                            store.record_application(
                                record,
                                result="success",
                                fields=result.fields_filled,
                                answers=result.answers,
                                screenshot_path=result.screenshot_path,
                            )
                            store.upsert_posting(record, status="applied")
                            summary.applied.append(record)
                            applied_count += 1
                            consecutive_failures = 0
                        except CaptchaBlocked as e:
                            store.record_application(record, result="failure", error_message=str(e))
                            store.upsert_posting(record, status="apply_failed")
                            summary.failed.append((record, f"CAPTCHA blocked submission: {e}"))
                            consecutive_failures += 1
                        except NeedsManualReview as e:
                            store.record_application(record, result="failure", error_message=str(e))
                            store.upsert_posting(record, status="apply_failed")
                            summary.failed.append((record, f"needs manual review: {e}"))
                            consecutive_failures += 1
                        except Exception as e:
                            store.record_application(
                                record, result="failure", error_message=f"{e}\n{traceback.format_exc()}"
                            )
                            store.upsert_posting(record, status="apply_failed")
                            summary.failed.append((record, f"error: {e}"))
                            consecutive_failures += 1
                        finally:
                            page.close()
                finally:
                    browser.close()
    finally:
        store.close()

    notify.write_summary(summary)
    notify.print_summary(summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Discover and apply to jobs on your whitelist.")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Fill applications but never click submit (default: real submit).",
    )
    parser.add_argument(
        "--headed", action="store_true",
        help="Run Playwright with a visible browser window (default: headless).",
    )
    args = parser.parse_args()
    run(dry_run=args.dry_run, headed=args.headed)


if __name__ == "__main__":
    main()
