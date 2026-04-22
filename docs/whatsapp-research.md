# WhatsApp integration — free-tier research

> Owner: Abhinandan. Goal: pick one provider for the MVP. This doc is the comparison so we can decide once and stop re-debating it.

We need to **send** templated/free-form messages and **receive** inbound messages (text + media) from WhatsApp users. Three contenders fit the "free or near-free for an MVP" bar.

---

## TL;DR

| Provider                | Best for                              | Free tier (today)                                                           | Setup pain | Production-grade |
| ----------------------- | ------------------------------------- | --------------------------------------------------------------------------- | ---------- | ---------------- |
| **Twilio Sandbox**      | Hackathons, fastest demo              | Free trial credit; sandbox number is free but users must `join <code>` first | Lowest     | No (sandbox only) |
| **Meta WhatsApp Cloud API** | Real users, real number           | 1,000 free service conversations / month per WABA (Meta's published tier)   | Medium     | Yes              |
| **Unipile**             | Multi-channel (WA + LinkedIn + email) | Free dev tier with limited messages; paid above                             | Low        | Yes              |

Recommendation by maturity stage:
- **Day-1 demo to teammates / judges:** Twilio Sandbox.
- **Pilot with real users in India:** Meta WhatsApp Cloud API directly.
- **If we also want LinkedIn / email in the same SDK:** Unipile.

---

## 1. Twilio WhatsApp Sandbox

**What it is.** A shared Twilio test number anyone can use after sending a `join <code>` message. Free during Twilio's trial credit window.

**Pros**
- Zero approvals — working in ~10 minutes.
- Excellent Python SDK (`twilio` package), well-documented webhooks.
- Same code path graduates to a paid Twilio WABA later (only number + auth changes).

**Cons**
- Every recipient must opt into the sandbox by texting the join code first — unusable for public launch.
- Sandbox templates are limited; media inbound works but with restrictions.
- Twilio adds a per-message markup once you leave the trial.

**Webhook model.** Twilio POSTs `application/x-www-form-urlencoded` to your endpoint. Media URLs are signed Twilio URLs (need basic-auth to download).

**Docs.** <https://www.twilio.com/docs/whatsapp/sandbox>

---

## 2. Meta WhatsApp Cloud API

**What it is.** Meta's own hosted WhatsApp Business Platform. No BSP middleman.

**Pros**
- 1,000 free service conversations / month per business (Meta's stated free allowance).
- Real phone number, public users, no opt-in code.
- Cheapest at scale (no BSP markup).

**Cons**
- Requires a Meta Business Manager account, a verified business, and a phone number not already on WhatsApp.
- Template messages must be approved by Meta (can take hours to days).
- Webhook setup needs a public HTTPS URL and a verify-token handshake.

**Webhook model.** Meta POSTs JSON. Media is referenced by `media_id`; you GET it via the Graph API with the access token.

**Docs.** <https://developers.facebook.com/docs/whatsapp/cloud-api>

---

## 3. Unipile

**What it is.** A unified messaging API across WhatsApp, LinkedIn, Telegram, Instagram, email. Single SDK, single webhook shape.

**Pros**
- One integration covers multiple channels — useful if we ever want LinkedIn outreach for the B2B tier.
- Hosted, no Meta Business Manager hoops for the dev tier.
- Free developer tier for testing.

**Cons**
- Adds a third party between us and Meta — outage / pricing risk.
- Smaller community than Twilio or Meta direct.
- Free tier message volume is limited; production needs a paid plan.

**Webhook model.** Unified JSON event shape across providers.

**Docs.** <https://developer.unipile.com>

---

## Decision checklist (fill in when picking)

- [ ] Do we need real public users on day one? → **Meta Cloud**
- [ ] Do we just need a working demo today? → **Twilio Sandbox**
- [ ] Do we want one SDK across WhatsApp + LinkedIn + email? → **Unipile**
- [ ] Who owns the Meta Business verification paperwork? →
- [ ] Which India phone number can we dedicate? →

Once the choice is made, implement the matching adapter under `services/whatsapp/adapters/` and wire it in `services/whatsapp/send_receive.py`.
