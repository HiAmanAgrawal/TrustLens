import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../services/mock_api_service.dart';
import '../services/storage_service.dart';

/// Core service providers — single instances shared across the app.

final mockApiServiceProvider = Provider<MockApiService>((ref) {
  return MockApiService();
});

final storageServiceProvider = Provider<StorageService>((ref) {
  return StorageService();
});
