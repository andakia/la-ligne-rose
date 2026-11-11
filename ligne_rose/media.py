"""Audio cache: text is rendered once through the Voice API `/tts` endpoint,
kept in memory and served to the gateway at GET /media/<key>.wav.

Fixed menu messages are rendered on first use and reused for every call.
Conversation replies are cached too, and evicted oldest first.
"""
from __future__ import annotations

import hashlib
from collections import OrderedDict

from .voice_api import VoiceAPIClient


class MediaStore:
    def __init__(self, client: VoiceAPIClient, sample_rate: int = 8000, max_items: int = 500):
        self._client = client
        self._sample_rate = sample_rate
        self._max_items = max_items
        self._items: OrderedDict[str, bytes] = OrderedDict()

    @staticmethod
    def key(text: str, language: str) -> str:
        return hashlib.sha256(f"{language}|{text}".encode("utf-8")).hexdigest()[:32]

    async def render(self, text: str, language: str) -> str:
        """Return the media key for this text, rendering it if needed."""
        k = self.key(text, language)
        if k in self._items:
            self._items.move_to_end(k)
            return k
        speech = await self._client.tts(text, language=language, sample_rate=self._sample_rate)
        self._items[k] = speech.audio
        while len(self._items) > self._max_items:
            self._items.popitem(last=False)
        return k

    def get(self, key: str) -> bytes | None:
        return self._items.get(key)
