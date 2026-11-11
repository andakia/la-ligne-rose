from __future__ import annotations

import asyncio
import base64

import httpx
import pytest

from ligne_rose.routing import local_flags
from ligne_rose.voice_api import VoiceAPIClient, VoiceAPIError


def run(coro):
    return asyncio.run(coro)


def test_bearer_key_is_sent_and_answers_are_parsed():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization")
        seen["path"] = request.url.path
        return httpx.Response(200, json={"text": "Am naa laaj.", "language": "wo", "confidence": 0.9})

    client = VoiceAPIClient("https://api.example.com", "demo-key", transport=httpx.MockTransport(handler))
    result = run(client.asr(b"RIFF....", language_hint="wo"))
    assert seen == {"auth": "Bearer demo-key", "path": "/asr"}
    assert result.text == "Am naa laaj." and result.language == "wo"


def test_one_retry_on_server_error():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503)
        audio = base64.b64encode(b"RIFFdata").decode()
        return httpx.Response(200, json={"audio_base64": audio, "format": "wav", "sample_rate": 8000})

    client = VoiceAPIClient("https://api.example.com", "demo-key", transport=httpx.MockTransport(handler))
    speech = run(client.tts("Jërëjëf", language="wo"))
    assert calls["n"] == 2 and speech.audio == b"RIFFdata"


def test_client_errors_are_not_retried():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(401, json={"error": "bad key"})

    client = VoiceAPIClient("https://api.example.com", "wrong", transport=httpx.MockTransport(handler))
    with pytest.raises(VoiceAPIError):
        run(client.chat(session_id="s", language="fr", messages=[{"role": "user", "content": "Bonjour"}]))
    assert calls["n"] == 1


def test_chat_flags_are_read():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "reply": "Je vous passe une sage-femme.",
                "language": "fr",
                "handoff": {"requested": True, "reason": "caller_request"},
                "safety": {"emergency": False},
            },
        )

    client = VoiceAPIClient("https://api.example.com", "demo-key", transport=httpx.MockTransport(handler))
    reply = run(client.chat(session_id="s", language="fr", messages=[{"role": "user", "content": "sage-femme"}]))
    assert reply.handoff and not reply.emergency and reply.handoff_reason == "caller_request"


@pytest.mark.parametrize(
    "sentence, handoff, emergency",
    [
        ("Je veux parler à un médecin", True, False),
        ("Dama bëgg wax ak ab fajkat", True, False),
        ("Elle a perdu connaissance, elle s'est évanouie", False, True),
        ("Am na deret bu bare", False, True),
        ("Am naa laaj ci sama wér-gi-yaram", False, False),
    ],
)
def test_local_safety_net(sentence, handoff, emergency):
    flags = local_flags(sentence)
    assert (flags.handoff, flags.emergency) == (handoff, emergency)
