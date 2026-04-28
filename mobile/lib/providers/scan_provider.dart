import 'dart:typed_data';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/scan_result.dart';
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
  Future<void> scanImage(Uint8List imageBytes) async {
    state = const ScanState(isScanning: true);
    try {
      final api = ref.read(mockApiServiceProvider);
      final result = await api.scanImage(imageBytes);
      state = ScanState(result: result);
    } catch (e) {
      state = ScanState(error: e.toString());
    }
  }

  /// Scan via barcode/QR code text.
  Future<void> scanCode(String code) async {
    state = const ScanState(isScanning: true);
    try {
      final api = ref.read(mockApiServiceProvider);
      final result = await api.scanCode(code);
      state = ScanState(result: result);
    } catch (e) {
      state = ScanState(error: e.toString());
    }
  }

  /// Clear current scan state.
  void clear() {
    state = const ScanState();
  }
}

final scanProvider = StateNotifierProvider<ScanNotifier, ScanState>((ref) {
  return ScanNotifier(ref);
});
