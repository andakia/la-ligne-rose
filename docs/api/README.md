# Andakia Voice API: the three endpoints used by the line

The Andakia Voice API is an external, proprietary service. It is not part of
this repository. This page documents only the contract the phone line relies
on. `mock_api/server.py` implements the same contract for local work.

- Base URL: `ANDAKIA_API_URL` (example: `https://api.example.com`)
- Authentication: `Authorization: Bearer $ANDAKIA_API_KEY` on every request
- Content type: `application/json`, UTF-8
- Audio: base64 inside JSON, WAV, mono, 16-bit, 8000 Hz by default (telephone quality)
- Languages: `wo` (Wolof), `fr` (French)

| Endpoint | Purpose | Request | Response |
|---|---|---|---|
| `POST /asr` | caller audio to text | [asr.request.json](asr.request.json) | [asr.response.json](asr.response.json) |
| `POST /chat` | conversation to next reply, with routing flags | [chat.request.json](chat.request.json) | [chat.response.json](chat.response.json), [emergency](chat.response.emergency.json) |
| `POST /tts` | reply text to audio | [tts.request.json](tts.request.json) | [tts.response.json](tts.response.json) |

Errors use standard HTTP status codes with a JSON body, see
[error.response.json](error.response.json). The line retries once on network
errors and `5xx` answers, never on `4xx`.

## POST /asr

```bash
curl -s "$ANDAKIA_API_URL/asr" \
  -H "Authorization: Bearer $ANDAKIA_API_KEY" \
  -H "Content-Type: application/json" \
  -d @docs/api/asr.request.json
```

```json
{ "text": "Am naa laaj ci sama wér-gi-yaram.", "language": "wo", "confidence": 0.87 }
```

`text` is empty when no speech was heard. `language_hint` is optional.

## POST /chat

```bash
curl -s "$ANDAKIA_API_URL/chat" \
  -H "Authorization: Bearer $ANDAKIA_API_KEY" \
  -H "Content-Type: application/json" \
  -d @docs/api/chat.request.json
```

```json
{
  "reply": "Waaw, maa ngi lay jokkale ak ab fajkat.",
  "language": "wo",
  "handoff": { "requested": true, "reason": "caller_request" },
  "safety": { "emergency": false }
}
```

- `messages` is the conversation so far, oldest first, `role` is `user` or `assistant`.
- `language` in the answer is the language of `reply`. It may differ from the
  request when the caller switches language.
- `handoff.requested = true` means the caller should be put through to a
  health professional. `safety.emergency = true` means the line must also play
  its emergency message. The line applies its own keyword safety net on top
  of these flags (see `ligne_rose/routing.py`).

## POST /tts

```bash
curl -s "$ANDAKIA_API_URL/tts" \
  -H "Authorization: Bearer $ANDAKIA_API_KEY" \
  -H "Content-Type: application/json" \
  -d @docs/api/tts.request.json
```

```json
{ "audio_base64": "UklGRjQAAABXQVZF...", "format": "wav", "sample_rate": 8000, "duration_ms": 2100 }
```

## Try the examples against the mock

```bash
uvicorn mock_api.server:app --port 9000 &
export ANDAKIA_API_URL=http://localhost:9000 ANDAKIA_API_KEY=demo-key-not-real
curl -s "$ANDAKIA_API_URL/chat" -H "Authorization: Bearer $ANDAKIA_API_KEY" \
  -H "Content-Type: application/json" -d @docs/api/chat.request.json
```
