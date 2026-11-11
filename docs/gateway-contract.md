# Gateway contract: how a telephony platform drives the line

La Ligne Rose does not depend on one telephony vendor. The voice gateway in
front of it (a SIP PBX, or any VoIP provider that supports call webhooks)
calls four HTTP webhooks and executes the actions returned. A thin adapter of
a few dozen lines maps these actions to the gateway's own verbs.

## Webhooks (gateway to line)

| Webhook | When | Body |
|---|---|---|
| `POST /voice/incoming` | a call is answered | `{"call_id": "...", "from": "<caller number>", "to": "<line number>"}` |
| `POST /voice/menu` | after a `gather` | `{"call_id": "...", "digits": "1"}` (`""` on timeout) |
| `POST /voice/turn` | after a `record` | `{"call_id": "...", "audio_base64": "...", "format": "wav", "sample_rate": 8000}` or `{"call_id": "...", "digits": "0"}` if a key was pressed |
| `POST /voice/hangup` | the call ends, whoever hangs up | `{"call_id": "...", "reason": "caller_hangup"}` |

Every answer is `{"actions": [ ... ]}`, executed in order.

## Actions (line to gateway)

| Action | Fields | Gateway does |
|---|---|---|
| `play` | `url` | fetch the WAV from `url` (served by the line at `/media/<key>.wav`) and play it |
| `gather` | `digits`, `timeout_s`, `next` | collect DTMF keys, then POST them to `next` |
| `record` | `max_s`, `silence_ms`, `beep`, `dtmf_interrupt`, `next` | record one utterance (stop on silence or `max_s`), POST it to `next`; a key pressed during recording is posted as `digits` |
| `transfer` | `target` | bridge the call to `target` (for example a SIP URI of the health desk) |
| `hangup` | | end the call |

## Example

```http
POST /voice/incoming
{"call_id": "call-7f3a9c21", "from": "+000000001", "to": "+000000002"}
```

```json
{
  "actions": [
    {"type": "play", "url": "http://localhost:8080/media/3f1c...wav"},
    {"type": "play", "url": "http://localhost:8080/media/9a0b...wav"},
    {"type": "play", "url": "http://localhost:8080/media/51de...wav"},
    {"type": "play", "url": "http://localhost:8080/media/c27e...wav"},
    {"type": "gather", "digits": 1, "timeout_s": 6, "next": "http://localhost:8080/voice/menu"}
  ]
}
```

`scripts/simulate_call.py` plays the role of a gateway and is the reference
implementation of this contract.
