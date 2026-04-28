import 'package:flutter/material.dart';
import 'package:lucide_icons/lucide_icons.dart';

import '../theme/app_theme.dart';

/// Scale-pulsing center bottom nav button with gradient fill and glow shadow.
/// 56px diameter, primary gradient, blue glow, pulses 1.0 → 1.05.
class AnimatedScanFab extends StatefulWidget {
  final VoidCallback? onTap;

  const AnimatedScanFab({super.key, this.onTap});

  @override
  State<AnimatedScanFab> createState() => _AnimatedScanFabState();
}

class _AnimatedScanFabState extends State<AnimatedScanFab>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;
  late final Animation<double> _scaleAnimation;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 2),
    )..repeat(reverse: true);

    _scaleAnimation = Tween<double>(begin: 1.0, end: 1.05).animate(
      CurvedAnimation(parent: _controller, curve: Curves.easeInOut),
    );
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return ScaleTransition(
      scale: _scaleAnimation,
      child: GestureDetector(
        onTap: widget.onTap,
        child: Container(
          width: 56,
          height: 56,
          decoration: const BoxDecoration(
            gradient: AppGradients.primary,
            shape: BoxShape.circle,
            boxShadow: [AppShadows.buttonGlow],
          ),
          child: const Icon(
            LucideIcons.plus,
            color: AppColors.onPrimary,
            size: 28,
          ),
        ),
      ),
    );
  }
}
