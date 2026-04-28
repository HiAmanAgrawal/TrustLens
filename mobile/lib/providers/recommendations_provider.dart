import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/recommendation.dart';
import 'service_providers.dart';

/// Recommendations state.
class RecommendationsState {
  final bool isLoading;
  final List<Recommendation> items;
  final String? error;

  const RecommendationsState({
    this.isLoading = false,
    this.items = const [],
    this.error,
  });
}

class RecommendationsNotifier extends StateNotifier<RecommendationsState> {
  final Ref ref;

  RecommendationsNotifier(this.ref) : super(const RecommendationsState()) {
    loadRecommendations();
  }

  Future<void> loadRecommendations() async {
    state = const RecommendationsState(isLoading: true);
    try {
      final api = ref.read(mockApiServiceProvider);
      final items = await api.getRecommendations();
      state = RecommendationsState(items: items);
    } catch (e) {
      state = RecommendationsState(error: e.toString());
    }
  }

  List<Recommendation> filterByCategory(String category) {
    if (category == 'All') return state.items;
    return state.items.where((r) => r.category == category).toList();
  }
}

final recommendationsProvider =
    StateNotifierProvider<RecommendationsNotifier, RecommendationsState>((ref) {
  return RecommendationsNotifier(ref);
});
