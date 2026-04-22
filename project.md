
## Executive Summary
**MediCheck** is a WhatsApp-first, India-focused healthcare tool designed to combat the country’s ₹3,000Cr counterfeit medicine crisis. By turning a standard WhatsApp chat into a drug verification engine, MediCheck provides India’s 1.4 billion consumers with an instant, free, and AI-powered way to verify the authenticity and safety of their medicines. 

* **Mission:** To provide a free, instant, and accessible way for Indian consumers to verify medicine authenticity and safety.
* **Vision:** Your medicine guardian lives in WhatsApp.

## The Market Problem
India’s medicine market is plagued by counterfeits, yet consumers lack a unified, accessible tool to verify what they are consuming.
* **Counterfeit Volume:** An estimated 25% (1 in 4) of medicines in India are substandard or fake.
* **Lack of Tooling:** There are zero free, instant consumer verification tools available. 
* **Data Fragmentation:** While the CDSCO publishes hundreds of substandard drug alerts annually, there is no consumer-facing interface to act on them. Furthermore, 40% of OTC medicines are not yet covered by the national Track & Trace system.

---

## How MediCheck Works

<Steps>
{/* Reason: Demonstrates the sequential user journey and backend workflow where order defines the product experience. */}
  <Step title="User Input" subtitle="Zero-install interface">
    The user sends a photo of their medicine barcode, QR code, or batch number to the MediCheck WhatsApp bot.
  </Step>
  <Step title="Parallel Lookup" subtitle="3-second SLA">
    The backend simultaneously queries the official CDSCO DAVA database, state FDA recall PDFs, and community reports to verify authenticity.
  </Step>
  <Step title="AI Safety Analysis" subtitle="Beyond pass/fail">
    The system cross-references the drug against OpenFDA, DrugBank, and PubChem, using an LLM to translate complex medical data into a consumer-friendly safety profile.
  </Step>
  <Step title="Report Delivery" subtitle="Instant WhatsApp reply">
    The user receives a plain-language report containing the authenticity verdict, a 0–10 safety score, and a breakdown of hidden ingredients and risks.
  </Step>
</Steps>

---

## Core Product Features: "Beyond the Packet"
Instead of just a simple pass/fail authenticity check, MediCheck decodes the medicine’s chemical profile and manufacturer history.

* **Overall Safety Score (0–10):** A composite rating combining ingredient risk, manufacturer trust, recalls, and interactions. (0–3: High Risk | 4–6: Caution | 7–10: Safe).
* **Ingredient Decoder:** Translates active/inactive ingredients, flagging synthetic fillers, allergens, and controversial additives hidden in fine print.
* **Side Effect & Interaction Profile:** Highlights common (>10%), rare (<1%), and severe side effects, alongside dangerous combinations (e.g., paracetamol + alcohol, or OTC conflicts).
* **Safe-For Profile:** Explicitly flags demographic risks (e.g., unsafe for pregnant women, diabetics, or children under 12).
* **Manufacturer Trust Score:** Aggregates the CDSCO inspection history, past recalls, and active licence status of the pharmaceutical company.
* **Honest Gap Reporting:** Transparently labels OTC drugs not covered by the Track & Trace system as 'Unverifiable' to maintain user trust, rather than defaulting to 'Safe'.

### Example Verdicts

| Drug | Score | Safety Verdict | Context |
| :--- | :--- | :--- | :--- |
| **Nimesulide (100mg)** | 🔴 0-3 | **High Risk** | Banned in 30+ countries; hepatotoxic in children under 12. Still legally sold OTC in India. |
| **Cetirizine (10mg)** | 🟡 4-6 | **Caution** | Generally safe but causes drowsiness in 14% of users. Interacts with alcohol. |
| **ORS (Rehydration)** | 🟢 7-10 | **Safe** | WHO essential medicine. No serious interactions. Safe for pregnancy/children. |

---

## Technical Architecture
* **Backend Engine:** FastAPI, Python, PostgreSQL, asyncpg, APScheduler. Uses `asyncio.gather` with a strict 3-second timeout for multi-source single-verdict lookups.
* **WhatsApp & Media:** Twilio WABA, Meta Cloud API, pyzbar, Pillow, zxing (DataMatrix, QR, Code128 extraction).
* **Data & AI Layer:** OpenFDA, DrugBank, PubChem, CDSCO DAVA. LLMs (Claude Vision / GPT-4o Vision) are used for unstructured data extraction and plain-language summarization.
* **Private Sector Scraping:** Uses Headless Chrome, Playwright, and CapSolver to bypass CAPTCHAs and scrape private manufacturer QR portals, regardless of layout.

## Business Model
* **Consumer Tier (Free Forever):** Full verification, safety scores, and AI analysis for ordinary citizens via WhatsApp. Drives mass user adoption.
* **B2B Pharmacy & Hospital Tier (₹499–₹999/month):** A bulk verification API and compliance dashboard for institutional buyers. This creates recurring revenue, positioned as cheaper than a single penalty from a drug inspector visit.
