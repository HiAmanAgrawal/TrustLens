import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:lucide_icons/lucide_icons.dart';

import '../theme/app_theme.dart';
import '../theme/wobbly_borders.dart';

/// Severity level for allergen/condition flags.
enum FlagSeverity { low, medium, high }

/// A single health compatibility flag.
class HealthFlag {
  final String ingredient;
  final String reason;
  final FlagSeverity severity;

  const HealthFlag({
    required this.ingredient,
    required this.reason,
    required this.severity,
  });
}

/// Displays allergen/condition flags with color-coded severity icons
/// and an overall compatibility score.
class HealthCompatibilityCard extends StatelessWidget {
  final List<HealthFlag> flags;
  final double compatibilityScore;

  const HealthCompatibilityCard({
    super.key,
    required this.flags,
    required this.compatibilityScore,
  });

  @override
  Widget build(BuildContext context) {
    final safeCount = flags.where((f) => f.severity == FlagSeverity.low).length;
    final totalCount = flags.length;

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: WobblyBorders.standard,
        border: Border.all(color: AppColors.border, width: 2),
        boxShadow: const [AppShadows.standard],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(LucideIcons.shieldCheck, size: 20, color: AppColors.secondary),
              const SizedBox(width: 8),
              Text(
                'Health Compatibility',
                style: GoogleFonts.plusJakartaSans(
                  fontSize: 18,
                  fontWeight: FontWeight.w700,
                  color: AppColors.onBackground,
                ),
              ),
              const Spacer(),
              _buildScoreBadge(),
            ],
          ),
          const SizedBox(height: 12),
          if (flags.isEmpty)
            Text(
              'No flags detected. Looks good!',
              style: GoogleFonts.plusJakartaSans(
                fontSize: 15,
                color: AppColors.verified,
              ),
            )
          else ...[
            ...flags.map(_buildFlagRow),
            const SizedBox(height: 8),
            Text(
              '$safeCount of $totalCount ingredients are safe for your profile',
              style: GoogleFonts.plusJakartaSans(
                fontSize: 14,
                color: AppColors.onBackground.withValues(alpha: 0.6),
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildScoreBadge() {
    final color = compatibilityScore >= 0.7
        ? AppColors.verified
        : compatibilityScore >= 0.4
            ? AppColors.cautionBadge
            : AppColors.unverified;

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.15),
        borderRadius: WobblyBorders.pill,
        border: Border.all(color: color, width: 1.5),
      ),
      child: Text(
        '${(compatibilityScore * 100).round()}%',
        style: GoogleFonts.plusJakartaSans(
          fontSize: 14,
          fontWeight: FontWeight.w700,
          color: color,
        ),
      ),
    );
  }

  Widget _buildFlagRow(HealthFlag flag) {
    Color severityColor;
    IconData severityIcon;

    switch (flag.severity) {
      case FlagSeverity.low:
        severityColor = AppColors.verified;
        severityIcon = LucideIcons.checkCircle;
        break;
      case FlagSeverity.medium:
        severityColor = AppColors.cautionBadge;
        severityIcon = LucideIcons.alertTriangle;
        break;
      case FlagSeverity.high:
        severityColor = AppColors.unverified;
        severityIcon = LucideIcons.xCircle;
        break;
    }

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        children: [
          Icon(severityIcon, size: 16, color: severityColor),
          const SizedBox(width: 8),
          Expanded(
            child: RichText(
              text: TextSpan(
                children: [
                  TextSpan(
                    text: flag.ingredient,
                    style: GoogleFonts.plusJakartaSans(
                      fontSize: 15,
                      fontWeight: FontWeight.w400,
                      color: AppColors.onBackground,
                    ),
                  ),
                  TextSpan(
                    text: ' — ${flag.reason}',
                    style: GoogleFonts.plusJakartaSans(
                      fontSize: 14,
                      color: AppColors.onBackground.withValues(alpha: 0.6),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}
