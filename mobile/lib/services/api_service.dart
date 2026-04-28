import 'dart:typed_data';

import 'package:dio/dio.dart';

import '../models/chat_message.dart';
import '../models/recommendation.dart';
import '../models/scan_result.dart';

/// API service using Dio. Structured to match the existing backend
/// endpoints (/images, /codes) so swapping from mock to real is a
/// single baseUrl change.
class ApiService {
  late final Dio _dio;

  ApiService({String? baseUrl, String? authToken}) {
    _dio = Dio(BaseOptions(
      baseUrl: baseUrl ?? 'http://localhost:8000',
      connectTimeout: const Duration(seconds: 15),
      receiveTimeout: const Duration(seconds: 30),
      headers: {
        'Content-Type': 'application/json',
        if (authToken != null) 'Authorization': 'Bearer $authToken',
      },
    ));

    _dio.interceptors.add(LogInterceptor(
      requestBody: false,
      responseBody: true,
    ));
  }

  /// Update auth token after login.
  void setAuthToken(String token) {
    _dio.options.headers['Authorization'] = 'Bearer $token';
  }

  /// Scan image via POST /images (multipart upload).
  /// Maps to existing backend route routes_images.py.
  Future<ScanResult> scanImage(Uint8List imageBytes, {String filename = 'scan.jpg'}) async {
    final formData = FormData.fromMap({
      'file': MultipartFile.fromBytes(imageBytes, filename: filename),
    });

    final response = await _dio.post('/images', data: formData);
    final result = ScanResult.fromJson(response.data as Map<String, dynamic>);
    return result;
  }

  /// Scan via barcode/QR code text POST /codes.
  /// Maps to existing backend route routes_codes.py.
  Future<ScanResult> scanCode(String code, {String? symbology}) async {
    final response = await _dio.post('/codes', data: {
      'code': code,
      if (symbology != null) 'symbology': symbology,
    });
    return ScanResult.fromJson(response.data as Map<String, dynamic>);
  }

  /// AI chat POST /api/ai/chat.
  /// New route — will be added to backend.
  Future<ChatResponse> sendChatMessage({
    required List<ChatMessage> messages,
    Map<String, dynamic>? scanContext,
    String? userId,
  }) async {
    final response = await _dio.post('/api/ai/chat', data: {
      'messages': messages.map((m) => m.toJson()).toList(),
      'scan_context': scanContext,
      'user_id': userId,
    });
    return ChatResponse.fromJson(response.data as Map<String, dynamic>);
  }

  /// Get recommendations GET /api/recommendations.
  /// New route — will be added to backend.
  Future<List<Recommendation>> getRecommendations({String? userId}) async {
    final response = await _dio.get('/api/recommendations', queryParameters: {
      if (userId != null) 'user_id': userId,
    });
    final data = response.data as Map<String, dynamic>;
    final list = data['recommendations'] as List<dynamic>;
    return list
        .map((r) => Recommendation.fromJson(r as Map<String, dynamic>))
        .toList();
  }
}
