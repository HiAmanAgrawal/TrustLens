import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import '../theme/app_theme.dart';
import '../theme/wobbly_borders.dart';

enum VerdictResult { verified, caution, unverified }

/// Pill-shaped verdict badge with clean styling.
/// Colors: teal-green (verified), amber (caution), red (unverified).
class ResultBadge extends StatelessWidget {
  final VerdictResult result;
  final double fontSize;

  const ResultBadge({
    super.key,
    required this.result,
    this.fontSize = 32,
  });

  Color get _color {
    switch (result) {
      case VerdictResult.verified:
        return AppColors.verified;
      case VerdictResult.caution:
        return AppColors.cautionBadge;
      case VerdictResult.unverified:
        return AppColors.unverified;
    }
  }

  String get _label {
    switch (result) {
      case VerdictResult.verified:
        return '\u2713 VERIFIED';
      case VerdictResult.caution:
        return '\u26A0 CAUTION';
      case VerdictResult.unverified:
        return '\u2717 UNVERIFIED';
    }
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 10),
      decoration: BoxDecoration(
        color: _color.withValues(alpha: 0.12),
        borderRadius: WobblyBorders.pill,
        border: Border.all(color: _color, width: 2),
      ),
      child: Text(
        _label,
        style: GoogleFonts.plusJakartaSans(
          fontSize: fontSize,
          fontWeight: FontWeight.w700,
          color: _color,
        ),
      ),
    );
  }
}
