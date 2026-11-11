from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from ligne_rose.app import create_app
from ligne_rose.call_log import CallLog
from ligne_rose.config import Settings
from ligne_rose.voice_api import VoiceAPIClient
from mock_api.server import app as mock_app

CALLER = "+000000001"  # fictional numbers only, never real ones
LINE = "+000000002"
TRANSFER = "sip:health-desk@pbx.example.com"


class FailingTransport(httpx.AsyncBaseTransport):
    """Sends requests to the mock, except the paths listed, which get a 500."""

    def __init__(self, fail_paths: set[str]):
        self._inner = httpx.ASGITransport(app=mock_app)
        self._fail = fail_paths

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if request.url.path in self._fail:
            return httpx.Response(500, json={"error": "simulated failure"})
        return await self._inner.handle_async_request(request)


def build(transfer: str = "", fail: set[str] | None = None, log_transcripts: bool = False):
    settings = Settings(
        api_url="http://voice-api.test",
        api_key="test-key",
        public_base_url="http://testserver",
        human_transfer_target=transfer,
        call_log_path=":memory:",
        caller_hash_salt="test-salt",
        log_transcripts=log_transcripts,
        max_ai_turns=3,
    )
    transport = FailingTransport(fail) if fail else httpx.ASGITransport(app=mock_app)
    client = VoiceAPIClient(settings.api_url, settings.api_key, transport=transport)
    call_log = CallLog(":memory:", settings.caller_hash_salt, settings.log_transcripts)
    return create_app(settings, client, call_log), call_log


@pytest.fixture
def line():
    app, call_log = build(transfer=TRANSFER)
    with TestClient(app) as tc:
        yield tc, call_log


@pytest.fixture
def line_no_human():
    app, call_log = build(transfer="")
    with TestClient(app) as tc:
        yield tc, call_log
