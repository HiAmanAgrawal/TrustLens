import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../services/api_service.dart';
import '../services/mock_api_service.dart';
import '../services/storage_service.dart';

/// Core service providers — single instances shared across the app.

/// Backend base URL — auto-selects a sensible default per platform.
/// - Web/Chrome: http://localhost:8000 (same machine)
/// - Android emulator: http://10.0.2.2:8000
/// Override at runtime from Profile → Backend Server (e.g. ngrok URL).
final baseUrlProvider = StateProvider<String>((ref) {
  if (kIsWeb) return 'http://localhost:8000';
  return 'http://10.0.2.2:8000';
});

/// Real API service wired to the backend.
final apiServiceProvider = Provider<ApiService>((ref) {
  final baseUrl = ref.watch(baseUrlProvider);
  return ApiService(baseUrl: baseUrl);
});

/// Mock API service (kept for fallback / offline testing).
final mockApiServiceProvider = Provider<MockApiService>((ref) {
  return MockApiService();
});

final storageServiceProvider = Provider<StorageService>((ref) {
  return StorageService();
});
