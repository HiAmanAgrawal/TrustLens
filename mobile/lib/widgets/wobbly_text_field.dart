import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import '../theme/app_theme.dart';
import '../theme/wobbly_borders.dart';

/// A TextField with wobbly InputDecoration border, Patrick Hand font,
/// and blue focus border.
class WobblyTextField extends StatelessWidget {
  final String? label;
  final String? hint;
  final TextEditingController? controller;
  final bool obscureText;
  final TextInputType? keyboardType;
  final int maxLines;
  final Widget? suffixIcon;
  final String? Function(String?)? validator;
  final void Function(String)? onChanged;

  const WobblyTextField({
    super.key,
    this.label,
    this.hint,
    this.controller,
    this.obscureText = false,
    this.keyboardType,
    this.maxLines = 1,
    this.suffixIcon,
    this.validator,
    this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (label != null) ...[
          Text(
            label!,
            style: GoogleFonts.plusJakartaSans(
              fontSize: 16,
              color: AppColors.onBackground,
            ),
          ),
          const SizedBox(height: 6),
        ],
        TextFormField(
          controller: controller,
          obscureText: obscureText,
          keyboardType: keyboardType,
          maxLines: maxLines,
          onChanged: onChanged,
          validator: validator,
          style: GoogleFonts.plusJakartaSans(
            fontSize: 16,
            color: AppColors.onBackground,
          ),
          decoration: InputDecoration(
            hintText: hint,
            hintStyle: GoogleFonts.plusJakartaSans(
              fontSize: 16,
              color: AppColors.onBackground.withValues(alpha: 0.4),
            ),
            filled: true,
            fillColor: AppColors.surface,
            suffixIcon: suffixIcon,
            contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
            enabledBorder: WobblyBorders.outlineInput(),
            focusedBorder: WobblyBorders.focusedInput(),
            errorBorder: WobblyBorders.outlineInput(color: AppColors.error),
            focusedErrorBorder: WobblyBorders.outlineInput(color: AppColors.error, width: 3),
          ),
        ),
      ],
    );
  }
}
