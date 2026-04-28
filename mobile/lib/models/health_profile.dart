/// Health profile data model for user's health information.
class HealthProfile {
  final String? ageRange;
  final String? biologicalSex;
  final List<String> healthConditions;
  final List<String> dietaryPreferences;
  final String? currentMedications;

  const HealthProfile({
    this.ageRange,
    this.biologicalSex,
    this.healthConditions = const [],
    this.dietaryPreferences = const [],
    this.currentMedications,
  });

  bool get isEmpty =>
      ageRange == null &&
      biologicalSex == null &&
      healthConditions.isEmpty &&
      dietaryPreferences.isEmpty &&
      (currentMedications == null || currentMedications!.isEmpty);

  factory HealthProfile.fromJson(Map<String, dynamic> json) => HealthProfile(
        ageRange: json['age_range'] as String?,
        biologicalSex: json['biological_sex'] as String?,
        healthConditions: (json['health_conditions'] as List<dynamic>?)
                ?.map((e) => e.toString())
                .toList() ??
            [],
        dietaryPreferences: (json['dietary_preferences'] as List<dynamic>?)
                ?.map((e) => e.toString())
                .toList() ??
            [],
        currentMedications: json['current_medications'] as String?,
      );

  Map<String, dynamic> toJson() => {
        'age_range': ageRange,
        'biological_sex': biologicalSex,
        'health_conditions': healthConditions,
        'dietary_preferences': dietaryPreferences,
        'current_medications': currentMedications,
      };

  HealthProfile copyWith({
    String? ageRange,
    String? biologicalSex,
    List<String>? healthConditions,
    List<String>? dietaryPreferences,
    String? currentMedications,
  }) {
    return HealthProfile(
      ageRange: ageRange ?? this.ageRange,
      biologicalSex: biologicalSex ?? this.biologicalSex,
      healthConditions: healthConditions ?? this.healthConditions,
      dietaryPreferences: dietaryPreferences ?? this.dietaryPreferences,
      currentMedications: currentMedications ?? this.currentMedications,
    );
  }
}
