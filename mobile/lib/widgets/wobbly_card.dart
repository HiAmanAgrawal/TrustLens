import 'package:flutter/material.dart';

import '../theme/app_theme.dart';
import '../theme/wobbly_borders.dart';

/// Decoration type for WobblyCard — kept for backward compat.
enum CardDecoration { none, tape, tack }

/// A clean card with soft blue-tinted shadow, subtle border,
/// and optional gradient background for hero elements.
class WobblyCard extends StatefulWidget {
  final Widget child;
  final CardDecoration decoration;
  final double rotation; // ignored in new design
  final Offset shadowOffset; // ignored in new design
  final Color? backgroundColor;
  final Color borderColor;
  final double borderWidth;
  final EdgeInsetsGeometry padding;
  final EdgeInsetsGeometry margin;
  final VoidCallback? onTap;
  final Gradient? gradient;
  final BorderRadius? borderRadius;

  const WobblyCard({
    super.key,
    required this.child,
    this.decoration = CardDecoration.none,
    this.rotation = 0.0,
    this.shadowOffset = const Offset(0, 4),
    this.backgroundColor,
    this.borderColor = const Color(0x0D000000), // rgba(0,0,0,0.05)
    this.borderWidth = 1,
    this.padding = const EdgeInsets.all(16),
    this.margin = const EdgeInsets.all(0),
    this.onTap,
    this.gradient,
    this.borderRadius,
  });

  @override
  State<WobblyCard> createState() => _WobblyCardState();
}

class _WobblyCardState extends State<WobblyCard> {
  bool _isPressed = false;

  @override
  Widget build(BuildContext context) {
    final radius = widget.borderRadius ?? AppBorders.card;

    return Padding(
      padding: widget.margin,
      child: GestureDetector(
        onTapDown: widget.onTap != null ? (_) => setState(() => _isPressed = true) : null,
        onTapUp: widget.onTap != null
            ? (_) {
                setState(() => _isPressed = false);
                widget.onTap?.call();
              }
            : null,
        onTapCancel: widget.onTap != null ? () => setState(() => _isPressed = false) : null,
        child: AnimatedScale(
          scale: _isPressed ? 0.97 : 1.0,
          duration: const Duration(milliseconds: 150),
          curve: Curves.easeOut,
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 200),
            decoration: BoxDecoration(
              color: widget.gradient == null
                  ? (widget.backgroundColor ?? AppColors.surface)
                  : null,
              gradient: widget.gradient,
              borderRadius: radius,
              border: Border.all(
                color: widget.borderColor,
                width: widget.borderWidth,
              ),
              boxShadow: const [AppShadows.card],
            ),
            child: ClipRRect(
              borderRadius: radius,
              child: Padding(
                padding: widget.padding,
                child: widget.child,
              ),
            ),
          ),
        ),
      ),
    );
  }
}
