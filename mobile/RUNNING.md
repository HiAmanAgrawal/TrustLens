# TrustLens — Running the Full Stack

This guide covers how to run the Flutter app connected to the real backend.

---

## Prerequisites

| Tool | Version | Notes |
|---|---|---|
| Python | 3.10+ | For the backend |
| Flutter | 3.x | For the mobile/web app |
| ngrok | 3.x | For tunneling (physical device or web) |

---

## Step 1 — Start the Backend

Open a terminal in `d:\TrustLens\backend` and run:

```bash
python run.py
```

This starts uvicorn on `http://0.0.0.0:8000` with hot reload enabled.

You should see:
```
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     Application startup complete.
```

> **Note:** The backend binds to `0.0.0.0` so it is reachable from the Android emulator (`10.0.2.2`) and from physical devices on the same LAN.

---

## Step 2 — Start ngrok (for Web / Physical Device)

> Skip this step if you are using an **Android emulator** — it can reach the backend directly at `http://10.0.2.2:8000`.

Open a **second terminal** and run:

```bash
ngrok http 8000
```

ngrok will display a forwarding URL like:
```
Forwarding   https://commotion-attitude-shadily.ngrok-free.dev -> http://localhost:8000
```

**Copy the `https://...` URL** — you will need it in Step 4.

> If `ngrok` is not found, add its folder to your Windows PATH:  
> `System Properties → Environment Variables → User PATH → Add ngrok folder`

---

## Step 3 — Run the Flutter App

### Android Emulator
```bash
cd mobile
flutter run
```
The default backend URL (`http://10.0.2.2:8000`) works out of the box — skip Step 4.

### Chrome / Web
```bash
cd mobile
flutter run -d chrome
```
You **must** complete Step 4 to set the ngrok URL before scanning.

### Physical Device (USB)
```bash
cd mobile
flutter run
```
You **must** complete Step 4 to set the ngrok URL (or your machine's LAN IP).

---

## Step 4 — Set the Backend URL in the App

> Required for: **Chrome/Web** and **physical devices**.  
> Not required for: **Android emulator** (uses `http://10.0.2.2:8000` by default).

1. Open the app and navigate to the **Profile** tab (bottom nav, rightmost icon)
2. Scroll down to the **Backend Server** section
3. Clear the existing URL and type your ngrok URL, e.g.:
   ```
   https://commotion-attitude-shadily.ngrok-free.dev
   ```
4. Press **Enter / Done** on the keyboard to confirm
5. The "Current:" label below the field should update to your new URL

---

## Step 5 — Test a Scan

1. Tap the **scan FAB** (blue circular button in the bottom nav)
2. Choose **Medicine** or **Food**
3. Pick an input method:
   - **Camera** — take a photo of a medicine/food label
   - **Upload** — choose an image from your gallery
   - **Enter Code** — type a barcode, QR code, or product URL
4. Wait for the result (the backend pipeline can take 10–30 seconds)
5. The **Scan Result** screen will show verdict, score, evidence, and notes

---

## Step 6 — Use the AI Chat

1. From the **Scan Result** screen, tap **Ask AI**
2. The chat automatically loads context from your scan
3. Ask follow-up questions about the product, ingredients, or safety
4. Standalone chat is also available via the **AI Chat** quick action on the Home screen

---

## Default URLs per Platform

| Platform | Default Base URL | Notes |
|---|---|---|
| Android Emulator | `http://10.0.2.2:8000` | Host machine's localhost |
| Chrome / Web | `http://localhost:8000` | Same machine, set ngrok URL manually |
| Physical Device | `http://10.0.2.2:8000` | Won't work — must set LAN IP or ngrok |

---

## Troubleshooting

**"Could not connect to the backend"**
- Make sure `python run.py` is running in `d:\TrustLens\backend`
- Check the URL in Profile → Backend Server matches your ngrok URL
- For Chrome: ngrok must be running (browser blocks plain `http://localhost`)

**"Scan Failed" after long wait**
- The backend pipeline (OCR + scraping) can take up to 30 seconds
- Check the backend terminal for Python errors
- Ensure your `.env` file has `GOOGLE_API_KEY` set for AI features

**ngrok "command not found"**
- Add the ngrok folder to Windows PATH, or run it by full path:
  ```
  C:\path\to\ngrok\ngrok.exe http 8000
  ```

**CORS errors in browser console**
- The backend now has `CORSMiddleware` with `allow_origins=["*"]`
- Restart the backend if you updated `main.py` recently

---

## Environment Variables (Backend)

Create `d:\TrustLens\backend\.env`:

```env
GOOGLE_API_KEY=your_google_api_key_here
# Optional — only needed for WhatsApp webhook
TWILIO_ACCOUNT_SID=...
TWILIO_AUTH_TOKEN=...
TWILIO_WHATSAPP_FROM=...
```
