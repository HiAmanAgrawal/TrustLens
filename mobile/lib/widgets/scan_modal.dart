import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:lucide_icons/lucide_icons.dart';

import '../theme/app_theme.dart';
import '../theme/wobbly_borders.dart';

/// Bottom sheet scan type selector.
/// Step 1: Choose Medicine or Food.
/// Step 2: Choose Camera or Upload.
class ScanModal extends StatefulWidget {
  const ScanModal({super.key});

  @override
  State<ScanModal> createState() => _ScanModalState();
}

class _ScanModalState extends State<ScanModal> {
  String? _selectedType; // 'medicine' or 'food'

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: WobblyBorders.bottomSheet,
        boxShadow: const [AppShadows.elevated],
      ),
      padding: const EdgeInsets.fromLTRB(20, 12, 20, 24),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          // Handle bar
          Container(
            width: 48,
            height: 5,
            decoration: BoxDecoration(
              color: AppColors.muted,
              borderRadius: BorderRadius.circular(3),
            ),
          ),
          const SizedBox(height: 20),
          Text(
            _selectedType == null ? 'What are you scanning?' : 'How do you want to scan?',
            style: GoogleFonts.plusJakartaSans(
              fontSize: 22,
              fontWeight: FontWeight.w700,
              color: AppColors.onBackground,
            ),
          ),
          const SizedBox(height: 20),
          if (_selectedType == null) _buildTypeSelector() else _buildInputMethodSelector(),
          const SizedBox(height: 12),
        ],
      ),
    );
  }

  Widget _buildTypeSelector() {
    return Row(
      children: [
        Expanded(
          child: _ScanOptionCard(
            icon: LucideIcons.pill,
            emoji: '\uD83D\uDC8A',
            title: 'Medicine',
            subtitle: 'Verify authenticity, check batch, manufacturer',
            isSelected: _selectedType == 'medicine',
            onTap: () => setState(() => _selectedType = 'medicine'),
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: _ScanOptionCard(
            icon: LucideIcons.package,
            emoji: '\uD83E\uDD6B',
            title: 'Packaged Food',
            subtitle: 'Read labels, check ingredients, allergen warnings',
            isSelected: _selectedType == 'food',
            onTap: () => setState(() => _selectedType = 'food'),
          ),
        ),
      ],
    );
  }

  Widget _buildInputMethodSelector() {
    return Column(
      children: [
        Row(
          children: [
            Expanded(
              child: _ScanOptionCard(
                icon: LucideIcons.camera,
                emoji: '\uD83D\uDCF7',
                title: 'Use Camera',
                subtitle: 'Take a photo of the product',
                isSelected: false,
                onTap: () {
                  Navigator.of(context).pop();
                  // TODO: Open camera — will be wired in Phase 2
                  context.push('/scan-result');
                },
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: _ScanOptionCard(
                icon: LucideIcons.image,
                emoji: '\uD83D\uDDBC',
                title: 'Upload Photo',
                subtitle: 'Choose from your gallery',
                isSelected: false,
                onTap: () {
                  Navigator.of(context).pop();
                  // TODO: Open gallery — will be wired in Phase 2
                  context.push('/scan-result');
                },
              ),
            ),
          ],
        ),
        const SizedBox(height: 12),
        GestureDetector(
          onTap: () => setState(() => _selectedType = null),
          child: Text(
            '\u2190 Back to scan type',
            style: GoogleFonts.plusJakartaSans(
              fontSize: 15,
              color: AppColors.secondary,
              decoration: TextDecoration.underline,
            ),
          ),
        ),
      ],
    );
  }
}

class _ScanOptionCard extends StatefulWidget {
  final IconData icon;
  final String emoji;
  final String title;
  final String subtitle;
  final bool isSelected;
  final VoidCallback onTap;

  const _ScanOptionCard({
    required this.icon,
    required this.emoji,
    required this.title,
    required this.subtitle,
    required this.isSelected,
    required this.onTap,
  });

  @override
  State<_ScanOptionCard> createState() => _ScanOptionCardState();
}

class _ScanOptionCardState extends State<_ScanOptionCard> {
  bool _isPressed = false;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTapDown: (_) => setState(() => _isPressed = true),
      onTapUp: (_) {
        setState(() => _isPressed = false);
        widget.onTap();
      },
      onTapCancel: () => setState(() => _isPressed = false),
      child: AnimatedScale(
        scale: _isPressed ? 0.96 : 1.0,
        duration: const Duration(milliseconds: 150),
        curve: Curves.easeOut,
        child: Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: widget.isSelected
                ? AppColors.primary.withValues(alpha: 0.08)
                : AppColors.surface,
            borderRadius: WobblyBorders.standard,
            border: Border.all(
              color: widget.isSelected ? AppColors.primary : AppColors.border,
              width: widget.isSelected ? 2 : 1,
            ),
            boxShadow: const [AppShadows.card],
          ),
          child: Column(
            children: [
              Text(widget.emoji, style: const TextStyle(fontSize: 32)),
              const SizedBox(height: 8),
              Text(
                widget.title,
                style: GoogleFonts.plusJakartaSans(
                  fontSize: 16,
                  fontWeight: FontWeight.w700,
                  color: AppColors.onBackground,
                ),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 4),
              Text(
                widget.subtitle,
                style: GoogleFonts.plusJakartaSans(
                  fontSize: 13,
                  color: AppColors.onBackground.withValues(alpha: 0.6),
                ),
                textAlign: TextAlign.center,
              ),
            ],
          ),
        ),
      ),
    );
  }
}
