import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import '../theme/app_theme.dart';
import '../theme/wobbly_borders.dart';

/// Button variant — primary (gradient fill) or secondary (outline).
enum WobblyButtonVariant { primary, secondary }

/// A modern button with gradient fill (primary) or outline (secondary),
/// scale-on-press animation, and optional blue glow shadow.
class WobblyButton extends StatefulWidget {
  final String label;
  final VoidCallback? onTap;
  final WobblyButtonVariant variant;
  final IconData? icon;
  final bool isLoading;
  final double? width;

  const WobblyButton({
    super.key,
    required this.label,
    this.onTap,
    this.variant = WobblyButtonVariant.primary,
    this.icon,
    this.isLoading = false,
    this.width,
  });

  @override
  State<WobblyButton> createState() => _WobblyButtonState();
}

class _WobblyButtonState extends State<WobblyButton> {
  bool _isPressed = false;

  bool get _isPrimary => widget.variant == WobblyButtonVariant.primary;
  bool get _disabled => widget.onTap == null;

  Color get _textColor => _isPrimary
      ? AppColors.onPrimary
      : AppColors.primary;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTapDown: !_disabled ? (_) => setState(() => _isPressed = true) : null,
      onTapUp: !_disabled
          ? (_) {
              setState(() => _isPressed = false);
              widget.onTap?.call();
            }
          : null,
      onTapCancel: !_disabled ? () => setState(() => _isPressed = false) : null,
      child: AnimatedScale(
        scale: _isPressed ? 0.96 : 1.0,
        duration: const Duration(milliseconds: 150),
        curve: Curves.easeOut,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 200),
          width: widget.width,
          height: 52,
          padding: const EdgeInsets.symmetric(horizontal: 24),
          decoration: BoxDecoration(
            gradient: _isPrimary && !_disabled ? AppGradients.primary : null,
            color: _isPrimary
                ? (_disabled ? AppColors.surfaceSecondary : null)
                : Colors.transparent,
            borderRadius: AppBorders.button,
            border: _isPrimary
                ? null
                : Border.all(
                    color: _disabled ? AppColors.textTertiary : AppColors.primary,
                    width: 2,
                  ),
            boxShadow: _isPrimary && !_disabled && _isPressed
                ? const [AppShadows.buttonGlow]
                : null,
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              if (widget.isLoading) ...[
                SizedBox(
                  width: 18,
                  height: 18,
                  child: CircularProgressIndicator(
                    strokeWidth: 2,
                    color: _textColor,
                  ),
                ),
                const SizedBox(width: 10),
              ] else if (widget.icon != null) ...[
                Icon(widget.icon, color: _disabled ? AppColors.textTertiary : _textColor, size: 20),
                const SizedBox(width: 10),
              ],
              Text(
                widget.label,
                style: GoogleFonts.plusJakartaSans(
                  fontSize: 16,
                  fontWeight: FontWeight.w700,
                  color: _disabled ? AppColors.textTertiary : _textColor,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
