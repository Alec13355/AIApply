# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A pipeline (meant to be run once a day) that discovers job postings matching
the user's parameters and auto-applies to a whitelisted set of company ATS
boards via Playwright, using an Azure AI Foundry-hosted model for resume
parsing, fit scoring, and free-text answer generation. Postings found outside
the whitelist are only ever surfaced in the daily summary for manual review —
**never auto-applied to**. See README.md for user-facing setup/usage
instructions; this file is architecture + conventions for working on the code.

Scheduling is intentionally not wired up yet (manual trigger only, per the
user). The user chose "fully autonomous" submission (no review-before-submit
step) for whitelisted postings, which is why the safety design described
below (CAPTCHA handling, screening_answers, demographic-field handling) is
load-bearing rather than optional — there is no human in the loop before a
real submission happens.

## Commands

```
uv sync                                          # install deps
uv run playwright install chromium               # install browser binary (one-time)
uv run pytest -q                                 # run tests
uv run pytest tests/test_store.py -q             # run a single test file
uv run python -m aiapply.run --dry-run --headed  # fill real forms, never submit, visible browser
uv run python -m aiapply.run                     # real run: discovers, scores, submits, records
./scripts/setup_azure.sh                         # provision the Azure AI Foundry resource + model deployment (idempotent, real billable resources)
```

There is no lint/typecheck config in this repo yet.

## Architecture

Pipeline, in order, orchestrated by `src/aiapply/run.py::run()`:

1. **Config** (`config.py`) — loads `config/profile.yaml` (target roles,
   locations, salary floor, `min_fit_score`, `daily_application_cap`,
   `circuit_breaker_failures`, `screening_answers`) and `config/sites.yaml`
   (the auto-apply `whitelist` of `{board, slug}` entries, plus a
   `discovery.web_search` block — see Known gaps below) into pydantic
   models. Azure credentials load separately via `AzureSettings`
   (`pydantic-settings`, reads `.env`).
2. **Resume parsing** (`resume.py`) — extracts text from `data/resume.pdf`/
   `.docx`, sends it to the LLM to produce a structured `ParsedResume`
   (pydantic model), cached in `data/resume_parsed.json` keyed by a hash of
   the source file so it's only re-parsed when the resume changes.
3. **Discovery** (`discovery/`) — `greenhouse.py` and `lever.py` hit those
   ATSs' public, unauthenticated JSON APIs (`boards-api.greenhouse.io`,
   `api.lever.co/v0/postings`) for every whitelisted `{board, slug}`, always
   with `auto_apply_eligible=True`. `github_careers.py` is a third fetcher,
   but unlike the other two it's hardcoded to one company's real endpoint
   (`www.github.careers/api/jobs`) rather than a generic per-tenant vendor
   API — `slug` is accepted for dispatch-signature parity but unused. It
   needs a realistic browser `User-Agent` header; the default/no-UA request
   gets a 403. `discovery/__init__.py` exposes `discover_whitelisted()` and
   `discover_surfaced()` (the latter currently a no-op stub, see Known
   gaps). Everything normalizes to the `JobPosting` model in
   `discovery/base.py`.
4. **Dedup + matching** — `run.py` skips any `JobPosting` whose
   `posting_key` (`{board}:{company}:{external_id}`) is already in the
   SQLite store, then scores the rest via `matching.score_posting()`
   (LLM call, returns `FitResult{fit_score, reasoning}`), keeping only
   postings scoring `>= profile.min_fit_score`.
5. **Apply** (`apply/`) — one function per board in `apply/__init__.py`'s
   `APPLY_FNS` dict (`greenhouse_apply.apply`, `lever_apply.apply`,
   `github_apply.apply`), each taking a Playwright `Page` + posting + resume
   + profile + AI client and returning an `ApplicationResult`. Greenhouse and
   Lever share:
   - `apply/_form_filler.py` — generic labeled-field filler used for any
     custom/per-company question not explicitly handled by name. Classifies
     each question via `apply/answers.py::classify_question()` into
     `demographic` (never answered — left blank or "decline to
     self-identify" if that option exists), `sensitive` (only answered from
     `profile.screening_answers`, a keyword-substring-matched dict the user
     configures; **no match → raises `NeedsManualReview`, application is not
     submitted**), or `open` (answered via LLM, grounded in the resume).
     This 3-way split is the main safety mechanism given there's no
     human review step — don't weaken it without re-reading why in
     `apply/answers.py`.
   - `apply/_captcha.py` — detects (never solves/bypasses) visible reCAPTCHA/
     hCaptcha challenge iframes after a submit attempt; raises
     `CaptchaBlocked`. **Do not add CAPTCHA-solving/bypass logic here** —
     both Greenhouse and Lever protect their submit step with CAPTCHA, and
     defeating that is out of scope by design, not an oversight.
   - Both flows support `dry_run=True`: fills the entire form, screenshots
     it, and returns without clicking submit. Always test a new/changed
     apply flow with `--dry-run --headed` against a real posting before a
     real run — this is how the current flows were built and debugged (see
     "How the apply flows were validated" below).
   - `github_apply.py` is structurally different, not just a third copy of
     the same pattern — see the "GitHub apply flow" note under Known gaps
     below before touching it.
6. **Store** (`store.py`) — SQLite at `data/store.db`. `postings` table is
   the dedup/status ledger (`seen`/`surfaced`/`applied`/`apply_failed`);
   `applications` table is the audit log (fields filled, AI-generated
   answers, screenshot path per attempt). `applied_count_today()` backs the
   `daily_application_cap` guardrail, checked/enforced across runs, not just
   within one.
7. **Guardrails, in `run.py`'s apply loop** — `daily_application_cap` stops
   new submissions once hit (remaining eligible postings stay `seen` and are
   picked up next run, not lost). `circuit_breaker_failures` counts
   consecutive non-success outcomes (any of `CaptchaBlocked`,
   `NeedsManualReview`, generic exception) and halts the rest of the run if
   tripped, on the theory that repeated failures usually mean something
   structural broke (a selector, the network, a systematic CAPTCHA wall) and
   continuing would just fail the same way while wasting the daily cap.
8. **Notify** (`notify.py`) — formats a `RunSummary` (applied / surfaced /
   failed, each with reasons) to `data/summaries/<date>.md` and stdout.

## Known gaps / deliberate non-goals

- **`discovery/web_search.py` is an intentional no-op stub.** Broader
  discovery outside the whitelist was scoped to be done *live* by Claude
  Code's own WebSearch tool when the user asks for the daily check, rather
  than hard-coded against a search API/key that wasn't chosen — this is a
  fuzzier, judgment-heavy task better suited to an LLM-in-the-loop than a
  fixed integration. Only Greenhouse/Lever whitelist discovery is a real,
  scheduled-pipeline concern.
- **Only Greenhouse and Lever have full, general apply flows.** Workday/
  generic iCIMS tenants/etc. are out of scope — their forms are far less
  consistent across tenants (see plan discussion in project history), so a
  generic fallback wasn't attempted.
- **GitHub apply flow (`apply/github_apply.py`) is a single hardcoded
  company integration, not a generic vendor integration, and is
  intentionally incomplete.** GitHub's careers site (`github.careers`) runs
  on iCIMS behind an hCaptcha-gated login/consent step. Live testing found:
  Playwright's default headless UA (`HeadlessChrome/...`) gets served a
  stripped page with no Apply link at all — `github_apply.py` opens its own
  browser context with a normal desktop Chrome UA string to work around
  this (the one deliberate exception to "don't touch Playwright's
  launch/context config" elsewhere in this codebase; this only affects
  whether ordinary content renders, not any CAPTCHA-relevant fingerprint —
  `navigator.webdriver` etc. are untouched). With that fix, the flow reaches
  the iCIMS gate, and — same as Greenhouse/Lever CAPTCHA hits — may either
  sail through (real user sessions likely do) or get walled by an hCaptcha
  challenge (`_captcha.py`'s existing selectors already detect this
  correctly, no changes needed there). If not blocked, it fills email +
  checks the consent checkbox (verified live, screenshot-confirmed), then
  **deliberately raises `NeedsManualReview`** rather than guessing at the
  form beyond that point — it was never observed in testing (every earlier
  attempt got walled before the UA fix), and guessing risks silently
  mis-filling or mis-submitting a real application with no human review
  step. **Every real run of this flow today ends in `CaptchaBlocked` or
  `NeedsManualReview`, never `success` — this is intentional, not a
  regression.** Finishing it requires a `--dry-run --headed` session against
  a real posting to observe the actual post-consent form and extend the
  flow accordingly (the "Next" button past consent was confirmed via
  screenshot but not yet clicked/explored further). The user explicitly
  declined adding CAPTCHA-solving/bypass logic to force this further —
  don't reconsider that without asking again.
- `config/sites.yaml`'s `github` whitelist entry must stay **last** in the
  list: `run.py` processes whitelist entries in order, so this keeps
  repeated GitHub `CaptchaBlocked`/`NeedsManualReview` outcomes from
  tripping `circuit_breaker_failures` before real Greenhouse/Lever
  applications in the same run get a chance to submit. This is an ordering
  convention, not an enforced invariant — anything appended after it loses
  the protection.
- **Radio/checkbox groups are skipped entirely** by `_form_filler.py` (not
  just demographic ones) — see the comment in `lever_apply.py`. This is a
  safe-by-default simplification: a skipped required question fails
  submission cleanly (caught, logged, surfaced) rather than risking a wrong
  answer, but it does mean a required Yes/No question rendered as radio
  buttons (rather than Greenhouse's react-select combobox pattern) won't be
  answered even if a correct answer is configured.
- No CI/lint config exists yet.

## Current project status (as of last working session)

Code is complete and tested (7 pytest tests passing; discovery verified live
against real Greenhouse/Lever boards and the real GitHub careers API; apply
flows verified via dry-run against a live GitLab Greenhouse posting, Lever's
demo board, and a live GitHub posting — screenshots confirmed correct in all
cases, though the GitHub flow only gets partway through by design, see Known
gaps above). Azure AI Foundry is provisioned and `.env` is populated. A real
resume is at `data/resume.pdf`. Not yet done, blocking a real (non-dry-run,
non-GitHub) run:

1. `config/sites.yaml`'s `greenhouse`/`lever` whitelist entries still hold
   the placeholder `example-company` slug — need real target companies from
   the user. The `github` entry is real (hardcoded to github.careers) and
   must stay last in the list (see Known gaps).
2. `config/profile.yaml` has real-looking values already (target titles,
   locations, `screening_answers`) — worth the user double-checking it
   still reflects what they want, but it's not a placeholder blocker.
3. Once 1 is done: run `--dry-run --headed` first, review the filled
   forms/screenshots, then run for real. Note a real (non-dry-run) run will
   still never actually submit a GitHub application today — see Known gaps.
