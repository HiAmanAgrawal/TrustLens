import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:lucide_icons/lucide_icons.dart';

import '../../theme/app_theme.dart';
import '../../theme/wobbly_borders.dart';
import '../../widgets/dot_grid_background.dart';
import '../../widgets/health_compatibility_card.dart';
import '../../widgets/result_badge.dart';
import '../../widgets/scan_type_badge.dart';
import '../../widgets/wobbly_button.dart';
import '../../widgets/wobbly_card.dart';

/// Scan result screen — displays the verdict, product details,
/// health compatibility, and AI explanation.
class ScanResultScreen extends StatefulWidget {
  const ScanResultScreen({super.key});

  @override
  State<ScanResultScreen> createState() => _ScanResultScreenState();
}

class _ScanResultScreenState extends State<ScanResultScreen> {
  bool _aiExplanationExpanded = false;
  bool _saved = false;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      body: DotGridBackground(
        child: SafeArea(
          child: Column(
            children: [
              // App bar
              _buildAppBar(context),
              // Content
              Expanded(
                child: ListView(
                  padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 8),
                  children: [
                    // Product image placeholder
                    _buildProductImage(),
                    const SizedBox(height: 16),
                    // Result badge
                    Center(child: ResultBadge(result: VerdictResult.verified)),
                    const SizedBox(height: 8),
                    // Confidence score
                    Center(
                      child: Text(
                        'Confidence: 8.5/10',
                        style: GoogleFonts.plusJakartaSans(
                          fontSize: 15,
                          color: AppColors.onBackground.withValues(alpha: 0.5),
                        ),
                      ),
                    ),
                    const SizedBox(height: 16),
                    // Product details card
                    _buildProductDetails(),
                    const SizedBox(height: 12),
                    // Health compatibility
                    HealthCompatibilityCard(
                      compatibilityScore: 0.85,
                      flags: const [
                        HealthFlag(
                          ingredient: 'Paracetamol',
                          reason: 'Compatible with your profile',
                          severity: FlagSeverity.low,
                        ),
                        HealthFlag(
                          ingredient: 'Caffeine',
                          reason: 'May interact with hypertension medication',
                          severity: FlagSeverity.medium,
                        ),
                      ],
                    ),
                    const SizedBox(height: 12),
                    // AI Explanation
                    _buildAiExplanation(),
                    const SizedBox(height: 16),
                    // CTA buttons
                    WobblyButton(
                      label: 'Ask AI a Question \u2192',
                      onTap: () => context.push('/ai-chat'),
                      width: double.infinity,
                    ),
                    const SizedBox(height: 12),
                    WobblyButton(
                      label: _saved ? 'Saved to History \u2713' : 'Save to History',
                      variant: WobblyButtonVariant.secondary,
                      icon: _saved ? LucideIcons.check : LucideIcons.bookmark,
                      onTap: _saved
                          ? null
                          : () => setState(() => _saved = true),
                      width: double.infinity,
                    ),
                    const SizedBox(height: 24),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildAppBar(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(8, 8, 20, 0),
      child: Row(
        children: [
          IconButton(
            onPressed: () => context.pop(),
            icon: const Icon(LucideIcons.arrowLeft, color: AppColors.onBackground),
            tooltip: 'Go back',
          ),
          Text(
            'Scan Result',
            style: GoogleFonts.plusJakartaSans(
              fontSize: 22,
              fontWeight: FontWeight.w700,
              color: AppColors.onBackground,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildProductImage() {
    return WobblyCard(
      rotation: 1.0,
      padding: const EdgeInsets.all(8),
      child: Container(
        height: 180,
        decoration: BoxDecoration(
          color: AppColors.muted.withValues(alpha: 0.3),
          borderRadius: WobblyBorders.standard,
        ),
        child: Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(
                LucideIcons.image,
                size: 48,
                color: AppColors.onBackground.withValues(alpha: 0.3),
              ),
              const SizedBox(height: 8),
              Text(
                'Product Image',
                style: GoogleFonts.plusJakartaSans(
                  fontSize: 16,
                  color: AppColors.onBackground.withValues(alpha: 0.4),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildProductDetails() {
    return WobblyCard(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(LucideIcons.fileText, size: 18, color: AppColors.secondary),
              const SizedBox(width: 8),
              Text(
                'Product Details',
                style: GoogleFonts.plusJakartaSans(
                  fontSize: 18,
                  fontWeight: FontWeight.w700,
                  color: AppColors.onBackground,
                ),
              ),
              const Spacer(),
              const ScanTypeBadge(type: ScanType.medicine),
            ],
          ),
          const SizedBox(height: 12),
          _detailRow('Name', 'Dolo-650'),
          _detailRow('Manufacturer', 'Micro Labs Limited'),
          _detailRow('Batch No.', 'DOBS3975'),
          _detailRow('Expiry', 'MAR 2027'),
          _detailRow('Active Ingredient', 'Paracetamol 650mg'),
        ],
      ),
    );
  }

  Widget _detailRow(String label, String value) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 130,
            child: Text(
              label,
              style: GoogleFonts.plusJakartaSans(
                fontSize: 15,
                color: AppColors.onBackground.withValues(alpha: 0.5),
              ),
            ),
          ),
          Expanded(
            child: Text(
              value,
              style: GoogleFonts.plusJakartaSans(
                fontSize: 15,
                color: AppColors.onBackground,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildAiExplanation() {
    return WobblyCard(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          GestureDetector(
            onTap: () => setState(() => _aiExplanationExpanded = !_aiExplanationExpanded),
            behavior: HitTestBehavior.opaque,
            child: Row(
              children: [
                const Icon(LucideIcons.sparkles, size: 18, color: AppColors.secondary),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    'What does this mean?',
                    style: GoogleFonts.plusJakartaSans(
                      fontSize: 18,
                      fontWeight: FontWeight.w700,
                      color: AppColors.onBackground,
                    ),
                  ),
                ),
                Icon(
                  _aiExplanationExpanded ? LucideIcons.chevronUp : LucideIcons.chevronDown,
                  size: 20,
                  color: AppColors.onBackground,
                ),
              ],
            ),
          ),
          if (_aiExplanationExpanded) ...[
            const SizedBox(height: 12),
            Text(
              'This medicine has been verified against the manufacturer\'s database. '
              'The batch number, manufacturing date, and expiry date on your pack match '
              'the official records from Micro Labs Limited. The label text and the '
              'manufacturer portal information show an 85% match, which is within the '
              'safe threshold.\n\n'
              'The caffeine content in this formulation may interact mildly with your '
              'hypertension medication. Consider consulting your doctor if you take this regularly.',
              style: GoogleFonts.plusJakartaSans(
                fontSize: 15,
                color: AppColors.onBackground.withValues(alpha: 0.7),
                height: 1.4,
              ),
            ),
            const SizedBox(height: 8),
            Container(
              padding: const EdgeInsets.all(10),
              decoration: BoxDecoration(
                color: AppColors.cautionBadge.withValues(alpha: 0.08),
                borderRadius: WobblyBorders.pill,
                border: Border.all(
                  color: AppColors.cautionBadge.withValues(alpha: 0.3),
                ),
              ),
              child: Row(
                children: [
                  const Icon(LucideIcons.info, size: 14, color: AppColors.cautionBadge),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      'This is not medical advice. Consult a qualified healthcare provider for medical decisions.',
                      style: GoogleFonts.plusJakartaSans(
                        fontSize: 12,
                        color: AppColors.cautionBadge,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ],
      ),
    );
  }
}
