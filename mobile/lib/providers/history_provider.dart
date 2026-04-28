import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/scan_result.dart';

/// Scan history provider — maintains a chronological log of past scans.
/// History is populated in real-time as the user performs scans via scanProvider.
class HistoryNotifier extends StateNotifier<List<ScanResult>> {
  HistoryNotifier() : super([]);

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
  return HistoryNotifier();
});
