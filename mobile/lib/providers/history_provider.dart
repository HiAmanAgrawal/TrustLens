import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/scan_result.dart';
import 'service_providers.dart';

/// Scan history provider — maintains a chronological log of past scans.
class HistoryNotifier extends StateNotifier<List<ScanResult>> {
  final Ref ref;

  HistoryNotifier(this.ref) : super([]) {
    _loadMockHistory();
  }

  /// Load mock history for UI testing.
  void _loadMockHistory() {
    final mockApi = ref.read(mockApiServiceProvider);
    state = [
      mockApi.mockFoodResult(),
      ScanResult(
        id: 'hist-001',
        status: 'match_ok',
        message: 'Label matches the manufacturer\'s information.',
        verdict: 'safe',
        score: 8,
        summary: 'Label matches.',
        labelFields: const {'drug_name': 'DOLO-650', 'batch': 'DOBS3975'},
        category: 'pharma',
        scannedAt: DateTime.now().subtract(const Duration(hours: 2)),
      ),
      ScanResult(
        id: 'hist-003',
        status: 'match_disagrees',
        message: 'Label and manufacturer information disagree.',
        verdict: 'high_risk',
        score: 2,
        summary: 'Label mismatch detected.',
        labelFields: const {'drug_name': 'CROCIN ADVANCE', 'batch': 'XYZ999'},
        category: 'pharma',
        scannedAt: DateTime.now().subtract(const Duration(days: 3)),
      ),
    ];
  }

  /// Add a new scan to history.
  void addScan(ScanResult result) {
    state = [result, ...state];
  }

  /// Get scans filtered by type.
  List<ScanResult> filterByType(String filter) {
    switch (filter) {
      case 'Medicine':
        return state.where((s) => s.isMedicine).toList();
      case 'Food':
        return state.where((s) => s.isFood).toList();
      case 'Verified':
        return state.where((s) => s.verdict == 'safe').toList();
      case 'Flagged':
        return state
            .where((s) => s.verdict == 'high_risk' || s.verdict == 'caution')
            .toList();
      default:
        return state;
    }
  }
}

final historyProvider =
    StateNotifierProvider<HistoryNotifier, List<ScanResult>>((ref) {
  return HistoryNotifier(ref);
});
