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

A few Python packages wrap C / Rust binaries or browsers that pip cannot install. Install the tools below **before** `pip install -r requirements.txt` (order matters less than having them on `PATH` before you run the app).

### macOS (Homebrew)

```bash
brew install zbar tesseract
```

### Debian / Ubuntu

```bash
sudo apt-get install -y libzbar0 tesseract-ocr
```

### Windows

1. **Python 3.11+** (64-bit) — from [python.org](https://www.python.org/downloads/) or e.g. `winget install Python.Python.3.11`. Enable “Add Python to PATH” during install.

2. **Tesseract** — install a Windows build (e.g. [UB Mannheim Tesseract installer](https://github.com/UB-Mannheim/tesseract/wiki)) or `winget install UB-Mannheim.TesseractOCR`. Ensure `tesseract.exe` is on **PATH**. If `pytesseract` still fails to find it, set `TESSDATA_PREFIX` or point your code/config at the install directory (see [pytesseract](https://github.com/madmaze/pytesseract) docs).

3. **ZBar** (needed for **`pyzbar`** fallback: EAN-13, Code128, etc.) — on Windows this is the fiddliest step: `pyzbar` needs the **ZBar DLLs** discoverable on `PATH`. Options:
   - Install a [ZBar for Windows](https://sourceforge.net/projects/zbar/files/zbar/0.10/) build and add its folder to **PATH**, or  
   - Use **Conda** in this environment: `conda install -c conda-forge zbar`, or  
   - Develop under **WSL2 (Ubuntu)** and use `sudo apt-get install -y libzbar0` — same flow as Linux above.

   OpenCV’s WeChat QR path still decodes many QRs without ZBar, but full parity with macOS/Linux needs ZBar working.

4. **`opencv-contrib-python`**, **`google-genai`**, **`rapidfuzz`**, etc. install via pip on Windows as usual.

### Playwright (all platforms)

After `pip install -r requirements.txt`, install Chromium (~150 MB, one-time):

```bash
playwright install chromium
```

With the venv activated on Windows: same command from `backend` after `.\.venv\Scripts\activate`.

### WeChat QR models (all platforms)

The barcode service uses OpenCV’s WeChat QR detector for the primary decode pass. Four small model files (~2 MB) download automatically on first use:

- **macOS / Linux:** `~/.cache/trustlens/wechat_qr/`
- **Windows:** `%USERPROFILE%\.cache\trustlens\wechat_qr\`

Override with **`TRUSTLENS_WECHAT_MODEL_DIR`** if you want a fixed path (e.g. Docker image). Pre-warm in CI by importing `services.barcode.decoder` once at build time.

## Run locally

### macOS / Linux

```bash
cd backend
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium    # first time only
uvicorn app.main:app --reload
```

Or call the venv binaries by path (avoids pyenv shims):

```bash
.venv/bin/pip install -r requirements.txt
.venv/bin/playwright install chromium
.venv/bin/uvicorn app.main:app --reload
```

Use the repo helper from the **repo root**: [`scripts/dev.sh`](../scripts/dev.sh) (bash) starts `.venv/bin/uvicorn` from `backend/`.

### Windows (PowerShell)

From the **`backend`** folder (sibling of `services/` at the repo root):

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
playwright install chromium
.\.venv\Scripts\uvicorn app.main:app --reload
```

There is no `scripts/dev.sh` equivalent for cmd/PowerShell; always run **`.\.venv\Scripts\uvicorn`** so you use the venv’s Python and packages.

Copy **`.env.example`** (repo root) values into **`backend/.env`** for secrets such as `GOOGLE_API_KEY`.

### Tests

From **`backend`** with the venv activated:

```bash
pytest
```

`backend/conftest.py` adds the repo root to `sys.path` so `services/` imports resolve. If imports fail, run `pytest` from `backend/`, not only from the repo root without that layout.

The interactive docs land at <http://localhost:8000/docs>.

> **Heads up if you use pyenv** (macOS/Linux): after `source .venv/bin/activate`, the bare `uvicorn` command may *still* resolve to a pyenv shim pointing at a different Python (commonly 3.9), which won’t have this project’s dependencies. Prefer `./.venv/bin/uvicorn` or `scripts/dev.sh`.

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
