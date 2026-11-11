"""Decide, after each spoken turn, whether the call stays with the voice
assistant or goes to a human health professional.

Two sources of truth, the safer one wins:
  1. flags returned by the Andakia Voice API (`handoff`, `emergency`);
  2. a small local keyword safety net, so a request for a human or a sign of
     emergency is never missed because of one bad answer from the service.

The keyword lists are a starting point. They must be reviewed and extended
with the health partners and with real (consented) call data.
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Literal

from .voice_api import ChatReply

Target = Literal["ai", "human", "end"]

HANDOFF_KEYWORDS: dict[str, tuple[str, ...]] = {
    "fr": ("medecin", "docteur", "sage-femme", "sage femme", "infirmiere", "parler a quelqu'un", "une personne"),
    "wo": ("doktoor", "fajkat", "sage-femme", "sage femme", "wax ak nit"),
}

EMERGENCY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "fr": ("urgence", "hemorragie", "saigne beaucoup", "evanoui", "convulsion", "je vais accoucher", "viol"),
    "wo": ("deret bu bare", "dafa xem", "lu jamp"),
}


def _fold(value: str) -> str:
    """Lower case, accents removed, so keyword matching survives ASR spelling."""
    decomposed = unicodedata.normalize("NFKD", value.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def _matches(transcript: str, lists: dict[str, tuple[str, ...]]) -> bool:
    folded = _fold(transcript)
    return any(_fold(k) in folded for words in lists.values() for k in words)


@dataclass(frozen=True)
class LocalFlags:
    handoff: bool
    emergency: bool


def local_flags(transcript: str) -> LocalFlags:
    # Both languages are checked on purpose: callers mix Wolof and French.
    return LocalFlags(
        handoff=_matches(transcript, HANDOFF_KEYWORDS),
        emergency=_matches(transcript, EMERGENCY_KEYWORDS),
    )


@dataclass(frozen=True)
class RouteDecision:
    target: Target
    reason: str
    emergency: bool = False


def decide(
    *,
    flags: LocalFlags,
    reply: ChatReply | None,
    turns: int,
    max_turns: int,
) -> RouteDecision:
    emergency = flags.emergency or bool(reply and reply.emergency)
    if emergency:
        return RouteDecision("human", "emergency", emergency=True)
    if reply is None:
        return RouteDecision("human", "service_error")
    if flags.handoff or reply.handoff:
        return RouteDecision("human", reply.handoff_reason or "caller_request")
    if turns >= max_turns:
        return RouteDecision("end", "max_turns")
    return RouteDecision("ai", "continue")
