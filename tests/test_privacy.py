from __future__ import annotations

from fastapi.testclient import TestClient

from .conftest import CALLER, TRANSFER, build
from .test_call_flow import call, menu, speak

SENTENCE = "J'ai une question très personnelle sur mes règles."


def _dump(call_log) -> str:
    rows = call_log.rows("SELECT * FROM calls") + call_log.rows("SELECT * FROM events")
    return " ".join(str(v) for row in rows for v in row)


def test_caller_number_and_transcripts_are_not_stored_by_default():
    app, call_log = build(transfer=TRANSFER)
    with TestClient(app) as tc:
        call(tc)
        menu(tc, "call-1", "2")
        menu(tc, "call-1", "1")
        speak(tc, "call-1", SENTENCE)
    dump = _dump(call_log)
    assert CALLER not in dump and CALLER.lstrip("+") not in dump
    assert SENTENCE not in dump


def test_transcripts_are_stored_only_when_enabled():
    app, call_log = build(transfer=TRANSFER, log_transcripts=True)
    with TestClient(app) as tc:
        call(tc)
        menu(tc, "call-1", "2")
        menu(tc, "call-1", "1")
        speak(tc, "call-1", SENTENCE)
    assert SENTENCE in _dump(call_log)


def test_same_caller_gets_the_same_pseudonym():
    _, call_log = build()
    assert call_log.caller_hash(CALLER) == call_log.caller_hash(CALLER.lstrip("+"))
    assert call_log.caller_hash(CALLER) != CALLER.lstrip("+")


def test_stats_are_disabled_without_admin_token(line):
    tc, _ = line
    assert tc.get("/stats").status_code == 404
