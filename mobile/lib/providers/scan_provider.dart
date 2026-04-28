import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/scan_result.dart';
import 'history_provider.dart';
import 'service_providers.dart';

/// State for the current scan operation.
class ScanState {
  final bool isScanning;
  final ScanResult? result;
  final String? error;

  const ScanState({
    this.isScanning = false,
    this.result,
    this.error,
  });

  ScanState copyWith({
    bool? isScanning,
    ScanResult? result,
    String? error,
  }) {
    return ScanState(
      isScanning: isScanning ?? this.isScanning,
      result: result ?? this.result,
      error: error,
    );
  }
}

class ScanNotifier extends StateNotifier<ScanState> {
  final Ref ref;

  ScanNotifier(this.ref) : super(const ScanState());

  /// Scan an image (medicine or food — backend auto-classifies).
  Future<void> scanImage(Uint8List imageBytes, {String filename = 'scan.jpg'}) async {
    state = const ScanState(isScanning: true);
    try {
      final api = ref.read(apiServiceProvider);
      final result = await api.scanImage(imageBytes, filename: filename);
      state = ScanState(result: result);
      ref.read(historyProvider.notifier).addScan(result);
    } on DioException catch (e) {
      state = ScanState(error: _friendlyError(e));
    } catch (e) {
      state = ScanState(error: e.toString());
    }
  }

  /// Scan via barcode/QR code text.
  Future<void> scanCode(String code) async {
    state = const ScanState(isScanning: true);
    try {
      final api = ref.read(apiServiceProvider);
      final result = await api.scanCode(code);
      state = ScanState(result: result);
      ref.read(historyProvider.notifier).addScan(result);
    } on DioException catch (e) {
      state = ScanState(error: _friendlyError(e));
    } catch (e) {
      state = ScanState(error: e.toString());
    }
  }

  /// Clear current scan state.
  void clear() {
    state = const ScanState();
  }

  /// Restore a previous scan result (e.g. from history).
  void restoreResult(ScanResult result) {
    state = ScanState(result: result);
  }

  /// Convert Dio errors to user-friendly messages.
  String _friendlyError(DioException e) {
    switch (e.type) {
      case DioExceptionType.connectionTimeout:
      case DioExceptionType.sendTimeout:
      case DioExceptionType.receiveTimeout:
        return 'Request timed out. The server may be busy — please try again.';
      case DioExceptionType.connectionError:
        return 'Could not connect to the backend. Check your URL in Profile settings.';
      default:
        if (e.response?.data is Map) {
          final data = e.response!.data as Map;
          return data['message'] as String? ?? data['detail'] as String? ?? 'Server error. Please try again.';
        }
        return 'Network error. Please check your connection.';
    }
  }
}

final scanProvider = StateNotifierProvider<ScanNotifier, ScanState>((ref) {
  return ScanNotifier(ref);
});
