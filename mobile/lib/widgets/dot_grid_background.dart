import 'package:flutter/material.dart';

import '../theme/app_theme.dart';

/// Clean app background — applies the scaffold background color.
/// In the new design system, this replaces the old dot-grid paper pattern
/// with a clean, solid background. Kept as a wrapper for backward compat.
class DotGridBackground extends StatelessWidget {
  final Widget child;

  const DotGridBackground({super.key, required this.child});

  @override
  Widget build(BuildContext context) {
    return Container(
      color: AppColors.background,
      child: child,
    );
  }
}
