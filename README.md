# TrustLens

> *Your personal product safety guardian — lives in WhatsApp.*

---

## The Problem We're Solving

Walk into any Indian pharmacy and pick up a medicine. How do you know it's real?

Roughly **1 in 4 medicines sold in India is substandard or counterfeit** — a ₹3,000 crore shadow market that quietly poisons the people it's supposed to heal. The CDSCO publishes hundreds of substandard drug alerts every year, but there is no consumer-facing way to act on that data. The national Track & Trace system doesn't cover 40% of over-the-counter drugs. And the average Indian patient — holding a strip of tablets they bought from a chemist two minutes ago — has zero tools to know if what's in their hand is safe.

Groceries aren't different. Ingredient labels are printed in 6-point font. FSSAI numbers are faked or missing. Allergen declarations are vague. A person with a peanut allergy or celiac disease or diabetes has no practical way to verify a product before it's already in their shopping bag.

The information exists. Regulatory databases, official labs, manufacturer portals, FSSAI registries — all public. But none of it is accessible. It requires a desktop browser, multiple tabs, and 20 minutes of cross-referencing. Nobody does it.

**We built TrustLens to close that gap — in 3 seconds, over WhatsApp, with zero install.**

---

## What TrustLens Does

Send a photo of anything in your hand — a medicine strip, a packet of biscuits, a prescription — and TrustLens replies with a complete safety verdict before you've put your phone down.

**For medicines:**
- Verifies the batch against official records and flags counterfeits
- Checks the expiry date and warns on near-expiry stock
- Reads the label against manufacturer data and scores the match
- Flags dangerous interactions with medicines you've told us you take
- Remembers if you had a reaction to a drug salt before — warns you even on a different brand

**For grocery products:**
- Reads every ingredient the label will admit to
- Checks FSSAI licence status in real-time
- Flags allergens against your personal allergy profile
- Checks vegetarian/vegan/gluten-free/halal compliance against your dietary preference
- Gives a 0-100 trust score backed by WHO and ICMR-NIN nutrition thresholds
- Warns if 5 or more people in the community have reported problems with the same batch


**For general questions:**
- "Is paracetamol safe with alcohol?" → real answer, sourced from Tavily, rephrased clearly
- "How much sodium is too much per day?" → WHO guideline, not a guess
- "What does FSSAI mean?" → explained in plain language

Everything is personalised to a profile built in a 4-step WhatsApp onboarding — name, diet, allergens, regular medicines. No app download. No account registration. Just WhatsApp.

---

## How It Works

```
User sends photo / text
        │
        ▼
  WhatsApp Webhook (Twilio / Meta)
        │
        ├── Image? ──────────────────────────────────────────────┐
        │                                                         │
        ▼                                                         ▼
  Barcode decoder                                      LM Studio vision OCR
  (WeChat QR → pyzbar)                                → Gemini Vision fallback
        │                                             → Tesseract fallback
        │                                                         │
        └──────────────────────┬──────────────────────────────────┘
                               │
                               ▼
                    Auto-classifier
                    (pharma / grocery / prescription)
                               │
              ┌────────────────┼────────────────┐
              ▼                ▼                ▼
        Medicine          Grocery          Prescription
        pipeline          pipeline           pipeline
              │                │                │
    DB lookup +          Gemini extract     pgvector
    Playwright           nutrition /        semantic match
    scraper +            FSSAI /            medicine names
    Tavily fallback      allergens
              │                │                │
              └────────────────┴────────────────┘
                               │
                    Trust Score + Allergen Check
                    + Community Flag + Side-effect Memory
                               │
                    Formatted WhatsApp reply
                               │
                    Product context stored in Redis (2h TTL)
                    → Follow-up Q&A via LangGraph advisor
```

---

## Architecture

### Services (framework-agnostic, importable from anywhere)

| Service | What it does |
|---------|-------------|
| `services/barcode/` | WeChat QR decoder → pyzbar fallback; caches model files locally |
| `services/ocr/` | LM Studio vision → Gemini → Tesseract chain; same prompt for all engines |
| `services/matcher/` | Deterministic field extractor + rapidfuzz comparator; no LLM |
| `services/scraper/` | Playwright headless Chromium for manufacturer portals |
| `services/pipeline/` | Orchestrates the three scan types (medicine / grocery / prescription) |
| `services/whatsapp/` | Provider-agnostic adapter (Twilio / Meta); formatter library |
| `services/grocery/` | Gemini label extraction, FSSAI verifier, nutrition rules, expiry parser |
| `services/search/` | Tavily web search fallback |

### Backend (FastAPI + PostgreSQL + Redis)

| Module | What it does |
|--------|-------------|
| `app/agents/` | LangGraph conversation agent (onboarding, greeting, Q&A) + product advisor ReAct agent with 6 tools |
| `app/services/` | Trust score engine, allergen checker, side-effect memory, refill reminder, alternatives engine, community report service |
| `app/api/v1/` | REST API — users, medicines, prescriptions, scans, community reports, drug reactions, refill reminders |
| `app/core/i18n` | Static i18n catalogue (safety-critical strings never go through AI) + AI translation layer for conversational messages |

### LLM Backbone (priority order, auto-selected)

1. **Anthropic Claude** — best tool-calling accuracy
2. **Google Gemini** — fast, generous free tier, excellent vision
3. **LM Studio** (Qwen3-VL / Qwen2.5-VL local) — private, no API cost, used for vision OCR + chat
4. **OpenAI / GPT-4o-mini** — cloud fallback

### Database (Supabase PostgreSQL + pgvector)

Medicines, salts, batches, prescriptions, user profiles, allergies, medical conditions, scan history, community reports, refill reminders — all in one Supabase instance. Vector columns on `medicines` and `grocery_items` for semantic prescription matching.

---

## Design Principles

**Deterministic for safety, AI for convenience.**
Trust scores, allergen checks, and drug interaction flags use hard-coded thresholds from WHO and ICMR-NIN guidelines — not LLM outputs. The AI handles OCR, natural language Q&A, and conversational flow. Safety decisions are auditable and reproducible.

**Reason transparency.**
Every warning carries a specific reason: *"High sodium (480mg/100g) — above the 400mg guideline."* Not a score, not a label — a sentence a person can act on.

**WhatsApp-first.**
No app. No registration. Works on a ₹3,000 smartphone with a basic data plan. This isn't a constraint — it's the entire distribution strategy for a 500M-user platform.

**Salt-level drug memory.**
When a user reports a reaction to Crocin (paracetamol), the system stores *paracetamol* — not the brand. The next time they scan any paracetamol product, they get the warning automatically, regardless of which company made it.

---

## Getting Started

```bash
# Dependencies (macOS)
brew install zbar tesseract

# Backend
cd backend
python3.11 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
playwright install chromium

# Database
alembic upgrade head

# Run
uvicorn app.main:app --reload
# or: ./scripts/dev.sh

# Testing portal (no WhatsApp needed)
open http://localhost:8000/testing
```

Copy `.env.example` → `.env` and fill in at minimum `DATABASE_URL` and one of `GOOGLE_API_KEY` or start LM Studio with a vision model loaded.

### Key environment variables

```
DATABASE_URL=postgresql+asyncpg://...
GOOGLE_API_KEY=...       # Gemini vision OCR + LLM (optional if LM Studio is running)
OPENAI_API_KEY=...       # pgvector embeddings (text-embedding-3-small)
TAVILY_API_KEY=...       # Web search for unknown products
TWILIO_ACCOUNT_SID=...   # WhatsApp via Twilio Sandbox
TWILIO_AUTH_TOKEN=...
TWILIO_WHATSAPP_FROM=whatsapp:+14155238886
```

---

## Testing the Product

**Quickest path:** open `http://localhost:8000/testing`, upload a grocery/medicine photo, and watch the analysis appear. Then ask follow-up questions in the chat — the product context is preserved for 2 hours.

**WhatsApp:** connect Twilio Sandbox, send your number a WhatsApp message, follow the 4-step onboarding, then send product photos.

**REST API:** full Swagger docs at `http://localhost:8000/docs`. Every feature (community reports, drug reactions, refill reminders, allergen checks) is exposed as a typed endpoint.

---

## Team

**TrustLens** — built for the Indian consumer who deserves to know what they're putting in their body.

| Name | Role |
|------|------|
| Gouri Agarwal | AI and Automation |

| Abhinadan Gupta | Flutter and Web DEV |
| Aman Agrawal | Backend |

---

*"The information to protect yourself exists. We just made it one WhatsApp message away."*
