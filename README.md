# 🛡️ TrustLens: Know What You're Putting In Your Body — Before It's Too Late

> 🏆 **Official Project Submission — HackIndia Spark 7 – North Region Hackathon**

## 🌟 Executive Summary

TrustLens is India's first AI-powered health safety guardian that lives entirely inside WhatsApp — built in 48 hours for **HackIndia**, India's largest Web3 & AI hackathon. In a country where **1 in 4 medicines is counterfeit** and FSSAI numbers are routinely faked, we give every Indian consumer a real-time safety verdict on any medicine or grocery product — in 3 seconds, with zero app download.

Just send a photo. We do the rest.

**Live Demo:** http://localhost:8000/testing &nbsp;|&nbsp; **Hackathon:** HackIndia 2026

---

## ❓ Problem Statement

Walk into any Indian pharmacy and pick up a medicine. How do you know it's real?

India has a **₹3,000 crore counterfeit medicine market** that quietly harms the people it's supposed to heal. CDSCO publishes hundreds of substandard drug alerts every year — but there's no consumer-facing way to act on that data. The national Track & Trace system doesn't even cover **40% of over-the-counter drugs**.

Groceries aren't different. FSSAI numbers are faked or missing. Allergen declarations are vague. Ingredient labels are printed in 6-point font. A person with a peanut allergy or diabetes has no practical way to verify a product before it's in their bag.

The information to protect yourself exists — in regulatory databases, official labs, manufacturer portals. But accessing it requires a desktop browser, multiple tabs, and 20 minutes of cross-referencing.

**Nobody does it.**

## 🔧 We aim to solve this by:

✅ Letting any Indian consumer verify medicines and groceries in real-time — over WhatsApp, zero install required.

✅ Using AI + official regulatory data (CDSCO, FSSAI, WHO) to generate safety verdicts backed by hard thresholds — not guesswork.

✅ Building a community-powered reporting layer so users can flag bad batches and protect each other.

✅ Personalising every check to the user's allergies, diet, and regular medicines — stored once, applied forever.

---

## 🚀 Technology Stack

| Layer | Technologies |
|-------|-------------|
| **Backend** | Python 3.11, FastAPI, LangGraph |
| **Database** | Supabase PostgreSQL, pgvector, Redis |
| **AI / LLM** | Anthropic Claude, Google Gemini, LM Studio (Qwen3-VL), OpenAI |
| **Vision OCR** | LM Studio → Gemini Vision → Tesseract (fallback chain) |
| **WhatsApp** | Twilio Sandbox / Meta Cloud API |
| **Scraping** | Playwright (headless Chromium) |
| **Search** | Tavily Web Search |
| **Barcode** | WeChat QR decoder → pyzbar fallback |

---

## 🔄 User Flows & Experience

### Complete User Journey

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  User opens     │───▶│  4-Step          │───▶│  Send a photo   │───▶│  Get safety     │
│  WhatsApp       │    │  Onboarding      │    │  of medicine    │    │  verdict in     │
│                 │    │  (name, diet,    │    │  or grocery     │    │  3 seconds      │
│                 │    │  allergens, meds)│    │                 │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘    └─────────────────┘
```

### Medicine Scan Flow

As a user scanning a medicine:

**Wallet Connection & Profile**
- Send any message to TrustLens on WhatsApp to begin
- 4-step onboarding captures your name, diet, allergens, and regular medicines
- Profile stored once — applied to every future scan automatically

**Scan & Verify**
- Send a photo of the medicine strip or box
- Batch checked against official CDSCO records
- Label matched against manufacturer data, expiry date extracted and validated

**Personalised Safety Check**
- Drug interactions flagged against your regular medicines
- Salt-level reaction history applied — not just the brand, the actual compound
- Result delivered in plain language with a specific reason for every warning

### Grocery Scan Flow

As a user scanning a grocery product:

**Scan & Extract**
- Send a photo of the product label or barcode
- Every ingredient extracted automatically by Gemini Vision

**Verify & Score**
- FSSAI licence verified in real-time
- Nutrition values scored against WHO and ICMR-NIN thresholds
- Community batch reports checked — warning fires if 5+ users flagged this batch

**Personalised Result**
- Allergens flagged against your saved allergy profile
- Dietary compliance checked (veg / vegan / gluten-free / halal)
- 0–100 trust score with a plain-language reason behind every flag

### Verification Flow

```
Photo ──▶ OCR / Barcode ──▶ Classifier ──▶ Regulatory DB ──▶ Personal Profile ──▶ Safety Verdict
   │            │                │                │                  │                  │
   ▼            ▼                ▼                ▼                  ▼                  ▼
┌──────┐  ┌──────────┐  ┌─────────────┐  ┌────────────┐  ┌──────────────┐  ┌──────────────┐
│ Snap │  │ Extract  │  │ Medicine /  │  │ CDSCO /    │  │ Allergens /  │  │ Clear result │
│ photo│  │ text &   │  │ Grocery /   │  │ FSSAI /    │  │ Medications /│  │ with reasons │
│      │  │ barcode  │  │ Prescription│  │ WHO data   │  │ Diet prefs   │  │ not scores   │
└──────┘  └──────────┘  └─────────────┘  └────────────┘  └──────────────┘  └──────────────┘
```

---

## 🌟 Competitive Edge & Unique Value

| Feature | Generic Apps | Google Search | TrustLens |
|---------|-------------|---------------|-----------|
| Works on WhatsApp | ❌ | ❌ | ✅ |
| Zero install needed | ❌ | ✅ | ✅ |
| Personalised to your allergens | ❌ | ❌ | ✅ |
| Drug interaction warnings | ❌ | ❌ | ✅ |
| Real-time FSSAI verification | ❌ | ❌ | ✅ |
| Salt-level reaction memory | ❌ | ❌ | ✅ |
| Community batch reporting | ❌ | ❌ | ✅ |
| Backed by WHO / ICMR-NIN data | ❌ | Sometimes | ✅ |

### Our WhatsApp Advantage:

✅ **Deterministic for safety** — Trust scores and allergen flags use hard WHO/ICMR-NIN thresholds. Never an LLM opinion.

✅ **Reason transparency** — Every warning says *why.* "High sodium (480mg/100g) — above the 400mg WHO guideline." Not just a red badge.

✅ **Salt-level memory** — React to Crocin? We store *paracetamol*. Every future paracetamol product triggers the same warning, any brand.

✅ **WhatsApp-first** — Works on a ₹3,000 phone with basic data. 500 million users, zero friction.

---

## 🧪 Features Completed :

✅ **WhatsApp Integration** — Twilio + Meta Cloud API adapter, fully functional  
✅ **4-Step Onboarding** — Name, diet, allergens, regular medicines — stored once  
✅ **Medicine Pipeline** — Batch verification, expiry check, label scoring, interaction flags  
✅ **Grocery Pipeline** — Gemini label extraction, FSSAI verifier, nutrition rules, allergen check  
✅ **Prescription Pipeline** — pgvector semantic matching on medicine names  
✅ **Trust Score Engine** — 0–100 score backed by hard regulatory thresholds  
✅ **Community Reports** — Users can flag bad batches; warnings fire at 5+ reports  
✅ **Side-effect Memory** — Salt-level reaction history applied across all future scans  
✅ **LangGraph Advisor** — Follow-up Q&A with 2-hour product context memory  
✅ **Multi-LLM Fallback** — Claude → Gemini → LM Studio → GPT-4o-mini auto-chain  

---

## 🛠️ Project Setup Instructions

### Backend Setup

```bash
git clone https://github.com/your-username/trustlens.git
cd trustlens/backend
python3.11 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

### Database Setup

```bash
alembic upgrade head
```

### Run the App

```bash
uvicorn app.main:app --reload
```

### Environment Variables

```bash
cp .env.example .env
```

```env
DATABASE_URL=postgresql+asyncpg://...
GOOGLE_API_KEY=...          # Gemini vision OCR + LLM
OPENAI_API_KEY=...          # pgvector embeddings
TAVILY_API_KEY=...          # Web search fallback
TWILIO_ACCOUNT_SID=...
TWILIO_AUTH_TOKEN=...
TWILIO_WHATSAPP_FROM=whatsapp:+14155238886
```

**Requirements:** Python 3.11+, a WhatsApp-connected Twilio or Meta Cloud API account

---

## 🌐 Impact & Vision

TrustLens isn't just a tool — it's a shift in who gets to make informed health decisions in India.

By making regulatory data accessible to anyone with WhatsApp, we're building a future where:

- A first-generation smartphone user in a Tier-3 city can verify their child's medicine in seconds
- People with diabetes, celiac disease, or severe allergies can grocery shop without fear
- Counterfeit medicine sellers lose their invisibility — one scan at a time
- Health literacy becomes a right, not a privilege for those with time and a laptop

What started as a gap in consumer safety has grown into a community-powered safety layer for 500 million WhatsApp users.

---

## 👥 Team

Our team combines expertise in AI systems, backend development, and consumer product design:

| Name | Role |
|------|------|
| **Gouri Agarwal** | AI & Automation |
| **Abhinandan Gupta** | Flutter & Web Dev |
| **Aman Agrawal** | Backend & Automation |

---

> *"The information to protect yourself already exists. We just made it one WhatsApp message away."*
>
> **— Team Meraki**
