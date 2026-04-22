# services/whatsapp/

Send and receive WhatsApp messages. The provider (Twilio / Meta Cloud / Unipile)
is undecided — see [`docs/whatsapp-research.md`](../../docs/whatsapp-research.md).

## Layout

```text
whatsapp/
├── send_receive.py     # Public API: send_message(), receive_messages()
└── adapters/           # One file per provider once chosen (twilio.py, meta.py, unipile.py)
```

## Public API (intent)

```python
from services.whatsapp.send_receive import send_message, receive_messages

await send_message(to="+91XXXXXXXXXX", body="Verifying your medicine…")
async for msg in receive_messages():
    ...
```

The functions accept a domain-level message shape and dispatch to whichever
adapter is configured. Routes never import an adapter directly.

## Adding an adapter (when the provider is picked)

1. Create `adapters/<provider>.py` exposing `send(...)` and `parse_inbound(payload)`.
2. Wire it into `send_receive.py` behind a small factory that reads
   `settings.app_env` / `settings.<provider>_*` to decide which to load.
3. Update [`docs/whatsapp-research.md`](../../docs/whatsapp-research.md) with the
   final decision and remove the other adapters from active use (keep them in
   git history for reference).

## Webhook payloads

Webhook handling lives in `backend/app/api/routes_whatsapp.py`. That route
calls `parse_inbound(payload)` here so all provider quirks stay in one folder.
