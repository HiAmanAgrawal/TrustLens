"""
All conversation prompt templates for the TrustLens WhatsApp agent.

WHY centralise prompts:
  Prompts are user-facing copy — they need i18n, A/B testing, and copy editing
  without touching node logic. Keeping them here means a content change is a
  one-line edit, not a code review.

All templates use the ``t_ai`` wrapper so:
  - English is served from the static JSON catalogue (no API cost).
  - Other languages are either served from the static catalogue (hi, ta) or
    translated on-the-fly by Gemini if USE_AI_I18N=true.

ONBOARDING QUESTIONS (fixed, deterministic — no LLM generation):
  Determinism is critical during onboarding to avoid the bot asking ambiguous
  questions. Every question is a static string from the i18n catalogue.

GREETING (LLM-generated):
  The existing-user greeting is the one place where we allow the LLM to compose
  a natural, personalised reply. It is strictly informational — the prompt
  instructs the model not to make health claims or diagnoses.
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Static onboarding question keys (used with t_ai / t)
# ---------------------------------------------------------------------------

# Keys match entries in app/i18n/en.json
ONBOARDING_WELCOME_KEY = "onboarding.welcome"
ONBOARDING_ASK_NAME_KEY = "onboarding.ask_name"
ONBOARDING_ASK_DIET_KEY = "onboarding.ask_diet"
ONBOARDING_ASK_ALLERGIES_KEY = "onboarding.ask_allergies"
ONBOARDING_ASK_MEDICINES_KEY = "onboarding.ask_medicines"
ONBOARDING_COMPLETE_KEY = "onboarding.complete"
ONBOARDING_INVALID_DIET_KEY = "onboarding.invalid_diet"
ONBOARDING_SKIP_KEY = "onboarding.skip"


# ---------------------------------------------------------------------------
# Greeting LLM prompt
# ---------------------------------------------------------------------------

GREETING_SYSTEM_PROMPT = """\
You are the TrustLens health assistant on WhatsApp. Your role is to help users
verify medicines and grocery products for safety, authenticity, and allergens.

STRICT RULES:
1. Do NOT make any medical claims, diagnoses, or treatment recommendations.
2. Do NOT suggest that any product is medically safe or unsafe for a condition.
3. Keep the greeting warm, brief (2–3 sentences), and action-oriented.
4. Mention 1–2 relevant personalised details from the user's profile (name,
   diet, known allergies, active prescriptions) to show you remember them.
5. End with a prompt to scan a product.
6. Reply in the language: {lang_name}
"""

GREETING_USER_PROMPT = """\
The user's profile:
  Name: {name}
  Dietary preference: {diet}
  Known allergies: {allergies}
  Active medicines: {medicines}

Recent conversation (last {msg_count} messages):
{history}

Generate a warm, personalised welcome-back greeting following the system rules.
"""


# ---------------------------------------------------------------------------
# i18n catalogue additions (we add these keys to the en.json / hi.json etc.)
# These are the default English strings; the i18n loader overwrites them.
# ---------------------------------------------------------------------------

CATALOGUE_ADDITIONS: dict[str, str] = {
    "onboarding.welcome": (
        "👋 *Hi! I'm TrustLens* — your personal product safety assistant.\n\n"
        "In India, 1 in 4 medicines is counterfeit and most grocery labels go unread. "
        "I help you fix that in seconds.\n\n"
        "*📷 Send me a photo of:*\n"
        "• A *medicine* — verify batch, check expiry & flag counterfeits\n"
        "• A *grocery product* — score ingredients, check FSSAI & allergens\n"
        "• A *prescription* — identify each drug and check interactions\n\n"
        "*💬 Or just ask me anything:*\n"
        "_\"Is paracetamol safe with alcohol?\"_\n"
        "_\"What does FSSAI mean?\"_\n\n"
        "Let's set up your safety profile first (takes 30 seconds).\n\n"
        "*What's your name?*"
    ),
    "onboarding.ask_name": "What's your name?",
    "onboarding.ask_diet": (
        "Nice to meet you, *{name}*! 🙏\n\n"
        "What's your dietary preference?\n"
        "Reply: *veg*, *vegan*, *non-veg*, *jain*, or *halal*\n\n"
        "_(This helps me flag products that don't match your diet.)_"
    ),
    "onboarding.ask_allergies": (
        "Got it! Do you have any food allergies or intolerances?\n\n"
        "Examples: peanuts, milk, gluten, eggs, sesame\n"
        "Or reply *none* to skip.\n\n"
        "_(I'll warn you instantly if a scanned product contains these.)_"
    ),
    "onboarding.ask_medicines": (
        "Almost done! Do you take any regular medicines?\n\n"
        "Examples: Metformin, Aspirin, Amlodipine\n"
        "Or reply *none* to skip.\n\n"
        "_(I'll automatically flag dangerous interactions when you scan a new medicine.)_"
    ),
    "onboarding.complete": (
        "✅ *You're all set, {name}!*\n\n"
        "Your safety profile is saved. Here's what to do next:\n\n"
        "📸 *Send a photo* of any medicine or grocery pack\n"
        "💬 *Ask a question* — health, ingredients, safety\n"
        "🔢 *Type a barcode number* to verify a medicine directly\n\n"
        "I've got your back. 🛡️"
    ),
    "onboarding.invalid_diet": (
        "I didn't catch that. Please reply with one of:\n"
        "*veg*, *vegan*, *non-veg*, *jain*, or *halal*"
    ),
    "onboarding.skip": "Skipped ✓",
}
