import 'package:flutter/material.dart';

import 'app_theme.dart';

/// Clean, consistent border radius system for TrustLens.
///
/// Standard card: 16px, Hero/large: 20px, Compact: 12px, Chips: 8px,
/// Pill: 999px, Buttons: 14px, Inputs: 12px.
class AppBorders {
  AppBorders._();

  /// Standard card — 16px
  static final BorderRadius card = BorderRadius.circular(16);

  /// Alias for backward compat (was WobblyBorders.standard)
  static final BorderRadius standard = card;

  /// Hero / large card — 20px
  static final BorderRadius hero = BorderRadius.circular(20);

  /// Compact card — 12px
  static final BorderRadius compact = BorderRadius.circular(12);

  /// Inner chips — 8px
  static final BorderRadius chip = BorderRadius.circular(8);

  /// Pill — 999px (badges, tags)
  static final BorderRadius pill = BorderRadius.circular(999);

  /// Buttons — 14px
  static final BorderRadius button = BorderRadius.circular(14);

  /// Inputs — 12px
  static final BorderRadius input = BorderRadius.circular(12);

  /// Icon button — 12px
  static final BorderRadius iconButton = BorderRadius.circular(12);

  /// Tab container — 10px
  static final BorderRadius tab = BorderRadius.circular(10);

  /// Chat bubble — user (right-aligned)
  static const BorderRadius chatUser = BorderRadius.only(
    topLeft: Radius.circular(16),
    topRight: Radius.circular(16),
    bottomLeft: Radius.circular(16),
    bottomRight: Radius.circular(4),
  );

  /// Chat bubble — AI (left-aligned)
  static const BorderRadius chatAi = BorderRadius.only(
    topLeft: Radius.circular(4),
    topRight: Radius.circular(16),
    bottomLeft: Radius.circular(16),
    bottomRight: Radius.circular(16),
  );

  /// Bottom sheet top corners
  static const BorderRadius bottomSheet = BorderRadius.only(
    topLeft: Radius.circular(20),
    topRight: Radius.circular(20),
  );

  /// Standard card ShapeBorder for Material widgets.
  static ShapeBorder get cardShape => RoundedRectangleBorder(
        borderRadius: card,
        side: const BorderSide(color: AppColors.border),
      );

  /// Input border (default state).
  static OutlineInputBorder outlineInput({
    Color color = const Color(0x0F000000),
    double width = 1,
  }) {
    return OutlineInputBorder(
      borderRadius: input,
      borderSide: BorderSide(color: color, width: width),
    );
  }

  /// Input border (focused state).
  static OutlineInputBorder focusedInput({
    Color color = const Color(0xFF3B82F6),
    double width = 2,
  }) {
    return OutlineInputBorder(
      borderRadius: input,
      borderSide: BorderSide(color: color, width: width),
    );
  }
}

/// Backward-compatible alias so existing widgets don't break.
/// New code should use [AppBorders] directly.
typedef WobblyBorders = AppBorders;
