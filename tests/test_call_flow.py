from __future__ import annotations

import base64

from fastapi.testclient import TestClient

from mock_api.server import make_wav, read_text

from .conftest import CALLER, LINE, TRANSFER, build


def types(answer: dict) -> list[str]:
    return [a["type"] for a in answer["actions"]]


def said(tc: TestClient, answer: dict) -> list[str]:
    """Texts behind every `play` action (the mock embeds the text in the WAV)."""
    out = []
    for a in answer["actions"]:
        if a["type"] == "play":
            r = tc.get(a["url"].replace("http://testserver", ""))
            assert r.status_code == 200 and r.headers["content-type"] == "audio/wav"
            out.append(read_text(r.content))
    return out


def speak(tc: TestClient, call_id: str, sentence: str) -> dict:
    audio = base64.b64encode(make_wav(sentence)).decode("ascii")
    r = tc.post("/voice/turn", json={"call_id": call_id, "audio_base64": audio, "format": "wav", "sample_rate": 8000})
    assert r.status_code == 200
    return r.json()


def call(tc: TestClient, call_id: str = "call-1") -> dict:
    r = tc.post("/voice/incoming", json={"call_id": call_id, "from": CALLER, "to": LINE})
    assert r.status_code == 200
    return r.json()


def menu(tc: TestClient, call_id: str, digits: str) -> dict:
    r = tc.post("/voice/menu", json={"call_id": call_id, "digits": digits})
    assert r.status_code == 200
    return r.json()


def test_wolof_caller_talks_to_the_assistant(line):
    tc, call_log = line
    first = call(tc)
    assert types(first) == ["play", "play", "play", "play", "gather"]
    assert said(tc, first)[0].startswith("Dalal ak jàmm")

    main = menu(tc, "call-1", "1")
    assert types(main) == ["play", "gather"]
    assert "bësal benn" in said(tc, main)[0]

    intro = menu(tc, "call-1", "1")
    assert types(intro) == ["play", "record"]

    answer = speak(tc, "call-1", "Am naa laaj ci sama wér-gi-yaram.")
    assert types(answer) == ["play", "record"]
    assert said(tc, answer)[0].startswith("Lii ab test la")

    tc.post("/voice/hangup", json={"call_id": "call-1"})
    row = call_log.rows("SELECT language, route, turns, transferred, ended_at FROM calls WHERE call_id='call-1'")[0]
    assert row[:4] == ("wo", "ai", 1, 0) and row[4] is not None


def test_french_caller_asks_for_a_midwife_and_is_transferred(line):
    tc, call_log = line
    call(tc)
    menu(tc, "call-1", "2")
    menu(tc, "call-1", "1")
    answer = speak(tc, "call-1", "Je voudrais parler à une sage-femme.")
    assert types(answer)[-1] == "transfer"
    assert answer["actions"][-1]["target"] == TRANSFER
    assert call_log.rows("SELECT route, transferred FROM calls")[0] == ("human", 1)


def test_emergency_is_flagged_and_transferred(line):
    tc, call_log = line
    call(tc)
    menu(tc, "call-1", "2")
    menu(tc, "call-1", "1")
    answer = speak(tc, "call-1", "Ma soeur saigne beaucoup, c'est une urgence.")
    texts = said(tc, answer)
    assert any("urgence" in t for t in texts)
    assert types(answer)[-1] == "transfer"
    assert call_log.rows("SELECT emergency FROM calls")[0] == (1,)


def test_zero_key_reaches_a_human_during_the_conversation(line):
    tc, _ = line
    call(tc)
    menu(tc, "call-1", "1")
    menu(tc, "call-1", "1")
    r = tc.post("/voice/turn", json={"call_id": "call-1", "digits": "0"})
    assert types(r.json())[-1] == "transfer"


def test_caller_without_keypad_ends_up_speaking_wolof(line):
    tc, call_log = line
    call(tc)
    assert types(menu(tc, "call-1", "")) == ["play", "play", "gather"]  # language menu again
    assert types(menu(tc, "call-1", "")) == ["play", "gather"]  # Wolof by default, main menu
    assert types(menu(tc, "call-1", "")) == ["play", "gather"]  # main menu again
    assert types(menu(tc, "call-1", "")) == ["play", "record"]  # straight to the assistant
    assert call_log.rows("SELECT language, route FROM calls")[0] == ("wo", "ai")


def test_no_professional_available_returns_to_menu(line_no_human):
    tc, _ = line_no_human
    call(tc)
    menu(tc, "call-1", "2")
    answer = menu(tc, "call-1", "2")
    assert types(answer) == ["play", "play", "gather"]
    assert said(tc, answer)[0].startswith("Aucune professionnelle")


def test_max_turns_ends_the_call_politely(line):
    tc, _ = line
    call(tc)
    menu(tc, "call-1", "2")
    menu(tc, "call-1", "1")
    for _ in range(2):
        assert types(speak(tc, "call-1", "J'ai une question sur mes règles."))[-1] == "record"
    last = speak(tc, "call-1", "J'ai une autre question.")
    assert types(last)[-1] == "hangup"


def test_silence_asks_the_caller_to_repeat(line):
    tc, _ = line
    call(tc)
    menu(tc, "call-1", "1")
    menu(tc, "call-1", "1")
    r = tc.post("/voice/turn", json={"call_id": "call-1", "audio_base64": ""})
    assert types(r.json()) == ["play", "record"]
    assert said(tc, r.json())[0].startswith("Déggu ma la")


def test_chat_outage_hands_over_to_a_human():
    app, _ = build(transfer=TRANSFER, fail={"/chat"})
    with TestClient(app) as tc:
        call(tc)
        menu(tc, "call-1", "2")
        menu(tc, "call-1", "1")
        answer = speak(tc, "call-1", "J'ai une question.")
        assert types(answer)[-1] == "transfer"
        assert any("problème technique" in t for t in said(tc, answer))


def test_voice_api_fully_down_still_transfers():
    app, _ = build(transfer=TRANSFER, fail={"/tts", "/asr", "/chat"})
    with TestClient(app) as tc:
        assert call(tc)["actions"] == [{"type": "transfer", "target": TRANSFER}]


def test_unknown_call_is_hung_up(line):
    tc, _ = line
    assert menu(tc, "nope", "1")["actions"] == [{"type": "hangup"}]
