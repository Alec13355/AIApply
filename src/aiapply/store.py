from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .paths import STORE_PATH, ensure_data_dir

SCHEMA = """
CREATE TABLE IF NOT EXISTS postings (
    posting_key TEXT PRIMARY KEY,
    board TEXT NOT NULL,
    company TEXT NOT NULL,
    title TEXT NOT NULL,
    location TEXT,
    url TEXT NOT NULL,
    auto_apply_eligible INTEGER NOT NULL,
    fit_score INTEGER,
    fit_reasoning TEXT,
    status TEXT NOT NULL,  -- seen | surfaced | applied | apply_failed | skipped
    first_seen_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    posting_key TEXT NOT NULL REFERENCES postings(posting_key),
    applied_at TEXT NOT NULL,
    result TEXT NOT NULL,  -- success | failure
    fields_json TEXT,
    answers_json TEXT,
    error_message TEXT,
    screenshot_path TEXT
);
"""


@dataclass
class PostingRecord:
    posting_key: str
    board: str
    company: str
    title: str
    url: str
    auto_apply_eligible: bool
    location: str | None = None
    fit_score: int | None = None
    fit_reasoning: str | None = None


@dataclass
class RunSummary:
    applied: list[PostingRecord] = field(default_factory=list)
    surfaced: list[PostingRecord] = field(default_factory=list)
    failed: list[tuple[PostingRecord, str]] = field(default_factory=list)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, path: Path = STORE_PATH):
        ensure_data_dir()
        self.path = path
        self._conn = sqlite3.connect(self.path)
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    @contextmanager
    def _cursor(self):
        cur = self._conn.cursor()
        try:
            yield cur
            self._conn.commit()
        finally:
            cur.close()

    def is_known(self, posting_key: str) -> bool:
        cur = self._conn.execute(
            "SELECT 1 FROM postings WHERE posting_key = ?", (posting_key,)
        )
        return cur.fetchone() is not None

    def upsert_posting(
        self,
        posting: PostingRecord,
        status: str,
    ) -> None:
        now = _now()
        with self._cursor() as cur:
            cur.execute(
                """
                INSERT INTO postings (
                    posting_key, board, company, title, location, url,
                    auto_apply_eligible, fit_score, fit_reasoning, status,
                    first_seen_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(posting_key) DO UPDATE SET
                    fit_score=excluded.fit_score,
                    fit_reasoning=excluded.fit_reasoning,
                    status=excluded.status,
                    updated_at=excluded.updated_at
                """,
                (
                    posting.posting_key,
                    posting.board,
                    posting.company,
                    posting.title,
                    posting.location,
                    posting.url,
                    int(posting.auto_apply_eligible),
                    posting.fit_score,
                    posting.fit_reasoning,
                    status,
                    now,
                    now,
                ),
            )

    def record_application(
        self,
        posting: PostingRecord,
        result: str,
        fields: dict | None = None,
        answers: dict | None = None,
        error_message: str | None = None,
        screenshot_path: str | None = None,
    ) -> None:
        with self._cursor() as cur:
            cur.execute(
                """
                INSERT INTO applications (
                    posting_key, applied_at, result, fields_json, answers_json,
                    error_message, screenshot_path
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    posting.posting_key,
                    _now(),
                    result,
                    json.dumps(fields) if fields else None,
                    json.dumps(answers) if answers else None,
                    error_message,
                    screenshot_path,
                ),
            )

    def applied_count_today(self) -> int:
        today = datetime.now(timezone.utc).date().isoformat()
        cur = self._conn.execute(
            "SELECT COUNT(*) FROM applications WHERE result = 'success' AND applied_at LIKE ?",
            (f"{today}%",),
        )
        return cur.fetchone()[0]
