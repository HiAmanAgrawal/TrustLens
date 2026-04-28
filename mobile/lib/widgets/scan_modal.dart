import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:image_picker/image_picker.dart';
import 'package:lucide_icons/lucide_icons.dart';

import '../providers/scan_provider.dart';
import '../theme/app_theme.dart';
import '../theme/wobbly_borders.dart';

/// Bottom sheet scan type selector.
/// Step 1: Choose Medicine or Food.
/// Step 2: Choose Camera, Upload, or Enter Code.
class ScanModal extends ConsumerStatefulWidget {
  const ScanModal({super.key});

  @override
  ConsumerState<ScanModal> createState() => _ScanModalState();
}

class _ScanModalState extends ConsumerState<ScanModal> {
  String? _selectedType; // 'medicine' or 'food'
  final _picker = ImagePicker();
  final _codeController = TextEditingController();
  bool _showCodeInput = false;

  @override
  void dispose() {
    _codeController.dispose();
    super.dispose();
  }

  Future<void> _pickImage(ImageSource source) async {
    try {
      final picked = await _picker.pickImage(
        source: source,
        maxWidth: 2048,
        maxHeight: 2048,
        imageQuality: 85,
      );
      if (picked == null) return;

      final bytes = await picked.readAsBytes();
      final filename = picked.name;

      if (!mounted) return;
      Navigator.of(context).pop();
      context.push('/scan-result');

      ref.read(scanProvider.notifier).scanImage(bytes, filename: filename);
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            source == ImageSource.camera
                ? 'Could not open camera. Check permissions in Settings.'
                : 'Could not open gallery. Check permissions in Settings.',
          ),
          behavior: SnackBarBehavior.floating,
        ),
      );
    }
  }

  void _submitCode() {
    final code = _codeController.text.trim();
    if (code.length < 4) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Please enter at least 4 characters.'),
          behavior: SnackBarBehavior.floating,
        ),
      );
      return;
    }

    Navigator.of(context).pop();
    context.push('/scan-result');
    ref.read(scanProvider.notifier).scanCode(code);
  }

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
            _selectedType == null
                ? 'What are you scanning?'
                : _showCodeInput
                    ? 'Enter barcode / QR text'
                    : 'How do you want to scan?',
            style: GoogleFonts.plusJakartaSans(
              fontSize: 22,
              fontWeight: FontWeight.w700,
              color: AppColors.onBackground,
            ),
          ),
          const SizedBox(height: 20),
          if (_selectedType == null)
            _buildTypeSelector()
          else if (_showCodeInput)
            _buildCodeInput()
          else
            _buildInputMethodSelector(),
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
                onTap: () => _pickImage(ImageSource.camera),
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
                onTap: () => _pickImage(ImageSource.gallery),
              ),
            ),
          ],
        ),
        const SizedBox(height: 12),
        _ScanOptionCard(
          icon: LucideIcons.keyboard,
          emoji: '\u2328\uFE0F',
          title: 'Enter Code',
          subtitle: 'Type or paste a barcode / QR / URL',
          isSelected: false,
          onTap: () => setState(() => _showCodeInput = true),
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

  Widget _buildCodeInput() {
    return Column(
      children: [
        Container(
          decoration: BoxDecoration(
            color: AppColors.background,
            borderRadius: WobblyBorders.input,
            border: Border.all(color: AppColors.border, width: 1.5),
          ),
          child: TextField(
            controller: _codeController,
            style: GoogleFonts.plusJakartaSans(fontSize: 16, color: AppColors.onBackground),
            decoration: InputDecoration(
              hintText: 'e.g. https://verify.site.com/XYZ or 8901234567890',
              hintStyle: GoogleFonts.plusJakartaSans(
                fontSize: 14,
                color: AppColors.onBackground.withValues(alpha: 0.4),
              ),
              border: InputBorder.none,
              contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
            ),
            onSubmitted: (_) => _submitCode(),
            textInputAction: TextInputAction.go,
          ),
        ),
        const SizedBox(height: 14),
        SizedBox(
          width: double.infinity,
          height: 48,
          child: ElevatedButton(
            onPressed: _submitCode,
            style: ElevatedButton.styleFrom(
              backgroundColor: AppColors.primary,
              foregroundColor: AppColors.onPrimary,
              shape: RoundedRectangleBorder(borderRadius: WobblyBorders.button),
            ),
            child: Text('Verify Code', style: GoogleFonts.plusJakartaSans(fontWeight: FontWeight.w600, fontSize: 16)),
          ),
        ),
        const SizedBox(height: 12),
        GestureDetector(
          onTap: () => setState(() => _showCodeInput = false),
          child: Text(
            '\u2190 Back to scan options',
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
