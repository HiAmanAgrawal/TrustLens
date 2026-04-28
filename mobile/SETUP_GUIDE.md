# TrustLens Flutter App — Complete Setup Guide

> **Know what you consume.** — A health-safety platform that verifies medicines and packaged foods.

---

## Table of Contents
1. [System Requirements](#system-requirements)
2. [IDE Setup](#ide-setup)
3. [Flutter Installation](#flutter-installation)
4. [Android Setup](#android-setup)
5. [Running the App](#running-the-app)
6. [Troubleshooting](#troubleshooting)

---

## System Requirements

### Minimum Hardware
- **RAM**: 8 GB (16 GB recommended)
- **Disk Space**: 10 GB free (for Flutter SDK, Android SDK, emulator)
- **OS**: Windows 10+, macOS 10.14+, or Linux (Ubuntu 18.04+)

### Software Prerequisites
- **Git**: [Download](https://git-scm.com/download/win)
- **JDK 11+**: [Download OpenJDK](https://adoptopenjdk.net/) or use Android Studio's bundled JDK

---

## IDE Setup

### Option 1: Visual Studio Code (Lightweight)

#### 1.1 Install VS Code
- Download from [code.visualstudio.com](https://code.visualstudio.com)
- Install and launch

#### 1.2 Install Required Extensions
Open VS Code and go to **Extensions** (Ctrl+Shift+X) and install:

| Extension | Publisher | Purpose |
|-----------|-----------|---------|
| **Flutter** | Dart Code | Flutter development, hot reload, device management |
| **Dart** | Dart Code | Dart language support, syntax highlighting, debugging |
| **Awesome Flutter Snippets** | Nash | Code snippets for Flutter widgets |
| **Pubspec Assist** | Jeroen Meijer | Auto-complete for `pubspec.yaml` dependencies |
| **Error Lens** | Alexander | Inline error messages |

**Installation Steps:**
1. Click the Extensions icon (or press Ctrl+Shift+X)
2. Search for "Flutter"
3. Click "Install" on the first result (by Dart Code)
4. Repeat for "Dart", "Awesome Flutter Snippets", "Pubspec Assist"

#### 1.3 Verify Installation
- Open Command Palette (Ctrl+Shift+P)
- Type `Flutter: Run Flutter Doctor`
- Wait for the output — all checks should be green ✓

---

### Option 2: Android Studio (Full-Featured)

#### 2.1 Install Android Studio
- Download from [developer.android.com/studio](https://developer.android.com/studio)
- Run installer, follow setup wizard
- Choose "Standard" installation

#### 2.2 Install Flutter & Dart Plugins
1. Open Android Studio
2. Go to **File → Settings → Plugins** (or **Android Studio → Preferences → Plugins** on macOS)
3. Search for and install:
   - **Flutter** (includes Dart automatically)
   - **Dart**

#### 2.3 Configure Flutter SDK Path
1. Go to **File → Settings → Languages & Frameworks → Flutter**
2. Set **Flutter SDK path** to your Flutter installation (e.g., `C:\flutter`)
3. Click **Apply** and **OK**

---

## Flutter Installation

### Step 1: Download Flutter SDK

#### Windows
1. Download Flutter SDK from [flutter.dev/docs/get-started/install/windows](https://flutter.dev/docs/get-started/install/windows)
2. Extract the ZIP file to a stable location (e.g., `C:\flutter`)
   - **Avoid**: Desktop, Downloads, or paths with spaces
3. Do NOT extract to `Program Files` (requires admin permissions)

#### macOS
```bash
cd ~/development
git clone https://github.com/flutter/flutter.git -b stable
```

#### Linux (Ubuntu)
```bash
cd ~/development
git clone https://github.com/flutter/flutter.git -b stable
```

### Step 2: Add Flutter to PATH

#### Windows
1. Open **Environment Variables**:
   - Press `Win + X` → **System**
   - Click **Advanced system settings**
   - Click **Environment Variables**
2. Under **User variables**, click **New**
   - Variable name: `PATH`
   - Variable value: `C:\flutter\bin` (adjust if you extracted elsewhere)
3. Click **OK** three times
4. **Restart your terminal/IDE**

#### macOS / Linux
Add to `~/.zshrc` or `~/.bashrc`:
```bash
export PATH="$PATH:$HOME/development/flutter/bin"
```
Then reload:
```bash
source ~/.zshrc
```

### Step 3: Verify Flutter Installation
Open a **new terminal/PowerShell** and run:
```bash
flutter --version
```
Expected output:
```
Flutter 3.7.x • channel stable
Dart 3.x.x
```

---

## Android Setup

### Step 1: Install Android Studio (if not already done)
- Download from [developer.android.com/studio](https://developer.android.com/studio)
- Run installer, select "Standard" setup

### Step 2: Install Android SDK Components
1. Open Android Studio
2. Go to **Tools → SDK Manager**
3. Install the following under **SDK Platforms**:
   - **Android 14** (API level 34) — recommended
   - **Android 13** (API level 33) — minimum
4. Under **SDK Tools**, ensure these are installed:
   - **Android SDK Command-line Tools** (latest)
   - **Android SDK Build-Tools** (latest)
   - **Android Emulator**
   - **Android SDK Platform-Tools**

### Step 3: Accept Android Licenses
Open terminal and run:
```bash
flutter doctor --android-licenses
```
Press `y` and Enter for each prompt.

### Step 4: Create an Android Virtual Device (Emulator)
1. In Android Studio, go to **Tools → Device Manager**
2. Click **Create Device**
3. Select **Pixel 6** (or any modern phone)
4. Select **Android 13** or **14** as the system image
5. Click **Finish**
6. The emulator will appear in the device list

### Step 5: Verify Android Setup
Run in terminal:
```bash
flutter doctor
```

Expected output (all green ✓):
```
Doctor summary (to see all details, run flutter doctor -v):
[✓] Flutter (Channel stable, 3.7.x, on Windows 10)
[✓] Android toolchain - develop for Android devices (Android SDK version 34.0.0)
[✓] Chrome - develop for the web
[✓] Visual Studio Code (version 1.x)
[✓] Connected device (1 available)
```

---

## Running the App

### Step 1: Clone the Repository
```bash
git clone https://github.com/yourusername/TrustLens.git
cd TrustLens/mobile
```

### Step 2: Install Dependencies
```bash
flutter pub get
```
This downloads all packages listed in `pubspec.yaml`.

### Step 3: Run on Android Emulator

#### 3a. Start the Emulator
```bash
flutter emulators
```
Find your emulator name (e.g., `Pixel_6_API_34`), then:
```bash
flutter emulators --launch Pixel_6_API_34
```
Wait 30-60 seconds for the emulator to fully boot.

#### 3b. Run the App
```bash
flutter run
```
The app will build and launch on the emulator. You'll see:
```
Launching lib/main.dart on Android SDK built for x86 in debug mode...
...
Application finished.
```

### Step 4: Run on Web (Chrome)
```bash
flutter run -d chrome
```
The app opens in a new Chrome window. Press `r` to hot reload.

### Step 5: Run on Physical Device (Android Phone)

#### 5a. Enable USB Debugging
1. On your Android phone, go to **Settings → About phone**
2. Tap **Build number** 7 times to unlock Developer options
3. Go to **Settings → Developer options**
4. Enable **USB Debugging**
5. Connect phone to computer via USB cable
6. Accept the "Allow USB debugging?" prompt on your phone

#### 5b. List Connected Devices
```bash
flutter devices
```
You should see your phone listed:
```
Android (Android 13.0) • emulator-5554 • android-x86 • Android 13 (API 33)
```

#### 5c. Run on Your Phone
```bash
flutter run -d emulator-5554
```
(Replace `emulator-5554` with your device ID from the list above)

---

## Development Workflow

### Hot Reload (Fastest)
While the app is running, press `r` in the terminal:
```
r Hot reload. 
```
This reloads code changes **without losing app state**. Takes ~1 second.

### Hot Restart
Press `R` in the terminal:
```
R Hot restart.
```
This rebuilds the entire app **and resets state**. Takes ~3 seconds.

### Full Rebuild
Press `q` to quit, then run again:
```bash
flutter run
```
Use this if hot reload fails or you've changed native code.

---

## Building for Release

### Android APK (for distribution)
```bash
flutter build apk --release
```
Output: `build/app/outputs/flutter-app.apk`

### Android App Bundle (for Google Play Store)
```bash
flutter build appbundle --release
```
Output: `build/app/outputs/bundle/release/app-release.aab`

### Web (static files)
```bash
flutter build web --release
```
Output: `build/web/` (upload to any web server)

---

## Troubleshooting

### Issue: "flutter: command not found"
**Solution**: Flutter is not in your PATH.
1. Verify Flutter is installed: Check if `C:\flutter\bin` exists (Windows) or `~/development/flutter/bin` (macOS/Linux)
2. Re-add to PATH (see [Step 2 above](#step-2-add-flutter-to-path))
3. Restart your terminal/IDE

### Issue: "Android SDK not found"
**Solution**:
```bash
flutter config --android-sdk-path "C:\Android\Sdk"
```
(Adjust path if Android SDK is installed elsewhere)

### Issue: Emulator won't start
**Solution**:
1. Check if virtualization is enabled in BIOS (Windows)
2. Try a different emulator: `flutter emulators --launch <name>`
3. Restart Android Studio and try again

### Issue: "Gradle build failed"
**Solution**:
```bash
flutter clean
flutter pub get
flutter run
```

### Issue: Hot reload not working
**Solution**:
1. Press `q` to quit
2. Run `flutter run` again
3. If still broken, do a full rebuild: `flutter clean && flutter run`

### Issue: App crashes on startup
**Solution**:
1. Check the terminal for error messages
2. Run with verbose logging: `flutter run -v`
3. Check `lib/main.dart` for syntax errors

---

## Useful Commands

| Command | Purpose |
|---------|---------|
| `flutter doctor` | Verify all dependencies are installed |
| `flutter devices` | List connected devices/emulators |
| `flutter pub get` | Download dependencies |
| `flutter pub upgrade` | Update all dependencies |
| `flutter clean` | Delete build artifacts (use if stuck) |
| `flutter analyze` | Check for code issues |
| `flutter test` | Run unit tests |
| `flutter run -v` | Run with verbose logging (for debugging) |

---

## Next Steps

1. **Explore the codebase**: Open `lib/main.dart` and familiarize yourself with the structure
2. **Read the README**: Check `mobile/README.md` for architecture details
3. **Try hot reload**: Make a small change to `lib/features/home/home_screen.dart` and press `r`
4. **Test dark mode**: Go to Profile screen and toggle dark mode
5. **Connect to backend**: Update API endpoints in `lib/services/api_service.dart`

---

## Support

- **Flutter Docs**: [flutter.dev/docs](https://flutter.dev/docs)
- **Dart Docs**: [dart.dev/guides](https://dart.dev/guides)
- **Stack Overflow**: Tag with `flutter` and `dart`
- **GitHub Issues**: Report bugs in the TrustLens repo

---

**Happy coding! 🚀**
