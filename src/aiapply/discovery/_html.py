from __future__ import annotations

from lxml import html as lxml_html


def strip_html(raw: str) -> str:
    if not raw:
        return ""
    try:
        tree = lxml_html.fromstring(raw)
        text = tree.text_content()
    except Exception:
        return raw
    return " ".join(text.split())
