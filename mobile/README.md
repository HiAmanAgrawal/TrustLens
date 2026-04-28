# TrustLens Mobile (Flutter)

> **Know what you consume.** — A health-safety platform that verifies medicines and packaged foods, delivering personalized AI-powered health recommendations.

## Setup Instructions

### Prerequisites

1. **Flutter SDK** (3.7+): [Install Flutter](https://docs.flutter.dev/get-started/install/windows/mobile)
   - Download zip, extract to `C:\flutter`
   - Add `C:\flutter\bin` to system PATH
2. **Android Studio**: [Download](https://developer.android.com/studio)
   - Install Android SDK, SDK Command-line Tools, SDK Build-Tools
   - Create an Android Virtual Device (AVD) for emulation
3. **Accept licenses**: `flutter doctor --android-licenses`
4. **Verify**: `flutter doctor` — all checks should be green (except Xcode on Windows)

### Running the App

#### 1. Install Dependencies
```bash
cd mobile
flutter pub get
```

#### 2. Run on Your Target Device

**Android Emulator** (default):
```bash
flutter run
```

**iOS Simulator** (macOS only):
```bash
flutter run -d ios
```

**Web Browser** (Chrome):
```bash
flutter run -d chrome
```

**Physical Device** (USB connected, debugging enabled):
```bash
flutter devices                    # List connected devices
flutter run -d <device-id>        # Run on specific device
```

#### 3. Hot Reload During Development
Once the app is running, press `r` in the terminal to hot reload (code changes) or `R` for hot restart (state reset).

#### 4. Build for Release
```bash
# Android APK
flutter build apk --release

# iOS IPA (macOS only)
flutter build ios --release

# Web (static files in build/web/)
flutter build web --release
```

---

## Architecture

```
lib/
  main.dart                 # Entry point (ProviderScope → TrustLensApp)
  app.dart                  # MaterialApp.router + ThemeData + GoRouter
  theme/
    app_theme.dart          # All color, typography, shape tokens
    wobbly_borders.dart     # Reusable asymmetric BorderRadius presets
  router/
    app_router.dart         # go_router config with custom page transitions
  features/
    splash/                 # Splash screen (2.5s → auth check)
    auth/                   # Login/Register (email + Google Sign-In)
    onboarding/             # Health intake multi-step flow
    home/                   # Home screen (hero, quick actions, recent scans)
    scan/                   # Scan result screen
    chat/                   # AI Health Chat
    history/                # Scan history with filters
    recommendations/        # AI-powered food recommendations
    profile/                # Health profile (editable, privacy-first)
  widgets/                  # Reusable components (WobblyCard, ChatBubble, etc.)
  models/                   # Data models (ScanResult, HealthProfile, etc.)
  services/                 # API + mock services, storage
  providers/                # Riverpod state management
```

## Design System

**Visual Language**: "Modern Healthcare" — clean, professional, trustworthy.

| Token | Light Mode | Dark Mode | Usage |
|-------|-----------|-----------|-------|
| Background | `#F4F7FE` | `#0D1117` | App background |
| Surface | `#FFFFFF` | `#1A2235` | Cards, dialogs |
| Primary | `#3B82F6` | `#3B82F6` | CTAs, active states, gradients |
| Secondary | `#10B981` | `#10B981` | Links, success, secondary CTAs |
| Warning | `#F59E0B` | `#F59E0B` | Caution badges, warnings |
| Error | `#EF4444` | `#EF4444` | Errors, destructive actions |
| Text Primary | `#0F172A` | `#F1F5F9` | Headings, body text |
| Text Secondary | `#64748B` | `#94A3B8` | Secondary text |
| Border | `rgba(0,0,0,0.06)` | `rgba(255,255,255,0.07)` | Dividers, borders |

**Typography**: Plus Jakarta Sans (all weights 400–700) via `google_fonts`
- Display: 32px / Bold
- Heading 1: 24px / Bold
- Heading 2: 20px / SemiBold
- Body Large: 16px / Regular
- Body Small: 14px / Regular
- Label: 13px / Medium

**Borders**: Clean, consistent `BorderRadius` (no wobbly asymmetry)
- Card: 16px
- Hero/Large: 20px
- Button: 14px
- Input: 12px
- Pill (badges): 999px

**Shadows**: Blue-tinted soft shadows (no hard offsets)
- Card: `rgba(59,130,246, 0.08)` blur 20px
- Button Glow: `rgba(59,130,246, 0.4)` blur 16px
- Elevated: `rgba(59,130,246, 0.1)` blur 32px

**Gradients**: Primary (blue → indigo), Secondary (teal → blue), Warm (amber → red)

**Dark Mode**: Full support via `ThemeMode` toggle on Profile screen. Smooth cross-fade transitions.

## Packages

| Package | Purpose |
|---------|---------|
| `flutter_riverpod` | State management |
| `go_router` | Declarative routing with nested navigation |
| `dio` | HTTP client for API calls |
| `firebase_auth`, `google_sign_in` | Authentication |
| `flutter_secure_storage` | Encrypted local storage (health profile) |
| `shared_preferences` | Settings & lightweight persistence |
| `image_picker` | Camera/gallery image selection |
| `google_fonts` | Plus Jakarta Sans font |
| `lucide_icons` | Hand-drawn style icons |
| `cached_network_image` | Image caching |
| `flutter_animate` | Entrance animations |
| `permission_handler` | Camera/storage permissions |
| `riverpod_annotation` | Code generation for Riverpod |
| `build_runner` | Code generation (dev dependency) |

## Backend Integration Guide

### Existing Endpoints (ready to use)

| Flutter Action | Backend Endpoint | Status |
|---------------|-----------------|--------|
| Medicine/Food scan (image) | `POST /images` (multipart) | **Exists** — auto-classifies pharma vs grocery |
| Scan via code text | `POST /codes` (JSON) | **Exists** |
| Health check | `GET /health` | **Exists** |

### New Endpoints (added/needed)

| Flutter Action | Backend Endpoint | Status |
|---------------|-----------------|--------|
| AI Chat | `POST /api/ai/chat` | **Added** — see `backend/app/api/routes_ai_chat.py` |
| Recommendations | `GET /api/recommendations` | **Needed** — currently mock-only in Flutter |
| Health Profile CRUD | `POST/GET /api/profile` | **Needed** — currently local-only |
| Scan History | `GET /api/history` | **Needed** — currently local-only |
| User Auth | Firebase Auth (client-side) | **Needed** — JWT validation on backend |

### Switching from Mock to Real API

In `lib/providers/service_providers.dart`, replace `MockApiService` with `ApiService`:

```dart
final apiServiceProvider = Provider<ApiService>((ref) {
  return ApiService(baseUrl: 'http://your-backend:8000');
});
```

Then update provider imports from `mockApiServiceProvider` to `apiServiceProvider`.

### AI Chat Backend Setup

The `POST /api/ai/chat` route requires `GOOGLE_API_KEY` in your `.env` for Gemini.
Without it, canned responses are returned (safe for development).

```bash
# In backend/.env
GOOGLE_API_KEY=your_gemini_api_key_here
```

Install the dependency:
```bash
pip install google-genai
```
