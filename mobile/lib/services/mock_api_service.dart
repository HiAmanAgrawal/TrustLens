import 'dart:typed_data';

import '../models/chat_message.dart';
import '../models/recommendation.dart';
import '../models/scan_result.dart';

/// Mock API service with hardcoded responses for full UI testing
/// without a live backend. Data shapes match the real VerdictResponse
/// schema so switching to the real API requires minimal changes.
class MockApiService {
  /// Simulate network latency.
  Future<void> _delay() => Future.delayed(const Duration(milliseconds: 800));

  /// Mock image scan — returns a pharma verdict.
  Future<ScanResult> scanImage(Uint8List imageBytes, {String filename = 'scan.jpg'}) async {
    await _delay();
    return _mockMedicineResult();
  }

  /// Mock code scan.
  Future<ScanResult> scanCode(String code, {String? symbology}) async {
    await _delay();
    return _mockMedicineResult();
  }

  /// Mock AI chat response.
  Future<ChatResponse> sendChatMessage({
    required List<ChatMessage> messages,
    Map<String, dynamic>? scanContext,
    String? userId,
  }) async {
    await _delay();
    final lastMessage = messages.last.content.toLowerCase();

    if (lastMessage.contains('side effect')) {
      return const ChatResponse(
        reply: 'Common side effects of Paracetamol include:\n\n'
            '\u2022 Nausea (in ~5% of users)\n'
            '\u2022 Mild stomach discomfort\n'
            '\u2022 Rarely, skin rash\n\n'
            'Serious side effects are rare at recommended doses. Exceeding 4g/day '
            'can cause liver damage.\n\n'
            '\u26A0 This is not medical advice. Consult a healthcare provider.',
        suggestions: ['What about overdose?', 'Safe alternatives?', 'For children?'],
      );
    }

    if (lastMessage.contains('interaction')) {
      return const ChatResponse(
        reply: 'Known interactions:\n\n'
            '\u2022 Warfarin \u2014 increased bleeding risk\n'
            '\u2022 Alcohol \u2014 increased liver toxicity\n'
            '\u2022 Isoniazid \u2014 increased liver toxicity\n\n'
            '\u26A0 This is not medical advice. Consult a healthcare provider.',
        suggestions: ['Should I stop Warfarin?', 'How about Aspirin?', 'Safe combinations?'],
      );
    }

    return const ChatResponse(
      reply: 'Based on your scan and health profile, this product appears safe for '
          'general use. However, I recommend discussing any specific concerns with '
          'your healthcare provider, especially given your health conditions.\n\n'
          '\u26A0 This is not medical advice. Consult a qualified healthcare provider.',
      suggestions: ['Tell me more', 'What should I do?', 'Any alternatives?'],
    );
  }

  /// Mock recommendations.
  Future<List<Recommendation>> getRecommendations({String? userId}) async {
    await _delay();
    return const [
      Recommendation(
        title: 'Oats with Almonds',
        reason: 'Good for Diabetes',
        category: 'Diet',
        compatibilityScore: 0.92,
        description: 'High in fiber and healthy fats. Helps regulate blood sugar.',
      ),
      Recommendation(
        title: 'Spinach & Kale Salad',
        reason: 'Rich in iron',
        category: 'Diet',
        compatibilityScore: 0.88,
        description: 'Excellent source of vitamins A, C, K and minerals.',
      ),
      Recommendation(
        title: 'Vitamin D3 Supplement',
        reason: 'Supports bone health',
        category: 'Supplements',
        compatibilityScore: 0.75,
        description: 'Recommended for those with limited sun exposure.',
      ),
      Recommendation(
        title: 'Processed Cheese',
        reason: 'High sodium content',
        category: 'Avoid',
        compatibilityScore: 0.3,
        description: 'Excessive sodium may aggravate hypertension.',
      ),
      Recommendation(
        title: 'Low-fat Yogurt',
        reason: 'Good source of probiotics',
        category: 'Diet',
        compatibilityScore: 0.85,
        description: 'Supports gut health and calcium intake.',
      ),
    ];
  }

  ScanResult _mockMedicineResult() {
    return ScanResult(
      id: 'mock-scan-001',
      status: 'match_ok',
      message: 'Label matches the manufacturer\'s information.',
      notes: const [
        Note(code: 'ocr_ok', message: 'Text extracted successfully', severity: 'info'),
        Note(code: 'category_pharma', message: 'Classified as pharmaceutical', severity: 'info'),
        Note(code: 'scrape_ok', message: 'Manufacturer page loaded', severity: 'info'),
        Note(code: 'match_ok', message: 'Label matches source data', severity: 'info'),
      ],
      verdict: 'safe',
      score: 8,
      summary: 'Label matches the manufacturer\'s information.',
      evidence: [
        'batch: label=\'DOBS3975\' vs page=\'DOBS3975\' (100%)',
        'drug_name: label=\'DOLO-650\' vs page=\'DOLO-650\' (100%)',
        'manufacturer: label=\'MICRO LABS LIMITED\' vs page=\'Micro Labs Limited\' (90%)',
        'exp_date: label=\'MAR2027\' vs page=\'MAR2027\' (100%)',
      ],
      barcode: const BarcodeInfo(
        payload: 'https://verify.microlabs.in/DOBS3975',
        symbology: 'QRCODE',
      ),
      ocr: const OcrInfo(
        engine: 'gemini',
        confidence: 0.92,
        text: 'DOLO-650 Paracetamol Tablets IP 650mg Micro Labs Limited Batch DOBS3975 Exp MAR2027',
      ),
      labelFields: const {
        'batch': 'DOBS3975',
        'drug_name': 'DOLO-650',
        'manufacturer': 'MICRO LABS LIMITED',
        'exp_date': 'MAR2027',
        'mfg_date': 'MAR2025',
      },
      pageFields: const {
        'batch': 'DOBS3975',
        'brand_name': 'DOLO-650',
        'manufacturer': 'Micro Labs Limited',
        'exp_date': 'MAR2027',
      },
      category: 'pharma',
      scannedAt: DateTime.now(),
    );
  }

  /// Mock food scan result.
  ScanResult mockFoodResult() {
    return ScanResult(
      id: 'mock-scan-002',
      status: 'category_grocery',
      message: 'We found a few things on this grocery label worth a closer look.',
      notes: const [
        Note(code: 'ocr_ok', message: 'Text extracted successfully', severity: 'info'),
        Note(code: 'category_grocery', message: 'Classified as grocery', severity: 'info'),
      ],
      verdict: 'caution',
      score: 5,
      summary: 'We found a few things on this grocery label worth a closer look.',
      evidence: const [
        'High sodium: 1200mg per serving (warning)',
        'Contains artificial colors: Tartrazine E102 (warning)',
        'FSSAI license valid (info)',
      ],
      labelFields: const {
        'brand_name': 'MAGGI',
      },
      category: 'grocery',
      grocery: const GroceryAnalysis(
        riskBand: 'medium',
        findings: [
          Finding(
            code: 'high_sodium',
            severity: 'warning',
            message: 'Sodium content exceeds recommended daily intake per serving.',
            evidence: '1200mg per serving',
          ),
          Finding(
            code: 'artificial_color',
            severity: 'warning',
            message: 'Contains artificial color additives.',
            evidence: 'Tartrazine (E102)',
          ),
          Finding(
            code: 'fssai_valid',
            severity: 'info',
            message: 'FSSAI license is valid.',
            evidence: '10015011000123',
          ),
        ],
        ingredientsCount: 18,
        dates: {'best_before': 'DEC 2026', 'mfg': 'JUN 2025'},
      ),
      scannedAt: DateTime.now(),
    );
  }
}
