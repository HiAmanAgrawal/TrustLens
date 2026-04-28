import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:lucide_icons/lucide_icons.dart';

import '../theme/wobbly_borders.dart';

enum ScanType { medicine, food }

/// Small pill badge with icon and label. Medicine = blue, Food = green.
class ScanTypeBadge extends StatelessWidget {
  final ScanType type;

  const ScanTypeBadge({super.key, required this.type});

  Color get _bgColor => type == ScanType.medicine
      ? const Color(0xFF2D5DA1).withValues(alpha: 0.15)
      : const Color(0xFF388E3C).withValues(alpha: 0.15);

  Color get _textColor =>
      type == ScanType.medicine ? const Color(0xFF2D5DA1) : const Color(0xFF388E3C);

  IconData get _icon =>
      type == ScanType.medicine ? LucideIcons.pill : LucideIcons.utensilsCrossed;

  String get _label => type == ScanType.medicine ? 'Medicine' : 'Food';

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: _bgColor,
        borderRadius: WobblyBorders.pill,
        border: Border.all(color: _textColor, width: 1.5),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(_icon, size: 14, color: _textColor),
          const SizedBox(width: 4),
          Text(
            _label,
            style: GoogleFonts.plusJakartaSans(
              fontSize: 13,
              color: _textColor,
              fontWeight: FontWeight.w400,
            ),
          ),
        ],
      ),
    );
  }
}
