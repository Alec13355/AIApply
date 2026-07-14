from __future__ import annotations

from playwright.sync_api import Page

# We only ever detect whether a CAPTCHA challenge is blocking submission --
# never attempt to solve, bypass, or otherwise defeat it.

_CHALLENGE_SELECTORS = [
    'iframe[src*="recaptcha/api2/bframe"]',
    'iframe[title*="recaptcha" i][title*="challenge" i]',
    'iframe[src*="hcaptcha.html#frame=challenge"]',
]


def is_captcha_challenge_visible(page: Page, timeout_ms: int = 3000) -> bool:
    for selector in _CHALLENGE_SELECTORS:
        locator = page.locator(selector)
        try:
            locator.first.wait_for(state="visible", timeout=timeout_ms)
            return True
        except Exception:
            continue
    return False
