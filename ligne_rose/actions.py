"""Telephony actions returned to the voice gateway.

La Ligne Rose speaks a small, neutral JSON contract. A thin adapter for the
telephony platform in front of it (a SIP PBX or any VoIP provider with
webhooks) maps each action to its own verbs. See docs/gateway-contract.md.

Every webhook answer has the shape: {"actions": [ ... ]}
"""
from __future__ import annotations

from typing import Any

Action = dict[str, Any]


def play(url: str) -> Action:
    return {"type": "play", "url": url}


def gather(next_url: str, *, digits: int = 1, timeout_s: int = 6) -> Action:
    """Collect DTMF digits, then POST {"call_id", "digits"} to next_url.
    On timeout, POST with "digits": ""."""
    return {"type": "gather", "digits": digits, "timeout_s": timeout_s, "next": next_url}


def record(next_url: str, *, max_s: int = 20, silence_ms: int = 1500) -> Action:
    """Record one caller utterance (ends on silence or max_s), then POST
    {"call_id", "audio_base64", "format", "sample_rate"} to next_url.
    A DTMF key pressed while recording is posted as {"call_id", "digits"}."""
    return {
        "type": "record",
        "max_s": max_s,
        "silence_ms": silence_ms,
        "beep": True,
        "dtmf_interrupt": True,
        "next": next_url,
    }


def transfer(target: str) -> Action:
    return {"type": "transfer", "target": target}


def hangup() -> Action:
    return {"type": "hangup"}
