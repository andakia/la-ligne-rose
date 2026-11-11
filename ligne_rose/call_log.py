"""Call journal (SQLite).

Privacy by default, because callers talk about their health:
  - the caller number is never stored, only a salted HMAC of it;
  - transcripts are NOT stored unless LOG_TRANSCRIPTS=true;
  - events keep what is needed to run and improve the service
    (route taken, number of turns, transfers, errors).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS calls (
    call_id      TEXT PRIMARY KEY,
    caller_hash  TEXT NOT NULL,
    line         TEXT,
    language     TEXT,
    started_at   REAL NOT NULL,
    ended_at     REAL,
    route        TEXT NOT NULL DEFAULT 'menu',
    turns        INTEGER NOT NULL DEFAULT 0,
    transferred  INTEGER NOT NULL DEFAULT 0,
    emergency    INTEGER NOT NULL DEFAULT 0,
    end_reason   TEXT
);
CREATE TABLE IF NOT EXISTS events (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    call_id  TEXT NOT NULL,
    ts       REAL NOT NULL,
    kind     TEXT NOT NULL,
    detail   TEXT
);
CREATE INDEX IF NOT EXISTS events_call ON events(call_id);
"""


class CallLog:
    def __init__(self, path: str, salt: str = "", log_transcripts: bool = False):
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.executescript(SCHEMA)
        self._lock = threading.Lock()
        # Without a configured salt, hashes are only stable for this process.
        self._salt = (salt or secrets.token_hex(16)).encode("utf-8")
        self.log_transcripts = log_transcripts

    def caller_hash(self, number: str) -> str:
        digits = "".join(c for c in number if c.isdigit())
        return hmac.new(self._salt, digits.encode("ascii"), hashlib.sha256).hexdigest()[:24]

    def _exec(self, sql: str, args: tuple[Any, ...] = ()) -> None:
        with self._lock:
            self._db.execute(sql, args)
            self._db.commit()

    def start(self, call_id: str, caller: str, line: str) -> str:
        h = self.caller_hash(caller)
        self._exec(
            "INSERT OR IGNORE INTO calls(call_id, caller_hash, line, started_at) VALUES (?,?,?,?)",
            (call_id, h, line, time.time()),
        )
        self.event(call_id, "call_start")
        return h

    def update(self, call_id: str, **fields: Any) -> None:
        allowed = {"language", "route", "turns", "transferred", "emergency", "end_reason"}
        cols = [k for k in fields if k in allowed]
        if not cols:
            return
        sql = "UPDATE calls SET " + ", ".join(f"{c}=?" for c in cols) + " WHERE call_id=?"
        self._exec(sql, tuple(fields[c] for c in cols) + (call_id,))

    def event(self, call_id: str, kind: str, **detail: Any) -> None:
        if not self.log_transcripts:
            detail.pop("transcript", None)
            detail.pop("reply", None)
        self._exec(
            "INSERT INTO events(call_id, ts, kind, detail) VALUES (?,?,?,?)",
            (call_id, time.time(), kind, json.dumps(detail, ensure_ascii=False) if detail else None),
        )

    def end(self, call_id: str, reason: str) -> None:
        self._exec(
            "UPDATE calls SET ended_at=?, end_reason=COALESCE(end_reason, ?) WHERE call_id=? AND ended_at IS NULL",
            (time.time(), reason, call_id),
        )
        self.event(call_id, "call_end", reason=reason)

    def stats(self) -> dict[str, Any]:
        with self._lock:
            cur = self._db.cursor()
            total = cur.execute("SELECT COUNT(*) FROM calls").fetchone()[0]
            by_language = dict(cur.execute("SELECT COALESCE(language,'none'), COUNT(*) FROM calls GROUP BY 1").fetchall())
            by_route = dict(cur.execute("SELECT route, COUNT(*) FROM calls GROUP BY 1").fetchall())
            transferred = cur.execute("SELECT COUNT(*) FROM calls WHERE transferred=1").fetchone()[0]
            emergencies = cur.execute("SELECT COUNT(*) FROM calls WHERE emergency=1").fetchone()[0]
            avg_turns = cur.execute("SELECT COALESCE(AVG(turns),0) FROM calls").fetchone()[0]
        return {
            "calls": total,
            "by_language": by_language,
            "by_route": by_route,
            "transferred": transferred,
            "emergencies": emergencies,
            "avg_turns": round(float(avg_turns), 2),
        }

    def rows(self, sql: str, args: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
        """Read helper for tests and local inspection."""
        with self._lock:
            return self._db.execute(sql, args).fetchall()
