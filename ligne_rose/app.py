"""La Ligne Rose: phone line webhooks.

Call flow:
    incoming call  -> welcome + language menu (1 Wolof, 2 French, no key = Wolof)
    main menu      -> 1 voice assistant, 2 health professional, 9 repeat
                      (no key twice = voice assistant, for callers who do not use the keypad)
    assistant turn -> /asr -> /chat -> /tts, then listen again
                      0 at any time, a request for a person, or an emergency
                      -> transfer to a health professional
    hangup         -> call journal closed

Run locally: see README.md (mock Voice API included).
"""
from __future__ import annotations

import base64
import binascii
import logging
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from enum import Enum

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from . import actions as act
from .call_log import CallLog
from .config import Settings
from .media import MediaStore
from .messages import DEFAULT_LANGUAGE, LANGUAGES, text
from .routing import decide, local_flags
from .voice_api import ChatReply, VoiceAPIClient, VoiceAPIError

log = logging.getLogger("ligne_rose")

SESSION_TTL_S = 2 * 3600
MAX_HISTORY = 20


class Stage(str, Enum):
    LANGUAGE = "language"
    MAIN = "main"
    AI = "ai"
    ENDED = "ended"


@dataclass
class CallSession:
    call_id: str
    caller_hash: str
    line: str
    language: str | None = None
    stage: Stage = Stage.LANGUAGE
    history: list[dict[str, str]] = field(default_factory=list)
    turns: int = 0
    invalid: int = 0
    timeouts: int = 0
    empty_turns: int = 0
    started: float = field(default_factory=time.time)

    @property
    def lang(self) -> str:
        return self.language or DEFAULT_LANGUAGE


class IncomingCall(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    call_id: str = Field(min_length=1, max_length=128)
    caller: str = Field(alias="from", default="")
    line: str = Field(alias="to", default="")


class MenuInput(BaseModel):
    call_id: str
    digits: str = ""


class TurnInput(BaseModel):
    call_id: str
    audio_base64: str | None = None
    format: str = "wav"
    sample_rate: int = 8000
    digits: str | None = None


class Hangup(BaseModel):
    call_id: str
    reason: str = "caller_hangup"


def create_app(
    settings: Settings | None = None,
    client: VoiceAPIClient | None = None,
    call_log: CallLog | None = None,
) -> FastAPI:
    settings = settings or Settings.from_env()
    client = client or VoiceAPIClient(settings.api_url, settings.api_key, settings.api_timeout_s)
    call_log = call_log or CallLog(settings.call_log_path, settings.caller_hash_salt, settings.log_transcripts)
    media = MediaStore(client, settings.audio_sample_rate)
    sessions: dict[str, CallSession] = {}

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        if not settings.api_key:
            log.warning("ANDAKIA_API_KEY is empty: Voice API calls will be refused")
        yield
        await client.aclose()

    app = FastAPI(title="La Ligne Rose", version="0.1.0", lifespan=lifespan)
    app.state.sessions = sessions
    app.state.call_log = call_log

    base = settings.public_base_url

    def url(path: str) -> str:
        return f"{base}{path}"

    async def say(key: str, language: str) -> dict:
        return act.play(url(f"/media/{await media.render(text(key, language), language)}.wav"))

    async def speak(sentence: str, language: str) -> dict:
        return act.play(url(f"/media/{await media.render(sentence, language)}.wav"))

    def prune() -> None:
        cutoff = time.time() - SESSION_TTL_S
        for call_id in [k for k, s in sessions.items() if s.started < cutoff]:
            sessions.pop(call_id, None)
            call_log.end(call_id, "expired")

    def fallback(session: CallSession | None) -> dict:
        """The Voice API cannot even render audio: hand over silently, or hang up."""
        if session is not None:
            call_log.event(session.call_id, "voice_api_down")
        if settings.human_transfer_target:
            if session is not None:
                call_log.update(session.call_id, route="human", transferred=1, end_reason="voice_api_down")
            return {"actions": [act.transfer(settings.human_transfer_target)]}
        return {"actions": [act.hangup()]}

    async def main_menu(session: CallSession, prefix: list[dict] | None = None) -> dict:
        session.stage = Stage.MAIN
        return {"actions": (prefix or []) + [await say("main_menu", session.lang), act.gather(url("/voice/menu"))]}

    async def start_assistant(session: CallSession) -> dict:
        session.stage = Stage.AI
        session.timeouts = session.invalid = 0
        call_log.update(session.call_id, route="ai")
        call_log.event(session.call_id, "route", target="ai")
        return {"actions": [await say("ai_intro", session.lang), act.record(url("/voice/turn"))]}

    async def to_human(
        session: CallSession, reason: str, prefix: list[dict] | None = None, announce: bool = True
    ) -> dict:
        prefix = prefix or []
        if not settings.human_transfer_target:
            call_log.event(session.call_id, "human_unavailable", reason=reason)
            return await main_menu(session, prefix + [await say("human_unavailable", session.lang)])
        session.stage = Stage.ENDED
        call_log.update(session.call_id, route="human", transferred=1)
        call_log.event(session.call_id, "route", target="human", reason=reason)
        notice = [await say("transferring", session.lang)] if announce else []
        return {"actions": prefix + notice + [act.transfer(settings.human_transfer_target)]}

    def get_session(call_id: str) -> CallSession | None:
        session = sessions.get(call_id)
        if session is None:
            log.warning("unknown call_id %s", call_id)
        return session

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok", "active_calls": len(sessions)}

    @app.get("/media/{key}.wav")
    async def media_file(key: str) -> Response:
        audio = media.get(key)
        if audio is None:
            raise HTTPException(status_code=404)
        return Response(content=audio, media_type="audio/wav")

    @app.post("/voice/incoming")
    async def incoming(call: IncomingCall) -> dict:
        prune()
        caller_hash = call_log.start(call.call_id, call.caller, call.line)
        session = CallSession(call_id=call.call_id, caller_hash=caller_hash, line=call.line)
        sessions[call.call_id] = session
        try:
            return {
                "actions": [
                    await say("welcome", "wo"),
                    await say("welcome", "fr"),
                    await say("choose_language", "wo"),
                    await say("choose_language", "fr"),
                    act.gather(url("/voice/menu")),
                ]
            }
        except VoiceAPIError:
            return fallback(session)

    @app.post("/voice/menu")
    async def menu(entry: MenuInput) -> dict:
        session = get_session(entry.call_id)
        if session is None:
            return {"actions": [act.hangup()]}
        digit = entry.digits.strip()[:1]
        try:
            if session.stage == Stage.LANGUAGE:
                return await choose_language(session, digit)
            if session.stage == Stage.MAIN:
                return await choose_main(session, digit)
            if session.stage == Stage.AI:
                if digit == "0":
                    return await to_human(session, "dtmf_0")
                return {"actions": [act.record(url("/voice/turn"))]}
            return {"actions": [act.hangup()]}
        except VoiceAPIError:
            return fallback(session)

    async def choose_language(session: CallSession, digit: str) -> dict:
        chosen = {"1": "wo", "2": "fr"}.get(digit)
        if chosen is None:
            if digit:
                session.invalid += 1
            else:
                session.timeouts += 1
            if session.invalid + session.timeouts < 2:
                prefix = [await say("invalid_choice", "fr")] if digit else []
                return {
                    "actions": prefix
                    + [
                        await say("choose_language", "wo"),
                        await say("choose_language", "fr"),
                        act.gather(url("/voice/menu")),
                    ]
                }
            chosen = DEFAULT_LANGUAGE
        session.language = chosen
        session.invalid = session.timeouts = 0
        call_log.update(session.call_id, language=chosen)
        call_log.event(session.call_id, "language", value=chosen, keyed=bool(digit in ("1", "2")))
        return await main_menu(session)

    async def choose_main(session: CallSession, digit: str) -> dict:
        if digit == "1":
            return await start_assistant(session)
        if digit == "2":
            return await to_human(session, "menu_2")
        if digit == "9":
            return await main_menu(session)
        if not digit:
            session.timeouts += 1
            if session.timeouts >= 2:
                # The caller may not use the keypad: let them simply speak.
                return await start_assistant(session)
            return await main_menu(session)
        session.invalid += 1
        return await main_menu(session, [await say("invalid_choice", session.lang)])

    @app.post("/voice/turn")
    async def turn(entry: TurnInput) -> dict:
        session = get_session(entry.call_id)
        if session is None:
            return {"actions": [act.hangup()]}
        try:
            if entry.digits:
                return await menu(MenuInput(call_id=entry.call_id, digits=entry.digits))
            if session.stage != Stage.AI:
                return await main_menu(session)
            return await assistant_turn(session, entry)
        except VoiceAPIError:
            return fallback(session)

    async def assistant_turn(session: CallSession, entry: TurnInput) -> dict:
        try:
            audio = base64.b64decode(entry.audio_base64 or "", validate=True)
        except (ValueError, binascii.Error):
            audio = b""
        started = time.perf_counter()

        transcript = ""
        if audio:
            try:
                result = await client.asr(
                    audio, fmt=entry.format, sample_rate=entry.sample_rate, language_hint=session.lang
                )
                transcript = result.text
            except VoiceAPIError as exc:
                call_log.event(session.call_id, "asr_error", error=str(exc)[:200])
                return await to_human(session, "service_error", [await say("service_error", session.lang)])

        if not transcript:
            session.empty_turns += 1
            call_log.event(session.call_id, "empty_turn", count=session.empty_turns)
            if session.empty_turns >= 3:
                session.empty_turns = 0
                return await main_menu(session)
            return {"actions": [await say("not_understood", session.lang), act.record(url("/voice/turn"))]}
        session.empty_turns = 0

        flags = local_flags(transcript)
        session.history.append({"role": "user", "content": transcript})
        reply: ChatReply | None = None
        try:
            reply = await client.chat(
                session_id=session.call_id,
                language=session.lang,
                messages=session.history[-MAX_HISTORY:],
                context={"channel": "phone", "service": "la-ligne-rose", "turn": session.turns + 1},
            )
        except VoiceAPIError as exc:
            call_log.event(session.call_id, "chat_error", error=str(exc)[:200])

        session.turns += 1
        if reply is not None:
            session.history.append({"role": "assistant", "content": reply.reply})
            if reply.language in LANGUAGES:
                session.language = reply.language
        decision = decide(flags=flags, reply=reply, turns=session.turns, max_turns=settings.max_ai_turns)

        call_log.update(session.call_id, turns=session.turns, language=session.lang)
        if decision.emergency:
            call_log.update(session.call_id, emergency=1)
        call_log.event(
            session.call_id,
            "turn",
            n=session.turns,
            transcript=transcript,
            reply=reply.reply if reply else None,
            decision=decision.target,
            reason=decision.reason,
            latency_ms=int((time.perf_counter() - started) * 1000),
        )

        spoken = [await speak(reply.reply, reply.language)] if reply is not None else []
        if decision.target == "human":
            if decision.emergency:
                spoken.append(await say("emergency", session.lang))
            elif reply is None:
                spoken.append(await say("service_error", session.lang))
            # The service reply already announces the transfer when it asked for it.
            announced = reply is not None and (reply.handoff or reply.emergency)
            return await to_human(session, decision.reason, spoken, announce=not announced)
        if decision.target == "end":
            session.stage = Stage.ENDED
            return {
                "actions": spoken
                + [await say("max_turns", session.lang), await say("goodbye", session.lang), act.hangup()]
            }
        return {"actions": spoken + [act.record(url("/voice/turn"))]}

    @app.post("/voice/hangup")
    async def hangup(entry: Hangup) -> dict:
        sessions.pop(entry.call_id, None)
        call_log.end(entry.call_id, entry.reason)
        return {"actions": []}

    @app.get("/stats")
    async def stats(x_admin_token: str | None = Header(default=None)) -> dict:
        if not settings.admin_token:
            raise HTTPException(status_code=404)
        if x_admin_token != settings.admin_token:
            raise HTTPException(status_code=401)
        return call_log.stats()

    return app
