/// Data models matching the backend VerdictResponse schema.
/// See backend/app/schemas/verdict.py for the canonical definition.

class BarcodeInfo {
  final String payload;
  final String symbology;
  final int rotation;
  final String status;

  const BarcodeInfo({
    required this.payload,
    required this.symbology,
    this.rotation = 0,
    this.status = 'decoded',
  });

  factory BarcodeInfo.fromJson(Map<String, dynamic> json) => BarcodeInfo(
        payload: json['payload'] as String,
        symbology: json['symbology'] as String,
        rotation: json['rotation'] as int? ?? 0,
        status: json['status'] as String? ?? 'decoded',
      );

  Map<String, dynamic> toJson() => {
        'payload': payload,
        'symbology': symbology,
        'rotation': rotation,
        'status': status,
      };
}

class OcrInfo {
  final String engine;
  final double confidence;
  final String text;

  const OcrInfo({
    required this.engine,
    required this.confidence,
    required this.text,
  });

  factory OcrInfo.fromJson(Map<String, dynamic> json) => OcrInfo(
        engine: json['engine'] as String,
        confidence: (json['confidence'] as num).toDouble(),
        text: json['text'] as String,
      );

  Map<String, dynamic> toJson() => {
        'engine': engine,
        'confidence': confidence,
        'text': text,
      };
}

class PageInfo {
  final String url;
  final String? title;
  final String? text;
  final bool captchaDetected;

  const PageInfo({
    required this.url,
    this.title,
    this.text,
    this.captchaDetected = false,
  });

  factory PageInfo.fromJson(Map<String, dynamic> json) => PageInfo(
        url: json['url'] as String,
        title: json['title'] as String?,
        text: json['text'] as String?,
        captchaDetected: json['captcha_detected'] as bool? ?? false,
      );
}

class Note {
  final String code;
  final String message;
  final String severity;

  const Note({
    required this.code,
    required this.message,
    required this.severity,
  });

  factory Note.fromJson(Map<String, dynamic> json) => Note(
        code: json['code'] as String,
        message: json['message'] as String,
        severity: json['severity'] as String,
      );
}

class Finding {
  final String code;
  final String severity;
  final String message;
  final String? evidence;

  const Finding({
    required this.code,
    required this.severity,
    required this.message,
    this.evidence,
  });

  factory Finding.fromJson(Map<String, dynamic> json) => Finding(
        code: json['code'] as String,
        severity: json['severity'] as String,
        message: json['message'] as String,
        evidence: json['evidence'] as String?,
      );
}

class FssaiCheck {
  final String? licenseNumber;
  final bool formatValid;
  final String onlineStatus;
  final String? businessName;
  final String? expiry;
  final String verifyUrl;

  const FssaiCheck({
    this.licenseNumber,
    this.formatValid = false,
    this.onlineStatus = 'skipped',
    this.businessName,
    this.expiry,
    this.verifyUrl = '',
  });

  factory FssaiCheck.fromJson(Map<String, dynamic> json) => FssaiCheck(
        licenseNumber: json['license_number'] as String?,
        formatValid: json['format_valid'] as bool? ?? false,
        onlineStatus: json['online_status'] as String? ?? 'skipped',
        businessName: json['business_name'] as String?,
        expiry: json['expiry'] as String?,
        verifyUrl: json['verify_url'] as String? ?? '',
      );
}

class GroceryAnalysis {
  final String riskBand;
  final List<Finding> findings;
  final Map<String, String> dates;
  final int? ingredientsCount;
  final FssaiCheck? fssai;

  const GroceryAnalysis({
    required this.riskBand,
    this.findings = const [],
    this.dates = const {},
    this.ingredientsCount,
    this.fssai,
  });

  factory GroceryAnalysis.fromJson(Map<String, dynamic> json) => GroceryAnalysis(
        riskBand: json['risk_band'] as String,
        findings: (json['findings'] as List<dynamic>?)
                ?.map((f) => Finding.fromJson(f as Map<String, dynamic>))
                .toList() ??
            [],
        dates: (json['dates'] as Map<String, dynamic>?)
                ?.map((k, v) => MapEntry(k, v.toString())) ??
            {},
        ingredientsCount: json['ingredients_count'] as int?,
        fssai: json['fssai'] != null
            ? FssaiCheck.fromJson(json['fssai'] as Map<String, dynamic>)
            : null,
      );
}

/// Main verdict response matching backend VerdictResponse schema.
class ScanResult {
  final String id;
  final String status;
  final String message;
  final List<Note> notes;
  final String verdict; // high_risk | caution | safe | unverifiable
  final int score;
  final String summary;
  final List<String> evidence;
  final BarcodeInfo? barcode;
  final OcrInfo? ocr;
  final PageInfo? page;
  final Map<String, String> labelFields;
  final Map<String, String> pageFields;
  final String category; // pharma | grocery | unknown
  final GroceryAnalysis? grocery;
  final DateTime scannedAt;
  final String? imageBase64;

  const ScanResult({
    required this.id,
    required this.status,
    required this.message,
    this.notes = const [],
    required this.verdict,
    required this.score,
    required this.summary,
    this.evidence = const [],
    this.barcode,
    this.ocr,
    this.page,
    this.labelFields = const {},
    this.pageFields = const {},
    this.category = 'pharma',
    this.grocery,
    required this.scannedAt,
    this.imageBase64,
  });

  factory ScanResult.fromJson(Map<String, dynamic> json) => ScanResult(
        id: json['id'] as String? ?? '',
        status: json['status'] as String,
        message: json['message'] as String,
        notes: (json['notes'] as List<dynamic>?)
                ?.map((n) => Note.fromJson(n as Map<String, dynamic>))
                .toList() ??
            [],
        verdict: json['verdict'] as String,
        score: json['score'] as int,
        summary: json['summary'] as String,
        evidence: (json['evidence'] as List<dynamic>?)
                ?.map((e) => e.toString())
                .toList() ??
            [],
        barcode: json['barcode'] != null
            ? BarcodeInfo.fromJson(json['barcode'] as Map<String, dynamic>)
            : null,
        ocr: json['ocr'] != null
            ? OcrInfo.fromJson(json['ocr'] as Map<String, dynamic>)
            : null,
        page: json['page'] != null
            ? PageInfo.fromJson(json['page'] as Map<String, dynamic>)
            : null,
        labelFields: (json['label_fields'] as Map<String, dynamic>?)
                ?.map((k, v) => MapEntry(k, v.toString())) ??
            {},
        pageFields: (json['page_fields'] as Map<String, dynamic>?)
                ?.map((k, v) => MapEntry(k, v.toString())) ??
            {},
        category: json['category'] as String? ?? 'pharma',
        grocery: json['grocery'] != null
            ? GroceryAnalysis.fromJson(json['grocery'] as Map<String, dynamic>)
            : null,
        scannedAt: DateTime.now(),
        imageBase64: json['image_base64'] as String?,
      );

  /// Convenience getters for display
  String get productName =>
      labelFields['drug_name'] ??
      labelFields['brand_name'] ??
      pageFields['brand_name'] ??
      'Unknown Product';

  String get manufacturer =>
      labelFields['manufacturer'] ??
      pageFields['manufacturer'] ??
      'Unknown Manufacturer';

  String get batchNumber =>
      labelFields['batch'] ?? pageFields['batch'] ?? 'N/A';

  String get expiryDate =>
      labelFields['exp_date'] ?? pageFields['exp_date'] ?? 'N/A';

  bool get isMedicine => category == 'pharma' || category == 'unknown';
  bool get isFood => category == 'grocery';
}
