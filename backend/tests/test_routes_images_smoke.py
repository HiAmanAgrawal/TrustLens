"""Smoke test for POST /images.

We swap the heavy collaborators (OCR, scraper) for fast fakes via
FastAPI's dependency override so the test runs without Tesseract,
Playwright, or the Gemini API. The barcode decoder runs for real against a
generated QR — this is the cheapest end-to-end signal that the routing,
schema, and pipeline are wired up correctly.
"""

from __future__ import annotations

import io

import pytest

pytest.importorskip("qrcode")
pytest.importorskip("pyzbar")


def _make_qr_png(payload: str) -> bytes:
    import qrcode

    img = qrcode.make(payload)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_post_images_returns_verdict_shape(monkeypatch) -> None:
    from fastapi.testclient import TestClient

    # Stub the slow + external collaborators BEFORE building the app, so the
    # pipeline imports the patched versions.
    from app.services import pipeline as pipeline_mod
    from services.matcher.engine import Verdict
    from services.ocr.extractor import OcrResult
    from services.scraper.agent import ScrapeResult

    async def fake_ocr(_image_bytes: bytes) -> OcrResult:
        return OcrResult(
            text="Cetirizine 10mg Batch: ABC123 Mfg: 01/2024 Exp: 12/2026",
            engine="tesseract",
            confidence=0.95,
            status="ok",
        )

    async def fake_scrape(url: str, *, timeout_s: float = 30.0) -> ScrapeResult:
        return ScrapeResult(
            url=url,
            fields={
                "title": "Acme Pharma — Verify",
                "visible_text": "Cetirizine Tablets 10mg Batch: ABC123 Mfg: 01/2024 Exp: 12/2026",
            },
            raw_html="<html></html>",
            captcha_solved=False,
            status="ok",
        )

    monkeypatch.setattr(pipeline_mod.ocr_extractor, "extract_text", fake_ocr)
    monkeypatch.setattr(pipeline_mod.scraper_agent, "scrape_url", fake_scrape)

    from app.main import create_app

    client = TestClient(create_app())
    qr = _make_qr_png("https://acme.example/verify?batch=ABC123")

    response = client.post("/images", files={"file": ("pack.png", qr, "image/png")})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["verdict"] in {"safe", "caution", "high_risk", "unverifiable"}
    assert body["barcode"]["payload"] == "https://acme.example/verify?batch=ABC123"
    assert body["ocr"]["engine"] == "tesseract"
    assert body["page"]["url"].startswith("https://acme.example/")
    # Same data on both sides -> the matcher should be confident.
    assert body["verdict"] == "safe"
    assert body["score"] >= 8
    assert body["barcode"]["status"] == "decoded"
    # Top-level status surface — happy path collapses to MATCH_OK.
    assert body["status"] == "match_ok"
    assert body["message"]
    # Notes should describe each successful stage.
    note_codes = [n["code"] for n in body["notes"]]
    assert "ocr_ok" in note_codes
    assert "scrape_ok" in note_codes
    assert "match_ok" in note_codes
    assert isinstance(Verdict, type)  # touch the import so it isn't pruned


def test_post_images_surfaces_qr_detected_but_unreadable(monkeypatch) -> None:
    """When the decoder locates a QR but can't read it, the response should
    carry ``status='detected_undecoded'`` and include the user-facing hint."""
    from fastapi.testclient import TestClient

    from app.services import pipeline as pipeline_mod
    from services.barcode.decoder import BarcodeResult
    from services.ocr.extractor import OcrResult

    def fake_decode(_image_bytes: bytes) -> BarcodeResult:
        return BarcodeResult(
            payload="",
            symbology="QRCODE",
            rotation=0,
            status="detected_undecoded",
        )

    async def fake_ocr(_image_bytes: bytes) -> OcrResult:
        return OcrResult(text="Some label text", engine="tesseract", confidence=0.8, status="ok")

    monkeypatch.setattr(pipeline_mod.barcode_decoder, "decode", fake_decode)
    monkeypatch.setattr(pipeline_mod.ocr_extractor, "extract_text", fake_ocr)

    from app.main import create_app

    client = TestClient(create_app())
    response = client.post(
        "/images", files={"file": ("pack.png", b"\x89PNG\r\n\x1a\n", "image/png")}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["barcode"]["status"] == "detected_undecoded"
    assert body["barcode"]["payload"] == ""
    # No URL was decoded -> no scrape -> verdict has to be 'unverifiable'.
    assert body["verdict"] == "unverifiable"
    assert body["page"] is None
    # Top-level status: the QR-detected-but-unreadable note is the most actionable.
    assert body["status"] == "qr_detected_unreadable"
    assert "retake" in body["message"].lower()
    note_codes = [n["code"] for n in body["notes"]]
    assert "qr_detected_unreadable" in note_codes
    assert "match_unverifiable" in note_codes


def test_post_images_no_qr_detected(monkeypatch) -> None:
    """When no barcode is found at all, surface ``qr_not_found`` distinctly."""
    from fastapi.testclient import TestClient

    from app.services import pipeline as pipeline_mod
    from services.ocr.extractor import OcrResult

    def fake_decode(_image_bytes: bytes):
        return None

    async def fake_ocr(_image_bytes: bytes) -> OcrResult:
        return OcrResult(text="Some label text", engine="tesseract", confidence=0.8, status="ok")

    monkeypatch.setattr(pipeline_mod.barcode_decoder, "decode", fake_decode)
    monkeypatch.setattr(pipeline_mod.ocr_extractor, "extract_text", fake_ocr)

    from app.main import create_app

    client = TestClient(create_app())
    response = client.post(
        "/images", files={"file": ("pack.png", b"\x89PNG\r\n\x1a\n", "image/png")}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["barcode"] is None
    assert body["status"] == "qr_not_found"
    note_codes = [n["code"] for n in body["notes"]]
    assert "qr_not_found" in note_codes


def test_post_images_ocr_fallback_auth_failed(monkeypatch) -> None:
    """Bad GOOGLE_API_KEY should produce a specific ``ocr_fallback_auth_failed`` note."""
    from fastapi.testclient import TestClient

    from app.services import pipeline as pipeline_mod
    from services.barcode.decoder import BarcodeResult
    from services.ocr.extractor import OcrResult

    def fake_decode(_image_bytes: bytes):
        return BarcodeResult(
            payload="https://example.com/x", symbology="QRCODE", rotation=0, status="decoded"
        )

    async def fake_ocr(_image_bytes: bytes) -> OcrResult:
        return OcrResult(text="x", engine="tesseract", confidence=0.1, status="fallback_auth_failed")

    async def fake_scrape(url: str, *, timeout_s: float = 30.0):
        from services.scraper.agent import ScrapeResult

        return ScrapeResult(
            url=url,
            fields={"title": "x", "visible_text": "x"},
            raw_html="<html></html>",
            status="ok",
        )

    monkeypatch.setattr(pipeline_mod.barcode_decoder, "decode", fake_decode)
    monkeypatch.setattr(pipeline_mod.ocr_extractor, "extract_text", fake_ocr)
    monkeypatch.setattr(pipeline_mod.scraper_agent, "scrape_url", fake_scrape)

    from app.main import create_app

    client = TestClient(create_app())
    response = client.post(
        "/images", files={"file": ("pack.png", b"\x89PNG\r\n\x1a\n", "image/png")}
    )

    assert response.status_code == 200
    body = response.json()
    note_codes = [n["code"] for n in body["notes"]]
    assert "ocr_fallback_auth_failed" in note_codes
    # An auth-failure 'error' note should win the top-level slot over the
    # matcher's 'warning' notes.
    assert body["status"] == "ocr_fallback_auth_failed"
    assert "api key" in body["message"].lower()


def test_post_images_scraper_timeout(monkeypatch) -> None:
    """A scrape timeout should be surfaced as ``scrape_timeout``."""
    from fastapi.testclient import TestClient

    from app.services import pipeline as pipeline_mod
    from services.barcode.decoder import BarcodeResult
    from services.ocr.extractor import OcrResult
    from services.scraper.agent import ScrapeResult

    def fake_decode(_image_bytes: bytes):
        return BarcodeResult(
            payload="https://example.com/x", symbology="QRCODE", rotation=0, status="decoded"
        )

    async def fake_ocr(_image_bytes: bytes) -> OcrResult:
        return OcrResult(text="something", engine="tesseract", confidence=0.9, status="ok")

    async def fake_scrape(url: str, *, timeout_s: float = 30.0) -> ScrapeResult:
        return ScrapeResult(url=url, status="timeout", error_detail="Timeout 1234ms exceeded.")

    monkeypatch.setattr(pipeline_mod.barcode_decoder, "decode", fake_decode)
    monkeypatch.setattr(pipeline_mod.ocr_extractor, "extract_text", fake_ocr)
    monkeypatch.setattr(pipeline_mod.scraper_agent, "scrape_url", fake_scrape)

    from app.main import create_app

    client = TestClient(create_app())
    response = client.post(
        "/images", files={"file": ("pack.png", b"\x89PNG\r\n\x1a\n", "image/png")}
    )

    assert response.status_code == 200
    body = response.json()
    note_codes = [n["code"] for n in body["notes"]]
    assert "scrape_timeout" in note_codes
    assert body["page"] is None
    assert body["verdict"] == "unverifiable"


# --- Error-envelope tests ----------------------------------------------------


def test_post_images_rejects_oversize_upload(monkeypatch) -> None:
    """A >10 MB upload returns 413 with the structured ``payload_too_large`` envelope."""
    from fastapi.testclient import TestClient

    from app.api import routes_images as routes_mod

    # Squeeze the cap to keep the test fast.
    monkeypatch.setattr(routes_mod, "_MAX_BYTES", 1024)

    from app.main import create_app

    client = TestClient(create_app())
    big = b"\x00" * 4096
    response = client.post("/images", files={"file": ("big.png", big, "image/png")})

    assert response.status_code == 413
    body = response.json()
    assert body["status"] == "payload_too_large"
    assert "limit" in body["message"].lower()


def test_post_images_rejects_unsupported_mime_type() -> None:
    """An obviously non-image upload returns 415 with ``unsupported_media_type``."""
    from fastapi.testclient import TestClient

    from app.main import create_app

    client = TestClient(create_app())
    response = client.post(
        "/images", files={"file": ("doc.pdf", b"%PDF-1.4\n%fake", "application/pdf")}
    )

    assert response.status_code == 415
    body = response.json()
    assert body["status"] == "unsupported_media_type"


def test_post_codes_validates_payload() -> None:
    """A too-short ``code`` triggers our 422 envelope, not raw FastAPI errors."""
    from fastapi.testclient import TestClient

    from app.main import create_app

    client = TestClient(create_app())
    response = client.post("/codes", json={"code": "ab"})

    assert response.status_code == 422
    body = response.json()
    assert body["status"] == "invalid_request"
    # Detail should at least name the failing field.
    assert body["detail"] is not None
    assert "code" in body["detail"]


def test_post_codes_info_only_when_scrape_succeeds_without_ocr(monkeypatch) -> None:
    """``/codes`` with a URL that scrapes cleanly should return ``info_only``,
    not ``match_unverifiable`` — there's nothing to compare *to*, but the
    scraped data is the answer the user wanted."""
    from fastapi.testclient import TestClient

    from app.services import pipeline as pipeline_mod
    from services.scraper.agent import ScrapeResult

    portal_text = (
        "DOLO-650\n"
        "Brand Name:\nDOLO-650\n"
        "Batch number:\nDOBS3975\n"
        "Date of manufacturing:\nMAR.2025\n"
        "Date of expiry:\nFEB.2029\n"
        "Name and Address of the manufacturer:\nMICROLABS LIMITED\n"
    )

    async def fake_scrape(url: str, *, timeout_s: float = 30.0) -> ScrapeResult:
        return ScrapeResult(
            url=url,
            fields={"title": "ACG", "visible_text": portal_text},
            raw_html="<html></html>",
            captcha_solved=False,
            status="ok",
        )

    monkeypatch.setattr(pipeline_mod.scraper_agent, "scrape_url", fake_scrape)

    from app.main import create_app

    client = TestClient(create_app())
    response = client.post(
        "/codes",
        json={"code": "https://mlprd.mllqrv1.in/U/abc"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "info_only"
    note_codes = [n["code"] for n in body["notes"]]
    assert "info_only" in note_codes
    # Page-side fields should be populated from the real-world text.
    assert body["page_fields"]["batch"] == "DOBS3975"
    assert body["page_fields"]["brand_name"] == "DOLO-650"
    assert "MICROLABS" in body["page_fields"]["manufacturer"].upper()


def test_unknown_route_returns_envelope() -> None:
    """404s flow through the same envelope as everything else."""
    from fastapi.testclient import TestClient

    from app.main import create_app

    client = TestClient(create_app())
    response = client.get("/this-does-not-exist")

    assert response.status_code == 404
    body = response.json()
    assert body["status"] == "not_found"


def test_post_images_routes_to_grocery_branch(monkeypatch) -> None:
    """When OCR'd text reads as a grocery label, the response should:

    - have ``category="grocery"``,
    - have a populated ``grocery`` block with findings + a risk_band,
    - skip the manufacturer scrape entirely (``page is None``),
    - mirror the grocery findings into the notes timeline.
    """
    from fastapi.testclient import TestClient

    from app.services import pipeline as pipeline_mod
    from services.barcode.decoder import BarcodeResult
    from services.ocr.extractor import OcrResult

    grocery_text = """
    Crispy Cookies
    NUTRITION INFORMATION (per 100 g)
    Energy 480 kcal
    Saturated Fat 8 g
    Trans Fat 0.4 g
    Sugars 30 g
    Sodium 720 mg
    Ingredients: Refined wheat flour, sugar, glucose syrup, dextrose,
    maltodextrin, edible vegetable oil, salt.
    Contains: Wheat, Milk.
    Best Before 12 months from MFG.
    MFG: 03/2026
    Net Weight: 200 g
    FSSAI Lic No: 12345678901234
    """

    def fake_decode(_image_bytes: bytes) -> BarcodeResult:
        return BarcodeResult(
            payload="08901302207789",
            symbology="EAN13",
            rotation=0,
            status="decoded",
        )

    async def fake_ocr(_image_bytes: bytes) -> OcrResult:
        return OcrResult(
            text=grocery_text,
            engine="tesseract",
            confidence=0.9,
            status="ok",
        )

    # Force the FSSAI online lookup off — we don't want the grocery smoke
    # test to depend on Playwright or the network.
    from services.grocery import analyzer as grocery_analyzer

    real_analyze = grocery_analyzer.analyze

    async def offline_analyze(text: str, **_kwargs):
        return await real_analyze(text, online_fssai=False)

    monkeypatch.setattr(pipeline_mod.barcode_decoder, "decode", fake_decode)
    monkeypatch.setattr(pipeline_mod.ocr_extractor, "extract_text", fake_ocr)
    monkeypatch.setattr(pipeline_mod.grocery_analyzer, "analyze", offline_analyze)

    from app.main import create_app

    client = TestClient(create_app())
    response = client.post(
        "/images", files={"file": ("pack.png", b"\x89PNG\r\n\x1a\n", "image/png")}
    )

    assert response.status_code == 200, response.text
    body = response.json()

    assert body["category"] == "grocery"
    assert body["grocery"] is not None
    grocery = body["grocery"]
    assert grocery["risk_band"] in {"low", "medium", "high"}
    assert grocery["fssai"] is not None
    assert grocery["fssai"]["license_number"] == "12345678901234"
    assert grocery["fssai"]["format_valid"] is True
    assert grocery["fssai"]["online_status"] == "skipped"

    finding_codes = {f["code"] for f in grocery["findings"]}
    assert "high_sodium" in finding_codes
    assert "high_sugar" in finding_codes
    assert "trans_fat_present" in finding_codes
    assert "hidden_sugars_found" in finding_codes
    assert "allergen_declaration_found" in finding_codes

    # Page-side scrape should have been skipped.
    assert body["page"] is None

    note_codes = [n["code"] for n in body["notes"]]
    assert "category_grocery" in note_codes
    # Findings should be mirrored into the notes timeline.
    assert "high_sodium" in note_codes
