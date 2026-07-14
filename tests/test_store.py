from pathlib import Path

import pytest

from aiapply.store import PostingRecord, Store


@pytest.fixture
def store(tmp_path: Path) -> Store:
    s = Store(path=tmp_path / "test.db")
    yield s
    s.close()


def _posting(key="greenhouse:acme:1") -> PostingRecord:
    return PostingRecord(
        posting_key=key, board="greenhouse", company="acme", title="SWE",
        url="https://example.com", auto_apply_eligible=True,
    )


def test_dedup(store: Store):
    rec = _posting()
    assert not store.is_known(rec.posting_key)
    store.upsert_posting(rec, status="seen")
    assert store.is_known(rec.posting_key)


def test_applied_count_today(store: Store):
    rec = _posting()
    assert store.applied_count_today() == 0
    store.record_application(rec, result="success")
    assert store.applied_count_today() == 1
    store.record_application(rec, result="failure")
    assert store.applied_count_today() == 1  # only successes count
