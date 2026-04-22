# backend/

The FastAPI HTTP layer for TrustLens. Owns transport, validation, and routing — and **nothing else**. All business logic lives in `services/` (one folder up).

## Layout

```text
backend/
├── app/
│   ├── main.py            # App factory: builds the FastAPI instance, includes routers
│   ├── api/               # Route modules (one per resource)
│   │   ├── routes_health.py
│   │   ├── routes_images.py    # photo input (multipart upload)
│   │   ├── routes_codes.py     # raw barcode/QR string input (JSON)
│   │   └── routes_whatsapp.py
│   ├── core/              # Cross-cutting infra: config, logging
│   ├── schemas/           # Pydantic request/response models (the wire contract)
│   └── services/          # Thin glue functions that adapt services/* to HTTP
└── tests/
```

## Why an app factory?

`create_app()` lets us spin up multiple app instances (one for tests with a different config, one for prod) without import-time side effects. It also keeps `main.py` tiny and declarative.

## System dependencies

A few Python packages wrap C / Rust binaries or browsers that pip cannot install. Run these once per machine before `pip install`:

```bash
# macOS (Homebrew)
brew install zbar tesseract

# Debian / Ubuntu
sudo apt-get install -y libzbar0 tesseract-ocr
```

After `pip install`, fetch the Chromium build Playwright will drive (~150 MB, one-time):

```bash
playwright install chromium
```

The barcode service uses OpenCV's WeChat QR detector for the primary decode pass — it's strictly better than `pyzbar` on the warped, low-contrast QRs that pharma foil packs are notorious for. The detector needs four small model files (~2 MB total). They're auto-downloaded on first use into `~/.cache/trustlens/wechat_qr/`; pre-warm them in CI / Docker by importing `services.barcode.decoder` once at build time, or set `TRUSTLENS_WECHAT_MODEL_DIR` to point at a baked-in copy.

## Run locally

```bash
cd backend
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/playwright install chromium    # only needed the first time
.venv/bin/uvicorn app.main:app --reload
```

The interactive docs land at <http://localhost:8000/docs>.

> **Heads up if you use pyenv** (or any PATH-shimming Python manager):
> after `source .venv/bin/activate`, the bare `uvicorn` command may *still*
> resolve to a pyenv shim pointing at a different Python (commonly 3.9),
> which won't have this project's dependencies and will fail with a
> confusing `ModuleNotFoundError`. Always launch the venv binary by its
> absolute path: `./.venv/bin/uvicorn ...` — or use the helper script
> [`scripts/dev.sh`](../scripts/dev.sh) which does this for you.

## Endpoints (planned)

| Method | Path                  | Purpose                                              |
| ------ | --------------------- | ---------------------------------------------------- |
| GET    | `/health`             | Liveness probe                                       |
| POST   | `/images`             | Upload an image, decode barcode + OCR, return verdict |
| POST   | `/codes`              | Submit an already-decoded barcode / QR string, return verdict |
| POST   | `/webhook/whatsapp`   | Inbound webhook from the WhatsApp provider (handles both photo and text messages) |
| GET    | `/webhook/whatsapp`   | Webhook verification handshake (Meta Cloud requires this) |

Both `/images` and `/codes` produce the same `Verdict` shape — the only difference is what's at the front of the pipeline.

## Conventions

- Routes do **no** business logic — they validate, call a service, format the response.
- Pydantic models in `schemas/` are the contract; treat them like an API spec.
- Settings are loaded once at startup via `core/config.py`. Never read `os.environ` from a route.
