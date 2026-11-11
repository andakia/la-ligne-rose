"""Thin HTTP client for the Andakia Voice API.

The Andakia Voice API is an external, proprietary service. It is NOT part of
this repository. The phone line only needs three operations from it:

    POST /asr   audio  -> text
    POST /chat  text   -> reply (plus routing flags)
    POST /tts   text   -> audio

All requests carry `Authorization: Bearer <ANDAKIA_API_KEY>`. Request and
response examples live in `docs/api/`. For local development, `mock_api/`
implements the same three endpoints with canned behaviour.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass, field
from typing import Any

import httpx

USER_AGENT = "la-ligne-rose/0.1"


class VoiceAPIError(RuntimeError):
    """The Voice API could not be reached or returned an unusable answer."""


@dataclass(frozen=True)
class Transcript:
    text: str
    language: str | None = None
    confidence: float | None = None


@dataclass(frozen=True)
class ChatReply:
    reply: str
    language: str
    handoff: bool = False
    handoff_reason: str | None = None
    emergency: bool = False


@dataclass(frozen=True)
class Speech:
    audio: bytes
    format: str = "wav"
    sample_rate: int = 8000


@dataclass
class VoiceAPIClient:
    base_url: str
    api_key: str
    timeout_s: float = 15.0
    transport: httpx.AsyncBaseTransport | None = None
    _client: httpx.AsyncClient | None = field(default=None, init=False, repr=False)

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "User-Agent": USER_AGENT,
                },
                timeout=self.timeout_s,
                transport=self.transport,
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        """POST with one retry on network errors and 5xx answers."""
        last_error: Exception | None = None
        for _attempt in range(2):
            try:
                response = await self._http().post(path, json=payload)
            except httpx.TransportError as exc:
                last_error = exc
                continue
            if response.status_code >= 500:
                last_error = VoiceAPIError(f"{path} returned {response.status_code}")
                continue
            if response.status_code != 200:
                raise VoiceAPIError(f"{path} returned {response.status_code}: {response.text[:200]}")
            try:
                return response.json()
            except ValueError as exc:
                raise VoiceAPIError(f"{path} returned invalid JSON") from exc
        raise VoiceAPIError(f"{path} failed after retry: {last_error}")

    async def asr(
        self,
        audio: bytes,
        *,
        fmt: str = "wav",
        sample_rate: int = 8000,
        language_hint: str | None = None,
    ) -> Transcript:
        data = await self._post(
            "/asr",
            {
                "audio_base64": base64.b64encode(audio).decode("ascii"),
                "format": fmt,
                "sample_rate": sample_rate,
                "language_hint": language_hint,
            },
        )
        return Transcript(
            text=str(data.get("text", "")).strip(),
            language=data.get("language"),
            confidence=data.get("confidence"),
        )

    async def chat(
        self,
        *,
        session_id: str,
        language: str,
        messages: list[dict[str, str]],
        context: dict[str, Any] | None = None,
    ) -> ChatReply:
        data = await self._post(
            "/chat",
            {
                "session_id": session_id,
                "language": language,
                "messages": messages,
                "context": context or {},
            },
        )
        reply = str(data.get("reply", "")).strip()
        if not reply:
            raise VoiceAPIError("/chat returned an empty reply")
        handoff = data.get("handoff") or {}
        safety = data.get("safety") or {}
        return ChatReply(
            reply=reply,
            language=data.get("language") or language,
            handoff=bool(handoff.get("requested", False)),
            handoff_reason=handoff.get("reason"),
            emergency=bool(safety.get("emergency", False)),
        )

    async def tts(
        self,
        text: str,
        *,
        language: str,
        fmt: str = "wav",
        sample_rate: int = 8000,
    ) -> Speech:
        data = await self._post(
            "/tts",
            {"text": text, "language": language, "format": fmt, "sample_rate": sample_rate},
        )
        try:
            audio = base64.b64decode(data["audio_base64"], validate=True)
        except (KeyError, ValueError) as exc:
            raise VoiceAPIError("/tts returned no usable audio") from exc
        return Speech(
            audio=audio,
            format=data.get("format", fmt),
            sample_rate=int(data.get("sample_rate", sample_rate)),
        )
