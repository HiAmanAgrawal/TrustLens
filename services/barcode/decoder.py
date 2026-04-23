"""Barcode / QR / DataMatrix decoder.

Strategy, in order of robustness:

1. **OpenCV's WeChat QR detector**, whole image — neural-net finder +
   super-resolution. Handles warped foil packs, glare, blur, and rotation
   that defeat ``pyzbar``. Succeeds on most cases in a single pass.
2. **WeChat over overlapping tiles** — when the whole-image pass returns
   nothing. Phone photos of pharma packs often pair a small QR with a
   busy background (checkered fabric, foil glare, repeating brand prints)
   that distracts the neural finder; feeding it smaller crops focuses it
   on plausible QR regions and recovers the payload in ~1 s.
3. **Classic ``cv2.QRCodeDetector``** — weaker decoder but a strong
   *locator*. We use it on the whole image to surface a
   ``detected_undecoded`` signal when a QR is physically present but
   genuinely unreadable (damaged modules, partial clip).
4. **pyzbar (libzbar)** — broad symbology coverage (EAN-13, Code128,
   ITF, …). Used as a fallback for non-QR codes.

Both OpenCV passes can report **detected-but-undecoded** outcomes: when a
QR is located but its payload can't be read, we surface that distinct
signal so the API can tell the user "there's a QR there, but please
retake the photo" instead of the much less useful "no barcode found".

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

# Tile sizes (pixels) and overlap fraction for the tiled WeChat sweep. Two
# passes are enough in practice: 1024 catches mid-sized QRs that get lost in
# 4K backgrounds, 768 catches the small printed QRs typical on pharma foil.
# 50% overlap means a QR straddling a tile boundary is always fully inside
# at least one neighbouring tile. Going smaller than 768 starts to cut
# realistic QRs in half before super-resolution can recover them.
_TILE_PASSES: tuple[tuple[int, float], ...] = ((1024, 0.5), (768, 0.5))


def _iter_tiles(image: Image.Image, size: int, overlap: float):
    """Yield ``(left, top, PIL.Image)`` crops covering ``image`` with overlap.

    Crops are produced lazily via ``PIL.Image.crop`` (no pixel copy until the
    consumer touches them), so a sweep over a 4K image stays cheap.
    """
    width, height = image.size
    if width <= size and height <= size:
        yield 0, 0, image
        return

    stride = max(1, int(size * (1.0 - overlap)))
    # ``range`` stops before ``width - size``; add one extra step at the right
    # edge so a QR sitting against the right or bottom edge isn't missed.
    xs = list(range(0, max(1, width - size + 1), stride))
    if xs[-1] + size < width:
        xs.append(max(0, width - size))
    ys = list(range(0, max(1, height - size + 1), stride))
    if ys[-1] + size < height:
        ys.append(max(0, height - size))

    for y in ys:
        for x in xs:
            yield x, y, image.crop((x, y, x + size, y + size))


def _wechat_decode(detector, image: Image.Image) -> tuple[tuple[str, ...], object]:
    """Run the WeChat detector on ``image`` and return ``(results, points)``.

    Wrapped so callers don't have to reimport numpy and so an exception in
    the C++ side becomes "no result" rather than a 500.
    """
    import numpy as np

    arr = np.asarray(image.convert("L"))
    try:
        return detector.detectAndDecode(arr)
    except Exception:
        logger.exception("WeChat QR detector raised on a %s image; treating as miss.", image.size)
        return (), ()


def _wechat_tiled(detector, image: Image.Image) -> BarcodeResult | None:
    """Sweep ``image`` in overlapping tiles, return the first decode hit.

    Returns ``None`` when no tile decoded — we deliberately do *not* return
    a ``detected_undecoded`` from this path because tile boundaries can
    create spurious finder-pattern hits; the whole-image classic detector
    is the authoritative source for "QR present but unreadable".
    """
    for size, overlap in _TILE_PASSES:
        for _x, _y, tile in _iter_tiles(image, size, overlap):
            results, _points = _wechat_decode(detector, tile)
            decoded = next((r for r in (results or ()) if r), None)
            if decoded:
                return BarcodeResult(
                    payload=decoded,
                    symbology="QRCODE",
                    rotation=0,
                    status="decoded",
                )
    return None


def _try_opencv_qr(image: Image.Image) -> BarcodeResult | None:
    """Decode (or at least *detect*) a QR using OpenCV.

    Three passes, in increasing cost:

    1. **WeChat, whole image** — fast (≈10 ms on a 4K frame) and the
       common case for clean photos.
    2. **WeChat, tiled sweep** — only when (1) decoded nothing. Recovers
       small QRs that the neural finder loses among busy backgrounds.
    3. **Classic ``cv2.QRCodeDetector``, whole image** — cheap, ships
       with every opencv build, and is good at *locating* QRs on pharma
       foil even when its decoder gives up. We use it primarily for the
       ``detected_undecoded`` signal.
    """
    try:
        import cv2  # noqa: F401
        import numpy as np
    except ImportError:
        return None

    detector = _get_wechat_detector()
    wechat_detected = False  # whole-image WeChat saw a finder pattern
    if detector is not None:
        results, points = _wechat_decode(detector, image)
        decoded = next((r for r in (results or ()) if r), None)
        if decoded:
            return BarcodeResult(
                payload=decoded,
                symbology="QRCODE",
                rotation=0,
                status="decoded",
            )
        wechat_detected = points is not None and len(points) > 0

        # Tiled sweep — only worth the cost when the whole-image pass
        # didn't decode. Stops at the first hit.
        if (tiled := _wechat_tiled(detector, image)) is not None:
            return tiled

    # Classic detector: also runs on the whole image (it's far slower per
    # pixel than WeChat, so tiling it isn't worth it).
    arr = np.asarray(image.convert("L"))
    try:
        classic = cv2.QRCodeDetector()
        ok, datas, points, _ = classic.detectAndDecodeMulti(arr)
    except Exception:
        # If the classic detector blew up but WeChat had already located a
        # QR, surface that detection rather than swallowing the signal.
        return _detected_undecoded() if wechat_detected else None

    if ok:
        decoded = next((d for d in (datas or ()) if d), None)
        if decoded:
            return BarcodeResult(
                payload=decoded,
                symbology="QRCODE",
                rotation=0,
                status="decoded",
            )
        if points is not None and len(points) > 0:
            return _detected_undecoded()

    return _detected_undecoded() if wechat_detected else None


def _detected_undecoded() -> BarcodeResult:
    """Canonical 'we saw a QR but couldn't read it' result."""
    return BarcodeResult(
        payload="",
        symbology="QRCODE",
        rotation=0,
        status="detected_undecoded",
    )


def _try_pyzbar(image: Image.Image) -> BarcodeResult | None:
    """Fallback: pyzbar with a 4-rotation sweep + autocontrast."""
    try:
        from pyzbar import pyzbar
    except (ImportError, FileNotFoundError, OSError):
        # pyzbar may be installed but libzbar DLL missing (FileNotFoundError
        # on Windows). Gracefully degrade rather than crash.
        logger.warning("pyzbar not available (missing libzbar DLL); barcode fallback disabled.")
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
