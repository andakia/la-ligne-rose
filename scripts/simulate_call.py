"""Simulate a phone call against a running line, as a voice gateway would.

    python scripts/simulate_call.py                     # Wolof caller, voice assistant
    python scripts/simulate_call.py --lang fr --say "Je voudrais parler à une sage-femme."

The caller's sentences are turned into audio with the Voice API /tts endpoint
(the mock embeds the text, so its /asr can read it back), then sent to the
line as recorded turns. Every action returned by the line is printed.
"""
from __future__ import annotations

import argparse
import base64
import os
import sys
import uuid
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mock_api.server import read_text  # noqa: E402

DEFAULT_SENTENCES = {
    "wo": ["Am naa laaj ci sama wér-gi-yaram.", "Dama bëgg wax ak ab fajkat."],
    "fr": ["J'ai une question sur mes règles.", "Je voudrais parler à une sage-femme."],
}


def show(line: httpx.Client, answer: dict) -> list[dict]:
    for a in answer["actions"]:
        if a["type"] == "play":
            audio = line.get(a["url"]).content
            print(f"   LINE  says : {read_text(audio) or '<audio>'}")
        else:
            detail = {k: v for k, v in a.items() if k not in ("type", "next")}
            print(f"   LINE  {a['type']:<6}: {detail if detail else ''}")
    return answer["actions"]


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--line", default=os.getenv("LINE_URL", "http://localhost:8080"))
    p.add_argument("--api", default=os.getenv("ANDAKIA_API_URL", "http://localhost:9000"))
    p.add_argument("--lang", choices=("wo", "fr"), default="wo")
    p.add_argument("--say", action="append", help="caller sentence (repeatable)")
    args = p.parse_args()

    key = os.getenv("ANDAKIA_API_KEY", "demo-key-not-real")
    api = httpx.Client(base_url=args.api, headers={"Authorization": f"Bearer {key}"}, timeout=15)
    line = httpx.Client(base_url=args.line, timeout=30)
    call_id = f"sim-{uuid.uuid4().hex[:8]}"

    print(f"CALL {call_id} rings")
    show(line, line.post("/voice/incoming", json={"call_id": call_id, "from": "+000000001", "to": "+000000002"}).json())

    language_key = "1" if args.lang == "wo" else "2"
    print(f"CALLER presses {language_key}")
    show(line, line.post("/voice/menu", json={"call_id": call_id, "digits": language_key}).json())
    print("CALLER presses 1")
    actions = show(line, line.post("/voice/menu", json={"call_id": call_id, "digits": "1"}).json())

    for sentence in args.say or DEFAULT_SENTENCES[args.lang]:
        if actions[-1]["type"] != "record":
            break
        print(f"CALLER says  : {sentence}")
        audio = api.post("/tts", json={"text": sentence, "language": args.lang}).json()["audio_base64"]
        actions = show(line, line.post("/voice/turn", json={"call_id": call_id, "audio_base64": audio}).json())

    line.post("/voice/hangup", json={"call_id": call_id})
    print(f"CALL {call_id} ends")


if __name__ == "__main__":
    main()
