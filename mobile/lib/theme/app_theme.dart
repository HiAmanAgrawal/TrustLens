import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

/// TrustLens design tokens — Modern Healthcare design language.
///
/// Clean, professional, and trustworthy. Light mode default with
/// dark mode variant. Plus Jakarta Sans typography, blue-tinted shadows,
/// and consistent 8pt spacing grid.

// ---------------------------------------------------------------------------
// Colors
// ---------------------------------------------------------------------------

class AppColors {
  AppColors._();

  // Light Mode
  static const Color background = Color(0xFFF4F7FE);
  static const Color surface = Color(0xFFFFFFFF);
  static const Color surfaceSecondary = Color(0xFFEEF2FB);
  static const Color primary = Color(0xFF3B82F6);
  static const Color onPrimary = Color(0xFFFFFFFF);
  static const Color secondary = Color(0xFF10B981);
  static const Color onSecondary = Color(0xFFFFFFFF);
  static const Color warning = Color(0xFFF59E0B);
  static const Color error = Color(0xFFEF4444);
  static const Color textPrimary = Color(0xFF0F172A);
  static const Color textSecondary = Color(0xFF64748B);
  static const Color textTertiary = Color(0xFF94A3B8);
  static const Color border = Color(0x0F000000); // rgba(0,0,0,0.06)
  static const Color divider = Color(0x0F000000);

  // Verdict-specific
  static const Color verified = Color(0xFF10B981);
  static const Color cautionBadge = Color(0xFFF59E0B);
  static const Color unverified = Color(0xFFEF4444);

  // Gradients (use with LinearGradient)
  static const List<Color> primaryGradient = [Color(0xFF3B82F6), Color(0xFF6366F1)];
  static const List<Color> secondaryGradient = [Color(0xFF10B981), Color(0xFF3B82F6)];
  static const List<Color> warmGradient = [Color(0xFFF59E0B), Color(0xFFEF4444)];

  // Dark Mode
  static const Color darkBackground = Color(0xFF0D1117);
  static const Color darkSurface = Color(0xFF1A2235);
  static const Color darkSurfaceSecondary = Color(0xFF1E2D40);
  static const Color darkTextPrimary = Color(0xFFF1F5F9);
  static const Color darkTextSecondary = Color(0xFF94A3B8);
  static const Color darkBorder = Color(0x12FFFFFF); // rgba(255,255,255,0.07)
  static const Color darkGlass = Color(0x991E2D40); // rgba(30,45,64,0.6)
  static const Color darkGlassBorder = Color(0x14FFFFFF); // rgba(255,255,255,0.08)

  // Backward-compat aliases used across widgets
  static const Color onBackground = textPrimary;
  static const Color muted = surfaceSecondary;
  static const Color postItYellow = Color(0xFFFFF9C4);
  static const Color success = secondary;
  static const Color caution = warning;
}

// ---------------------------------------------------------------------------
// Shadows
// ---------------------------------------------------------------------------

class AppShadows {
  AppShadows._();

  static const BoxShadow card = BoxShadow(
    color: Color(0x143B82F6), // blue-tinted, 8% opacity
    offset: Offset(0, 4),
    blurRadius: 20,
  );

  static const BoxShadow cardDark = BoxShadow(
    color: Color(0x59000000), // 35% black
    offset: Offset(0, 8),
    blurRadius: 32,
  );

  static const BoxShadow buttonGlow = BoxShadow(
    color: Color(0x663B82F6), // 40% primary blue
    offset: Offset(0, 4),
    blurRadius: 16,
  );

  static const BoxShadow elevated = BoxShadow(
    color: Color(0x1A3B82F6),
    offset: Offset(0, 8),
    blurRadius: 32,
  );

  // Backward-compat aliases
  static const BoxShadow standard = card;
  static const BoxShadow emphasized = elevated;
  static const BoxShadow pressed = BoxShadow(
    color: Color(0x0A3B82F6),
    offset: Offset(0, 2),
    blurRadius: 8,
  );
  static const BoxShadow none = BoxShadow(color: Colors.transparent);
}

// ---------------------------------------------------------------------------
// Typography — Plus Jakarta Sans
// ---------------------------------------------------------------------------

class AppTypography {
  AppTypography._();

  // Display — 32px / Bold
  static TextStyle get display => GoogleFonts.plusJakartaSans(
        fontSize: 32,
        fontWeight: FontWeight.w700,
        color: AppColors.textPrimary,
        height: 1.2,
        letterSpacing: -0.3,
      );

  // Heading 1 — 24px / Bold
  static TextStyle get h1 => GoogleFonts.plusJakartaSans(
        fontSize: 24,
        fontWeight: FontWeight.w700,
        color: AppColors.textPrimary,
        height: 1.2,
        letterSpacing: -0.3,
      );

  // Heading 2 — 20px / SemiBold
  static TextStyle get h2 => GoogleFonts.plusJakartaSans(
        fontSize: 20,
        fontWeight: FontWeight.w600,
        color: AppColors.textPrimary,
        height: 1.2,
      );

  // Heading 3 — 17px / SemiBold
  static TextStyle get h3 => GoogleFonts.plusJakartaSans(
        fontSize: 17,
        fontWeight: FontWeight.w600,
        color: AppColors.textPrimary,
        height: 1.3,
      );

  // Body Large — 16px / Regular
  static TextStyle get bodyLarge => GoogleFonts.plusJakartaSans(
        fontSize: 16,
        fontWeight: FontWeight.w400,
        color: AppColors.textPrimary,
        height: 1.5,
      );

  // Body Small — 14px / Regular
  static TextStyle get bodySmall => GoogleFonts.plusJakartaSans(
        fontSize: 14,
        fontWeight: FontWeight.w400,
        color: AppColors.textSecondary,
        height: 1.5,
      );

  // Label — 13px / Medium
  static TextStyle get label => GoogleFonts.plusJakartaSans(
        fontSize: 13,
        fontWeight: FontWeight.w500,
        color: AppColors.textSecondary,
        height: 1.3,
      );

  // Micro — 11px / Regular
  static TextStyle get micro => GoogleFonts.plusJakartaSans(
        fontSize: 11,
        fontWeight: FontWeight.w400,
        color: AppColors.textTertiary,
        height: 1.3,
      );

  // Material TextTheme bridge getters (used by older widgets)
  static TextStyle get displayLarge => display;
  static TextStyle get displayMedium => h1;
  static TextStyle get displaySmall => h2;
  static TextStyle get headlineLarge => h1;
  static TextStyle get headlineMedium => h2;
  static TextStyle get headlineSmall => h3;
  static TextStyle get titleLarge => h3;
  static TextStyle get titleMedium => GoogleFonts.plusJakartaSans(
        fontSize: 16,
        fontWeight: FontWeight.w600,
        color: AppColors.textPrimary,
        height: 1.3,
      );
  static TextStyle get titleSmall => label;
  static TextStyle get bodyMedium => bodyLarge;
  static TextStyle get labelLarge => GoogleFonts.plusJakartaSans(
        fontSize: 14,
        fontWeight: FontWeight.w500,
        color: AppColors.textPrimary,
        height: 1.3,
      );
  static TextStyle get labelMedium => label;
  static TextStyle get labelSmall => micro;
}

// ---------------------------------------------------------------------------
// Gradients helper
// ---------------------------------------------------------------------------

class AppGradients {
  AppGradients._();

  static const LinearGradient primary = LinearGradient(
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
    colors: AppColors.primaryGradient,
  );

  static const LinearGradient secondary = LinearGradient(
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
    colors: AppColors.secondaryGradient,
  );

  static const LinearGradient warm = LinearGradient(
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
    colors: AppColors.warmGradient,
  );
}

// ---------------------------------------------------------------------------
// ThemeData builders
// ---------------------------------------------------------------------------

ThemeData buildAppTheme({bool dark = false}) {
  final bg = dark ? AppColors.darkBackground : AppColors.background;
  final surface = dark ? AppColors.darkSurface : AppColors.surface;
  final textPrimary = dark ? AppColors.darkTextPrimary : AppColors.textPrimary;
  final textSecondary = dark ? AppColors.darkTextSecondary : AppColors.textSecondary;
  final borderColor = dark ? AppColors.darkBorder : AppColors.border;

  return ThemeData(
    useMaterial3: true,
    brightness: dark ? Brightness.dark : Brightness.light,
    scaffoldBackgroundColor: bg,
    colorScheme: ColorScheme(
      brightness: dark ? Brightness.dark : Brightness.light,
      primary: AppColors.primary,
      onPrimary: AppColors.onPrimary,
      secondary: AppColors.secondary,
      onSecondary: AppColors.onSecondary,
      error: AppColors.error,
      onError: Colors.white,
      surface: surface,
      onSurface: textPrimary,
    ),
    textTheme: TextTheme(
      displayLarge: AppTypography.displayLarge.copyWith(color: textPrimary),
      displayMedium: AppTypography.displayMedium.copyWith(color: textPrimary),
      displaySmall: AppTypography.displaySmall.copyWith(color: textPrimary),
      headlineLarge: AppTypography.headlineLarge.copyWith(color: textPrimary),
      headlineMedium: AppTypography.headlineMedium.copyWith(color: textPrimary),
      headlineSmall: AppTypography.headlineSmall.copyWith(color: textPrimary),
      titleLarge: AppTypography.titleLarge.copyWith(color: textPrimary),
      titleMedium: AppTypography.titleMedium.copyWith(color: textPrimary),
      titleSmall: AppTypography.titleSmall.copyWith(color: textSecondary),
      bodyLarge: AppTypography.bodyLarge.copyWith(color: textPrimary),
      bodyMedium: AppTypography.bodyMedium.copyWith(color: textPrimary),
      bodySmall: AppTypography.bodySmall.copyWith(color: textSecondary),
      labelLarge: AppTypography.labelLarge.copyWith(color: textPrimary),
      labelMedium: AppTypography.labelMedium.copyWith(color: textSecondary),
      labelSmall: AppTypography.labelSmall.copyWith(color: textSecondary),
    ),
    appBarTheme: AppBarTheme(
      backgroundColor: Colors.transparent,
      foregroundColor: textPrimary,
      elevation: 0,
      centerTitle: false,
      titleTextStyle: AppTypography.h3.copyWith(color: textPrimary),
    ),
    cardTheme: CardThemeData(
      color: surface,
      elevation: 0,
      margin: const EdgeInsets.all(0),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(16),
        side: BorderSide(color: borderColor),
      ),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: dark ? AppColors.darkSurfaceSecondary : AppColors.surfaceSecondary,
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      labelStyle: AppTypography.label.copyWith(color: textSecondary),
      hintStyle: AppTypography.bodyLarge.copyWith(color: AppColors.textTertiary),
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: BorderSide(color: borderColor),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: BorderSide(color: borderColor),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: const BorderSide(color: AppColors.primary, width: 2),
      ),
    ),
    elevatedButtonTheme: ElevatedButtonThemeData(
      style: ElevatedButton.styleFrom(
        backgroundColor: AppColors.primary,
        foregroundColor: AppColors.onPrimary,
        elevation: 0,
        minimumSize: const Size(0, 52),
        padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 14),
        textStyle: GoogleFonts.plusJakartaSans(
          fontSize: 16,
          fontWeight: FontWeight.w700,
        ),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(14),
        ),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: AppColors.primary,
        minimumSize: const Size(0, 52),
        padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 14),
        textStyle: GoogleFonts.plusJakartaSans(
          fontSize: 16,
          fontWeight: FontWeight.w700,
        ),
        side: const BorderSide(color: AppColors.primary, width: 2),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(14),
        ),
      ),
    ),
    bottomNavigationBarTheme: BottomNavigationBarThemeData(
      backgroundColor: surface,
      selectedItemColor: AppColors.primary,
      unselectedItemColor: AppColors.textTertiary,
      type: BottomNavigationBarType.fixed,
      elevation: 0,
    ),
    dividerTheme: DividerThemeData(color: borderColor, thickness: 1),
  );
}
