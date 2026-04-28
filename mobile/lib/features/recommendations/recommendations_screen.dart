import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:lucide_icons/lucide_icons.dart';

import '../../theme/app_theme.dart';
import '../../theme/wobbly_borders.dart';
import '../../widgets/dot_grid_background.dart';
import '../../widgets/wobbly_card.dart';

/// Recommendations screen — personalized food/diet recommendations
/// based on the user's health profile.
class RecommendationsScreen extends StatefulWidget {
  const RecommendationsScreen({super.key});

  @override
  State<RecommendationsScreen> createState() => _RecommendationsScreenState();
}

class _RecommendationsScreenState extends State<RecommendationsScreen> {
  String _activeCategory = 'All';
  final _categories = ['All', 'Diet', 'Supplements', 'Avoid'];

  // Mock data
  final _recommendations = [
    _Rec('Oats with Almonds', 'Good for Diabetes', 'Diet', 0.92,
        'High in fiber and healthy fats. Helps regulate blood sugar levels.'),
    _Rec('Spinach & Kale Salad', 'Rich in iron', 'Diet', 0.88,
        'Excellent source of vitamins A, C, K and minerals.'),
    _Rec('Vitamin D3 Supplement', 'Supports bone health', 'Supplements', 0.75,
        'Recommended for those with limited sun exposure.'),
    _Rec('Processed Cheese', 'High sodium content', 'Avoid', 0.3,
        'Contains excessive sodium which may aggravate hypertension.'),
    _Rec('Low-fat Yogurt', 'Good source of probiotics', 'Diet', 0.85,
        'Supports gut health and calcium intake.'),
  ];

  List<_Rec> get _filteredRecs => _activeCategory == 'All'
      ? _recommendations
      : _recommendations.where((r) => r.category == _activeCategory).toList();

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      body: DotGridBackground(
        child: SafeArea(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // App bar
              Padding(
                padding: const EdgeInsets.fromLTRB(20, 16, 20, 0),
                child: Text(
                  'For You',
                  style: GoogleFonts.plusJakartaSans(
                    fontSize: 28,
                    fontWeight: FontWeight.w700,
                    color: AppColors.onBackground,
                  ),
                ),
              ),
              Padding(
                padding: const EdgeInsets.fromLTRB(20, 2, 20, 12),
                child: Text(
                  'Based on your health profile',
                  style: GoogleFonts.plusJakartaSans(
                    fontSize: 16,
                    color: AppColors.onBackground.withValues(alpha: 0.5),
                  ),
                ),
              ),
              // Category filter tabs
              _buildCategoryTabs(),
              const SizedBox(height: 8),
              // Recommendations list
              Expanded(
                child: ListView(
                  padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 8),
                  children: [
                    ..._filteredRecs.map((r) => _buildRecCard(r)),
                    const SizedBox(height: 8),
                    _buildWeeklyDigest(),
                    const SizedBox(height: 16),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildCategoryTabs() {
    return SizedBox(
      height: 42,
      child: ListView.builder(
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.symmetric(horizontal: 16),
        itemCount: _categories.length,
        itemBuilder: (context, index) {
          final cat = _categories[index];
          final isActive = cat == _activeCategory;
          return Padding(
            padding: const EdgeInsets.symmetric(horizontal: 4),
            child: GestureDetector(
              onTap: () => setState(() => _activeCategory = cat),
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                decoration: BoxDecoration(
                  color: isActive ? AppColors.primary : AppColors.surface,
                  borderRadius: WobblyBorders.pill,
                  border: Border.all(
                    color: isActive ? AppColors.primary : AppColors.border,
                    width: 2,
                  ),
                ),
                child: Text(
                  cat,
                  style: GoogleFonts.plusJakartaSans(
                    fontSize: 14,
                    color: isActive ? AppColors.onPrimary : AppColors.onBackground,
                  ),
                ),
              ),
            ),
          );
        },
      ),
    );
  }

  Widget _buildRecCard(_Rec rec) {
    final isAvoid = rec.category == 'Avoid';
    final scoreColor = rec.score >= 0.7
        ? AppColors.verified
        : rec.score >= 0.4
            ? AppColors.cautionBadge
            : AppColors.unverified;

    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: WobblyCard(
        onTap: () => context.push('/ai-chat'),
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    rec.name,
                    style: GoogleFonts.plusJakartaSans(
                      fontSize: 18,
                      fontWeight: FontWeight.w700,
                      color: AppColors.onBackground,
                    ),
                  ),
                ),
                // Compatibility score circle
                _buildScoreCircle(rec.score, scoreColor),
              ],
            ),
            const SizedBox(height: 8),
            // Reason chip
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
              decoration: BoxDecoration(
                color: isAvoid
                    ? AppColors.unverified.withValues(alpha: 0.1)
                    : AppColors.verified.withValues(alpha: 0.1),
                borderRadius: WobblyBorders.pill,
                border: Border.all(
                  color: isAvoid ? AppColors.unverified : AppColors.verified,
                  width: 1.5,
                ),
              ),
              child: Text(
                rec.reason,
                style: GoogleFonts.plusJakartaSans(
                  fontSize: 13,
                  color: isAvoid ? AppColors.unverified : AppColors.verified,
                ),
              ),
            ),
            const SizedBox(height: 8),
            Text(
              rec.description,
              style: GoogleFonts.plusJakartaSans(
                fontSize: 14,
                color: AppColors.onBackground.withValues(alpha: 0.6),
              ),
            ),
            const SizedBox(height: 6),
            Text(
              'AI Recommendation',
              style: GoogleFonts.plusJakartaSans(
                fontSize: 12,
                color: AppColors.secondary.withValues(alpha: 0.6),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildScoreCircle(double score, Color color) {
    return SizedBox(
      width: 44,
      height: 44,
      child: Stack(
        alignment: Alignment.center,
        children: [
          CircularProgressIndicator(
            value: score,
            strokeWidth: 3,
            backgroundColor: AppColors.muted,
            valueColor: AlwaysStoppedAnimation(color),
          ),
          Text(
            '${(score * 100).round()}',
            style: GoogleFonts.plusJakartaSans(
              fontSize: 13,
              fontWeight: FontWeight.w700,
              color: color,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildWeeklyDigest() {
    return WobblyCard(
      backgroundColor: AppColors.secondary.withValues(alpha: 0.06),
      borderColor: AppColors.secondary.withValues(alpha: 0.15),
      padding: const EdgeInsets.all(16),
      child: Row(
        children: [
          const Icon(LucideIcons.calendarCheck, size: 28, color: AppColors.secondary),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Weekly Digest',
                  style: GoogleFonts.plusJakartaSans(
                    fontSize: 16,
                    fontWeight: FontWeight.w700,
                    color: AppColors.onBackground,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  'This week, 3 of 5 foods you scanned were compatible with your profile.',
                  style: GoogleFonts.plusJakartaSans(
                    fontSize: 14,
                    color: AppColors.onBackground.withValues(alpha: 0.7),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _Rec {
  final String name;
  final String reason;
  final String category;
  final double score;
  final String description;
  _Rec(this.name, this.reason, this.category, this.score, this.description);
}
