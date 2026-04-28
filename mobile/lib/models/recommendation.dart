/// Recommendation model from the AI recommendation engine.
class Recommendation {
  final String title;
  final String reason;
  final String category; // Diet | Supplements | Avoid
  final double compatibilityScore;
  final String? description;

  const Recommendation({
    required this.title,
    required this.reason,
    required this.category,
    required this.compatibilityScore,
    this.description,
  });

  bool get isAvoid => category == 'Avoid';

  factory Recommendation.fromJson(Map<String, dynamic> json) => Recommendation(
        title: json['title'] as String,
        reason: json['reason'] as String,
        category: json['category'] as String,
        compatibilityScore: (json['compatibility_score'] as num).toDouble(),
        description: json['description'] as String?,
      );

  Map<String, dynamic> toJson() => {
        'title': title,
        'reason': reason,
        'category': category,
        'compatibility_score': compatibilityScore,
        'description': description,
      };
}
