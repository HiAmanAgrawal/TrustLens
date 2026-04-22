"""Barcode / QR / DataMatrix decoder.

Two-stage strategy, in order of robustness:

1. **OpenCV's WeChat QR detector** — neural-net finder + super-resolution.
   Handles warped foil packs, glare, blur, and rotation that defeat
   ``pyzbar``. This is the primary path for QR codes (the dominant case
   for pharma + grocery).
2. **pyzbar (libzbar)** — broad symbology coverage (EAN-13, Code128,
   ITF, …). Used as a fallback for non-QR codes and when WeChat misses.

Both passes also report **detected-but-undecoded** outcomes: if WeChat
locates a QR but can't recover the payload (damaged modules, partial
clip), we surface that distinct signal so the API can tell the user
"there's a QR there, but please retake the photo" instead of the much
less useful "no barcode found".

Sync rather than async on purpose — both libraries are CPU-bound C
code; wrapping them in async would add overhead without unblocking
anything. Callers that need async should run this through
``asyncio.to_thread``.
"""

from __future__ import annotations

import io
import logging
import os
import threading
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from PIL import Image, ImageOps

logger = logging.getLogger(__name__)

DecodeStatus = Literal["decoded", "detected_undecoded", "none"]


@dataclass(frozen=True)
class BarcodeResult:
    """Outcome of a decode attempt.

    ``status="decoded"``         → ``payload`` and ``symbology`` are populated.
    ``status="detected_undecoded"`` → a code was located but its data couldn't be
                                     read; ``payload`` is empty, ``symbology`` is
                                     the best guess (usually "QRCODE"). Useful
                                     for nudging users to retake the photo.
    ``status="none"``            → nothing detected at all.
    """

    payload: str
    symbology: str
    rotation: int = 0
    status: DecodeStatus = "decoded"

    @property
    def is_decoded(self) -> bool:
        return self.status == "decoded" and bool(self.payload)


# --- WeChat model bootstrap -------------------------------------------------
#
# The WeChat detector ships as four small files (~2 MB) outside the
# opencv-contrib wheel. We lazily download them on first use into a cache
# directory; CI / Docker builds can pre-warm by calling decode() once at
# build time, or override the location via $TRUSTLENS_WECHAT_MODEL_DIR.

_WECHAT_MODEL_FILES = {
    "detect.prototxt": "https://raw.githubusercontent.com/WeChatCV/opencv_3rdparty/wechat_qrcode/detect.prototxt",
    "detect.caffemodel": "https://raw.githubusercontent.com/WeChatCV/opencv_3rdparty/wechat_qrcode/detect.caffemodel",
    "sr.prototxt": "https://raw.githubusercontent.com/WeChatCV/opencv_3rdparty/wechat_qrcode/sr.prototxt",
    "sr.caffemodel": "https://raw.githubusercontent.com/WeChatCV/opencv_3rdparty/wechat_qrcode/sr.caffemodel",
}

_wechat_lock = threading.Lock()
_wechat_detector = None  # type: ignore[var-annotated]
_wechat_unavailable_reason: str | None = None


def _wechat_model_dir() -> Path:
    override = os.environ.get("TRUSTLENS_WECHAT_MODEL_DIR")
    if override:
        return Path(override)
    return Path.home() / ".cache" / "trustlens" / "wechat_qr"


def _ensure_wechat_models(target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for name, url in _WECHAT_MODEL_FILES.items():
        path = target / name
        if path.exists() and path.stat().st_size > 0:
            continue
        logger.info("Downloading WeChat QR model %s ...", name)
        urllib.request.urlretrieve(url, path)


def _get_wechat_detector():
    """Return a cached WeChat detector, or ``None`` if unavailable.

    Failures (missing opencv-contrib build, network error fetching models)
    are recorded once and we silently fall back to pyzbar afterwards — a
    half-working barcode pipeline is better than a route that 500s.
    """
    global _wechat_detector, _wechat_unavailable_reason
    if _wechat_detector is not None:
        return _wechat_detector
    if _wechat_unavailable_reason is not None:
        return None

    with _wechat_lock:
        if _wechat_detector is not None:
            return _wechat_detector
        if _wechat_unavailable_reason is not None:
            return None
        try:
            import cv2  # noqa: F401  (validate import upfront for a cleaner error)

            model_dir = _wechat_model_dir()
            _ensure_wechat_models(model_dir)
            _wechat_detector = cv2.wechat_qrcode_WeChatQRCode(
                str(model_dir / "detect.prototxt"),
                str(model_dir / "detect.caffemodel"),
                str(model_dir / "sr.prototxt"),
                str(model_dir / "sr.caffemodel"),
            )
            return _wechat_detector
        except Exception as exc:
            _wechat_unavailable_reason = str(exc)
            logger.warning(
                "WeChat QR detector unavailable (%s); falling back to pyzbar only.", exc
            )
            return None


# --- Decoders ---------------------------------------------------------------

# Phone photos are rarely level; a quick 4-way rotation sweep on the pyzbar
# fallback recovers most almost-aligned shots without paying for a full
# perspective-correction pass. WeChat's detector handles rotation internally
# so we don't sweep on that path.
_ROTATIONS = (0, 90, 180, 270)


def _try_opencv_qr(image: Image.Image) -> BarcodeResult | None:
    """Decode (or at least *detect*) a QR using OpenCV.

    Two passes, both cheap on a single 4K image:
    - **WeChat detector** (neural net + super-resolution) for the best
      decode rate on warped / low-contrast QRs.
    - **Classic ``cv2.QRCodeDetector``** as a detection-only fallback —
      its decoder is weaker, but its detector frequently *locates* QRs
      that WeChat misses entirely (especially on embossed pharma foil).
      A bare detection is still useful: we surface it as
      ``detected_undecoded`` so the API can prompt the user.
    """
    try:
        import cv2  # noqa: F401
        import numpy as np
    except ImportError:
        return None

    arr = np.asarray(image.convert("L"))

    detector = _get_wechat_detector()
    if detector is not None:
        try:
            results, points = detector.detectAndDecode(arr)
        except Exception:
            logger.exception("WeChat QR detector raised; trying classic OpenCV.")
            results, points = (), ()

        decoded = [r for r in (results or ()) if r]
        if decoded:
            return BarcodeResult(
                payload=decoded[0],
                symbology="QRCODE",
                rotation=0,
                status="decoded",
            )
        if points is not None and len(points) > 0:
            # WeChat both located *and* failed to decode — record that.
            return BarcodeResult(
                payload="",
                symbology="QRCODE",
                rotation=0,
                status="detected_undecoded",
            )

    # Classic detector: cheap, ships with every opencv build, and is good
    # at locating QRs on pharma foil even when its decoder gives up.
    try:
        classic = cv2.QRCodeDetector()
        ok, datas, points, _ = classic.detectAndDecodeMulti(arr)
    except Exception:
        return None

    if ok:
        decoded = [d for d in (datas or ()) if d]
        if decoded:
            return BarcodeResult(
                payload=decoded[0],
                symbology="QRCODE",
                rotation=0,
                status="decoded",
            )
        if points is not None and len(points) > 0:
            return BarcodeResult(
                payload="",
                symbology="QRCODE",
                rotation=0,
                status="detected_undecoded",
            )

    return None


def _try_pyzbar(image: Image.Image) -> BarcodeResult | None:
    """Fallback: pyzbar with a 4-rotation sweep + autocontrast."""
    try:
        from pyzbar import pyzbar
    except ImportError:
        # If neither WeChat nor pyzbar are available the route will surface
        # 'no barcode' rather than crashing. Logged so it's diagnosable.
        logger.warning("pyzbar not installed; barcode fallback disabled.")
        return None

    base = ImageOps.autocontrast(image.convert("L"))
    for angle in _ROTATIONS:
        rotated = base if angle == 0 else base.rotate(angle, expand=True)
        symbols = pyzbar.decode(rotated)
        if not symbols:
            continue
        symbol = symbols[0]
        try:
            payload = symbol.data.decode("utf-8")
        except UnicodeDecodeError:
            payload = symbol.data.decode("utf-8", errors="replace")
        return BarcodeResult(
            payload=payload,
            symbology=symbol.type,
            rotation=angle,
            status="decoded",
        )
    return None


def decode(image_bytes: bytes) -> BarcodeResult | None:
    """Decode the first barcode found, or return ``None`` if nothing detected.

    Order:
      1. WeChat QR detector (best-in-class for QR; handles warp + low contrast).
      2. ``pyzbar`` fallback (covers EAN-13, Code128, ITF, …).

    Returns ``BarcodeResult`` with ``status="detected_undecoded"`` when a QR
    is located but cannot be read — callers can use that to ask the user for
    a better photo instead of giving up silently.
    """
    image = Image.open(io.BytesIO(image_bytes))

    opencv_result = _try_opencv_qr(image)
    if opencv_result is not None and opencv_result.is_decoded:
        return opencv_result

    if (zbar := _try_pyzbar(image)) is not None:
        return zbar

    # No decode from either backend — return the OpenCV 'detected' signal if
    # we have one so the user gets actionable feedback ("there's a QR but
    # it's damaged"). Otherwise nothing was found at all.
    return opencv_result
