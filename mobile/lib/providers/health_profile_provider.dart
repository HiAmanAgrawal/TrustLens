import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/health_profile.dart';
import 'service_providers.dart';

class HealthProfileNotifier extends StateNotifier<HealthProfile> {
  final Ref ref;

  HealthProfileNotifier(this.ref) : super(const HealthProfile());

  /// Load profile from secure storage.
  Future<void> loadProfile() async {
    final storage = ref.read(storageServiceProvider);
    final profile = await storage.getHealthProfile();
    if (profile != null) {
      state = profile;
    }
  }

  /// Save profile to secure storage.
  Future<void> saveProfile(HealthProfile profile) async {
    final storage = ref.read(storageServiceProvider);
    await storage.setHealthProfile(profile);
    state = profile;
  }

  /// Update a specific field.
  Future<void> updateProfile({
    String? ageRange,
    String? biologicalSex,
    List<String>? healthConditions,
    List<String>? dietaryPreferences,
    String? currentMedications,
  }) async {
    final updated = state.copyWith(
      ageRange: ageRange,
      biologicalSex: biologicalSex,
      healthConditions: healthConditions,
      dietaryPreferences: dietaryPreferences,
      currentMedications: currentMedications,
    );
    await saveProfile(updated);
  }
}

final healthProfileProvider =
    StateNotifierProvider<HealthProfileNotifier, HealthProfile>((ref) {
  return HealthProfileNotifier(ref);
});
