"""Mock of the Andakia Voice API, for local development and tests.

It implements the same three endpoints as the real service, with canned,
deterministic behaviour. It contains no speech or language model and gives no
health advice.

  POST /tts  writes a short tone WAV and embeds the text in a custom RIFF chunk.
  POST /asr  reads that chunk back, so a simulated caller can "speak" any
             sentence: render it with /tts, send the audio as the caller turn.
             Real audio without the chunk is answered with a fixed sentence,
             or with "" when the audio is silent.
  POST /chat rule based: flags emergencies and requests for a person, otherwise
             acknowledges the question.

Run: uvicorn mock_api.server:app --port 9000
"""
from __future__ import annotations

import base64
import binascii
import io
import math
import struct
import unicodedata
import wave

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

TEXT_CHUNK = b"lrtx"

app = FastAPI(title="Andakia Voice API (mock)", version="mock")


def _check_auth(authorization: str | None) -> None:
    if not authorization or not authorization.startswith("Bearer ") or len(authorization) <= len("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")


def make_wav(text: str, sample_rate: int = 8000) -> bytes:
    """Tone whose length follows the text, plus the text in a custom chunk."""
    seconds = min(0.3 + 0.04 * len(text), 8.0)
    n = int(seconds * sample_rate)
    frames = b"".join(
        struct.pack("<h", int(3000 * math.sin(2 * math.pi * 440 * i / sample_rate))) for i in range(n)
    )
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(frames)
    payload = text.encode("utf-8")
    chunk = TEXT_CHUNK + struct.pack("<I", len(payload)) + payload + (b"\x00" if len(payload) % 2 else b"")
    data = bytearray(buf.getvalue() + chunk)
    struct.pack_into("<I", data, 4, len(data) - 8)  # fix RIFF size
    return bytes(data)


def read_text(audio: bytes) -> str | None:
    """Return the text embedded by make_wav, if any."""
    if audio[:4] != b"RIFF" or audio[8:12] != b"WAVE":
        return None
    pos = 12
    while pos + 8 <= len(audio):
        cid, size = audio[pos : pos + 4], struct.unpack("<I", audio[pos + 4 : pos + 8])[0]
        if cid == TEXT_CHUNK:
            return audio[pos + 8 : pos + 8 + size].decode("utf-8", errors="replace")
        pos += 8 + size + (size % 2)
    return None


def _is_silent(audio: bytes) -> bool:
    try:
        with wave.open(io.BytesIO(audio), "rb") as w:
            frames = w.readframes(w.getnframes())
    except (wave.Error, EOFError):
        return not audio
    if len(frames) < 2:
        return True
    samples = struct.unpack(f"<{len(frames) // 2}h", frames[: len(frames) // 2 * 2])
    rms = math.sqrt(sum(s * s for s in samples) / len(samples))
    return rms < 200


def _fold(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


class ASRRequest(BaseModel):
    audio_base64: str
    format: str = "wav"
    sample_rate: int = 8000
    language_hint: str | None = None


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    session_id: str
    language: str = "wo"
    messages: list[ChatMessage]
    context: dict = {}


class TTSRequest(BaseModel):
    text: str
    language: str = "wo"
    format: str = "wav"
    sample_rate: int = 8000


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "mock": True}


@app.post("/asr")
async def asr(req: ASRRequest, authorization: str | None = Header(default=None)) -> dict:
    _check_auth(authorization)
    try:
        audio = base64.b64decode(req.audio_base64, validate=True)
    except (ValueError, binascii.Error):
        raise HTTPException(status_code=400, detail="audio_base64 is not valid base64")
    embedded = read_text(audio)
    if embedded is not None:
        text = embedded
    elif _is_silent(audio):
        text = ""
    else:
        text = "J'ai une question sur ma santé." if req.language_hint == "fr" else "Am naa laaj ci sama wér-gi-yaram."
    language = "fr" if any(w in f" {_fold(text)} " for w in (" je ", " j'ai ", " est-ce ", " mon ", " ma ")) else (req.language_hint or "wo")
    return {"text": text, "language": language, "confidence": 0.99 if embedded is not None else 0.5}


EMERGENCY = ("urgence", "hemorragie", "saigne beaucoup", "deret bu bare", "evanoui", "dafa xem")
HANDOFF = ("sage-femme", "sage femme", "medecin", "docteur", "fajkat", "doktoor", "parler a quelqu'un")


@app.post("/chat")
async def chat(req: ChatRequest, authorization: str | None = Header(default=None)) -> dict:
    _check_auth(authorization)
    last = next((m.content for m in reversed(req.messages) if m.role == "user"), "")
    folded = _fold(last)
    french = any(w in f" {folded} " for w in (" je ", " j'ai ", " est-ce ", " mon ", " ma "))
    language = "fr" if french else req.language
    emergency = any(k in folded for k in EMERGENCY)
    handoff = emergency or any(k in folded for k in HANDOFF)

    if emergency:
        reply = {
            "fr": "Ceci ressemble à une urgence. Je vous passe une professionnelle de santé.",
            "wo": "Lii mel na ni lu jamp. Maa ngi lay jokkale ak ab fajkat.",
        }[language]
    elif handoff:
        reply = {
            "fr": "D'accord, je vous passe une professionnelle de santé.",
            "wo": "Waaw, maa ngi lay jokkale ak ab fajkat.",
        }[language]
    else:
        reply = {
            "fr": "Ceci est le service de test. Votre question est bien reçue. Sur la vraie ligne, la réponse vient de contenus validés par des professionnels de santé.",
            "wo": "Lii ab test la. Sa laaj agsi na. Ci ligne bu dëgg bi, tontu bi dina jóge ci xibaar yu fajkat yi dëggal.",
        }[language]

    return {
        "reply": reply,
        "language": language,
        "handoff": {"requested": handoff, "reason": "emergency" if emergency else ("caller_request" if handoff else None)},
        "safety": {"emergency": emergency},
    }


@app.post("/tts")
async def tts(req: TTSRequest, authorization: str | None = Header(default=None)) -> dict:
    _check_auth(authorization)
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="text is empty")
    audio = make_wav(req.text, req.sample_rate)
    return {
        "audio_base64": base64.b64encode(audio).decode("ascii"),
        "format": "wav",
        "sample_rate": req.sample_rate,
        "duration_ms": int(min(0.3 + 0.04 * len(req.text), 8.0) * 1000),
    }
