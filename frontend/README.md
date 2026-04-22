# frontend/

Admin / B2B dashboard for TrustLens. The consumer experience is WhatsApp — this
app is for internal users (operators reviewing failed scrapes, B2B clients
checking bulk verification results).

## Stack

- **Next.js 14** (App Router)
- **TypeScript**
- **Tailwind CSS**

This folder is intentionally empty. Scaffold it once and commit the result:

```bash
cd frontend
npx create-next-app@latest . \
  --typescript \
  --tailwind \
  --app \
  --eslint \
  --src-dir \
  --import-alias "@/*"
```

## Conventions (apply once scaffolded)

- API base URL comes from `NEXT_PUBLIC_API_BASE_URL` — never hardcode it.
- Server components by default; use client components only when you need
  state, effects, or browser APIs.
- Co-locate component, styles, and tests in the same folder.
- Talk to the FastAPI backend via a small typed client in `src/lib/api.ts`
  (codegen from the OpenAPI spec is the eventual goal).

## What lives here long-term

| Page              | Purpose                                                |
| ----------------- | ------------------------------------------------------ |
| `/`               | Today's verification volume, verdict distribution      |
| `/queries`        | Searchable log of recent verifications                 |
| `/scraper-health` | Per-portal scrape success rate, failure traces         |
| `/admin/sources`  | CRUD for data sources (CDSCO mirrors, manufacturer URLs) |
