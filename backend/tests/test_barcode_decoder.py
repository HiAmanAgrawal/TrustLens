"""Round-trip a generated QR through the decoder.

The decoder tries OpenCV's WeChat detector first and falls back to
``pyzbar``. We need at least one of them available to exercise the
happy-path; if neither is installed we skip rather than fail.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest

pytest.importorskip("qrcode")

# At least one decoder backend has to be present.
_have_pyzbar = True
try:
    import pyzbar  # noqa: F401
except Exception:
    _have_pyzbar = False

_have_opencv = True
try:
    import cv2  # noqa: F401
except Exception:
    _have_opencv = False

if not (_have_pyzbar or _have_opencv):
    pytest.skip("no barcode backend available", allow_module_level=True)

_FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _png(payload: str) -> bytes:
    import qrcode

    img = qrcode.make(payload)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_decode_roundtrips_a_generated_qr() -> None:
    from services.barcode.decoder import decode

    payload = "https://example.com/verify?batch=ABC123"
    result = decode(_png(payload))

    assert result is not None
    assert result.is_decoded
    assert result.payload == payload
    assert result.symbology == "QRCODE"
    assert result.status == "decoded"


def test_decode_returns_none_for_blank_image() -> None:
    from PIL import Image

    from services.barcode.decoder import decode

    buf = io.BytesIO()
    Image.new("RGB", (200, 200), color="white").save(buf, format="PNG")

    # A truly blank image: neither decoder should report a finder pattern, so
    # the result must be a flat None.
    assert decode(buf.getvalue()) is None


def test_barcode_result_is_decoded_property() -> None:
    """Status flag drives downstream branching; lock the contract in."""
    from services.barcode.decoder import BarcodeResult

    assert BarcodeResult(payload="x", symbology="QRCODE").is_decoded is True
    assert (
        BarcodeResult(payload="", symbology="QRCODE", status="detected_undecoded").is_decoded
        is False
    )


def test_decode_real_dolo_blister_pack() -> None:
    """Regression: the Dolo-650 photo (cluttered 4K phone snap) used to
    return ``None`` because the QR is small relative to a busy embossed
    background. The tile-sweep WeChat fallback in ``_try_opencv_qr`` makes
    it decode reliably; this test prevents that regressing.

    Skipped when WeChat models can't be loaded (offline CI / no
    opencv-contrib build) — the classic OpenCV detector + pyzbar can't
    decode this particular frame on their own, so without WeChat the
    assertion below would be testing the wrong thing.
    """
    from services.barcode.decoder import _get_wechat_detector, decode

    fixture = _FIXTURES_DIR / "dolo_650_blister.jpg"
    if not fixture.exists():
        pytest.skip(f"missing fixture: {fixture}")
    if _get_wechat_detector() is None:
        pytest.skip("WeChat QR detector unavailable (no opencv-contrib or model files)")

    result = decode(fixture.read_bytes())

    assert result is not None
    assert result.is_decoded, f"expected a decoded QR, got status={result.status!r}"
    assert result.payload == "https://mlprd.mllqrv1.in/U/aaaabdib6i"
    assert result.symbology == "QRCODE"
