# Roadmap

Milestones are deliberately small so progress is visible weekly. Each phase is shippable on its own.

## Phase 0 — Scaffolding (this commit)
- Monorepo layout with READMEs at every boundary.
- Stub Python modules with typed signatures and intent comments.
- WhatsApp provider research doc.

## Phase 1 — Local end-to-end happy path
- Pick a WhatsApp provider (see [`whatsapp-research.md`](whatsapp-research.md)).
- Implement `services/whatsapp/send_receive.py` against that provider.
- Implement `services/barcode/decoder.py` with `pyzbar` + `pillow` (QR + Code128).
- Implement `services/matcher/engine.py` against a hard-coded mock dataset.
- Wire `backend/app/api/routes_whatsapp.py` so a photo round-trips into a real reply on a dev number.

## Phase 2 — Real data sources
- Add CDSCO DAVA + OpenFDA fetchers behind `services/matcher`.
- Implement `services/scraper/agent.py` with Playwright + CapSolver for one private manufacturer portal.
- Add request caching (Redis) so repeat lookups are sub-second.

## Phase 3 — OCR + AI summary
- Implement `services/ocr/extractor.py` (Tesseract first, LLM-vision fallback).
- Add an LLM summarisation step in `services/matcher` that returns a 0–10 score plus a plain-language paragraph.

## Phase 4 — Admin dashboard
- Run `create-next-app` inside `frontend/`.
- Read-only views: today's queries, verdict distribution, scraper failure logs.

## Phase 5 — Production hardening
- Postgres + Alembic migrations.
- Background workers (APScheduler or Arq) for slow scrapes.
- Docker-compose under `infra/`, then a deploy target.
