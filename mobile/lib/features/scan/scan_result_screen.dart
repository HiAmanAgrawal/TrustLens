import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:lucide_icons/lucide_icons.dart';

import '../../models/scan_result.dart';
import '../../providers/scan_provider.dart';
import '../../theme/app_theme.dart';
import '../../theme/wobbly_borders.dart';
import '../../widgets/dot_grid_background.dart';
import '../../widgets/result_badge.dart';
import '../../widgets/scan_type_badge.dart';
import '../../widgets/wobbly_button.dart';
import '../../widgets/wobbly_card.dart';

/// Scan result screen — displays the verdict, product details,
/// evidence, notes, and grocery analysis from the real backend.
class ScanResultScreen extends ConsumerStatefulWidget {
  const ScanResultScreen({super.key});

  @override
  ConsumerState<ScanResultScreen> createState() => _ScanResultScreenState();
}

class _ScanResultScreenState extends ConsumerState<ScanResultScreen> {
  bool _aiExplanationExpanded = false;

  @override
  Widget build(BuildContext context) {
    final scanState = ref.watch(scanProvider);

    return Scaffold(
      backgroundColor: AppColors.background,
      body: DotGridBackground(
        child: SafeArea(
          child: Column(
            children: [
              _buildAppBar(context),
              Expanded(
                child: scanState.isScanning
                    ? _buildLoadingState()
                    : scanState.error != null
                        ? _buildErrorState(scanState.error!)
                        : scanState.result != null
                            ? _buildResultContent(scanState.result!)
                            : _buildEmptyState(),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildLoadingState() {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const SizedBox(
            width: 48,
            height: 48,
            child: CircularProgressIndicator(color: AppColors.primary, strokeWidth: 3),
          ),
          const SizedBox(height: 24),
          Text(
            'Analyzing your scan...',
            style: GoogleFonts.plusJakartaSans(
              fontSize: 18,
              fontWeight: FontWeight.w600,
              color: AppColors.onBackground,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            'Decoding barcode, reading label, checking manufacturer...',
            style: GoogleFonts.plusJakartaSans(
              fontSize: 14,
              color: AppColors.onBackground.withValues(alpha: 0.5),
            ),
            textAlign: TextAlign.center,
          ),
        ],
      ),
    );
  }

  Widget _buildErrorState(String error) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(LucideIcons.alertTriangle, size: 48, color: AppColors.unverified.withValues(alpha: 0.7)),
            const SizedBox(height: 16),
            Text(
              'Scan Failed',
              style: GoogleFonts.plusJakartaSans(
                fontSize: 20,
                fontWeight: FontWeight.w700,
                color: AppColors.onBackground,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              error,
              style: GoogleFonts.plusJakartaSans(
                fontSize: 15,
                color: AppColors.onBackground.withValues(alpha: 0.6),
                height: 1.4,
              ),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 24),
            WobblyButton(
              label: 'Go Back',
              onTap: () => context.pop(),
              width: 200,
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildEmptyState() {
    return Center(
      child: Text(
        'No scan data yet.',
        style: GoogleFonts.plusJakartaSans(fontSize: 16, color: AppColors.onBackground.withValues(alpha: 0.5)),
      ),
    );
  }

  Widget _buildResultContent(ScanResult result) {
    final verdictResult = _mapVerdict(result.verdict);
    final isGrocery = result.isFood;

    return ListView(
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 8),
      children: [
        // Result badge
        Center(child: ResultBadge(result: verdictResult)),
        const SizedBox(height: 8),
        // Confidence score
        Center(
          child: Text(
            'Confidence: ${result.score}/10',
            style: GoogleFonts.plusJakartaSans(
              fontSize: 15,
              color: AppColors.onBackground.withValues(alpha: 0.5),
            ),
          ),
        ),
        const SizedBox(height: 4),
        // Status message
        Center(
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: Text(
              result.message,
              style: GoogleFonts.plusJakartaSans(
                fontSize: 14,
                color: AppColors.onBackground.withValues(alpha: 0.6),
              ),
              textAlign: TextAlign.center,
            ),
          ),
        ),
        const SizedBox(height: 16),
        // Product details card
        _buildProductDetails(result, isGrocery),
        const SizedBox(height: 12),
        // Evidence / comparison card (pharma)
        if (result.evidence.isNotEmpty) ...[
          _buildEvidenceCard(result),
          const SizedBox(height: 12),
        ],
        // Grocery findings
        if (isGrocery && result.grocery != null) ...[
          _buildGroceryFindings(result.grocery!),
          const SizedBox(height: 12),
        ],
        // Notes timeline
        if (result.notes.isNotEmpty) ...[
          _buildNotesTimeline(result.notes),
          const SizedBox(height: 12),
        ],
        // Summary / AI explanation
        _buildSummaryCard(result),
        const SizedBox(height: 16),
        // CTA buttons
        WobblyButton(
          label: 'Ask AI a Question \u2192',
          onTap: () => context.push('/ai-chat'),
          width: double.infinity,
        ),
        const SizedBox(height: 12),
        WobblyButton(
          label: 'Scan Another',
          variant: WobblyButtonVariant.secondary,
          icon: LucideIcons.scanLine,
          onTap: () => context.pop(),
          width: double.infinity,
        ),
        const SizedBox(height: 24),
      ],
    );
  }

  VerdictResult _mapVerdict(String verdict) {
    switch (verdict) {
      case 'safe':
        return VerdictResult.verified;
      case 'caution':
        return VerdictResult.caution;
      case 'high_risk':
        return VerdictResult.unverified;
      default:
        return VerdictResult.caution;
    }
  }

  Widget _buildProductDetails(ScanResult result, bool isGrocery) {
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
              ScanTypeBadge(type: isGrocery ? ScanType.food : ScanType.medicine),
            ],
          ),
          const SizedBox(height: 12),
          _detailRow('Name', result.productName),
          _detailRow('Manufacturer', result.manufacturer),
          if (result.batchNumber != 'N/A') _detailRow('Batch No.', result.batchNumber),
          if (result.expiryDate != 'N/A') _detailRow('Expiry', result.expiryDate),
          if (result.barcode != null) _detailRow('Barcode Type', result.barcode!.symbology),
          if (result.ocr != null)
            _detailRow('OCR Engine', '${result.ocr!.engine} (${(result.ocr!.confidence * 100).toStringAsFixed(0)}%)'),
          if (isGrocery && result.grocery != null) ...[
            if (result.grocery!.ingredientsCount != null)
              _detailRow('Ingredients', '${result.grocery!.ingredientsCount} items'),
            for (final entry in result.grocery!.dates.entries) _detailRow(entry.key.toUpperCase(), entry.value),
          ],
        ],
      ),
    );
  }

  Widget _buildEvidenceCard(ScanResult result) {
    return WobblyCard(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(LucideIcons.gitCompare, size: 18, color: AppColors.secondary),
              const SizedBox(width: 8),
              Text(
                'Comparison Evidence',
                style: GoogleFonts.plusJakartaSans(fontSize: 18, fontWeight: FontWeight.w700, color: AppColors.onBackground),
              ),
            ],
          ),
          const SizedBox(height: 12),
          for (final e in result.evidence) _evidenceRow(e),
        ],
      ),
    );
  }

  Widget _evidenceRow(String evidence) {
    final isMatch = evidence.contains('100%');
    final isPartial = evidence.contains('%') && !isMatch;
    final color = isMatch
        ? AppColors.verified
        : isPartial
            ? AppColors.cautionBadge
            : AppColors.onBackground.withValues(alpha: 0.7);
    final icon = isMatch ? LucideIcons.checkCircle2 : (isPartial ? LucideIcons.alertCircle : LucideIcons.minus);

    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, size: 16, color: color),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              evidence,
              style: GoogleFonts.plusJakartaSans(fontSize: 14, color: AppColors.onBackground.withValues(alpha: 0.8), height: 1.3),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildGroceryFindings(GroceryAnalysis grocery) {
    return WobblyCard(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(LucideIcons.clipboardList, size: 18, color: AppColors.secondary),
              const SizedBox(width: 8),
              Text(
                'Label Analysis',
                style: GoogleFonts.plusJakartaSans(fontSize: 18, fontWeight: FontWeight.w700, color: AppColors.onBackground),
              ),
              const Spacer(),
              _riskBandChip(grocery.riskBand),
            ],
          ),
          const SizedBox(height: 12),
          for (final finding in grocery.findings) _findingRow(finding),
        ],
      ),
    );
  }

  Widget _riskBandChip(String band) {
    Color bg;
    Color fg;
    switch (band) {
      case 'high':
        bg = AppColors.unverified.withValues(alpha: 0.12);
        fg = AppColors.unverified;
        break;
      case 'medium':
        bg = AppColors.cautionBadge.withValues(alpha: 0.12);
        fg = AppColors.cautionBadge;
        break;
      case 'low':
        bg = AppColors.verified.withValues(alpha: 0.12);
        fg = AppColors.verified;
        break;
      default:
        bg = AppColors.muted.withValues(alpha: 0.3);
        fg = AppColors.onBackground;
    }
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(color: bg, borderRadius: WobblyBorders.pill),
      child: Text(
        band.toUpperCase(),
        style: GoogleFonts.plusJakartaSans(fontSize: 12, fontWeight: FontWeight.w700, color: fg),
      ),
    );
  }

  Widget _findingRow(Finding finding) {
    final color = finding.severity == 'error'
        ? AppColors.unverified
        : finding.severity == 'warning'
            ? AppColors.cautionBadge
            : AppColors.verified;
    final icon = finding.severity == 'error'
        ? LucideIcons.xCircle
        : finding.severity == 'warning'
            ? LucideIcons.alertTriangle
            : LucideIcons.info;
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, size: 16, color: color),
          const SizedBox(width: 8),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  finding.message,
                  style: GoogleFonts.plusJakartaSans(fontSize: 14, color: AppColors.onBackground, height: 1.3),
                ),
                if (finding.evidence != null)
                  Padding(
                    padding: const EdgeInsets.only(top: 2),
                    child: Text(
                      finding.evidence!,
                      style: GoogleFonts.plusJakartaSans(fontSize: 12, color: AppColors.onBackground.withValues(alpha: 0.5)),
                    ),
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildNotesTimeline(List<Note> notes) {
    return WobblyCard(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(LucideIcons.list, size: 18, color: AppColors.secondary),
              const SizedBox(width: 8),
              Text(
                'Pipeline Steps',
                style: GoogleFonts.plusJakartaSans(fontSize: 18, fontWeight: FontWeight.w700, color: AppColors.onBackground),
              ),
            ],
          ),
          const SizedBox(height: 12),
          for (final note in notes) _noteRow(note),
        ],
      ),
    );
  }

  Widget _noteRow(Note note) {
    Color color;
    IconData icon;
    switch (note.severity) {
      case 'error':
        color = AppColors.unverified;
        icon = LucideIcons.xCircle;
        break;
      case 'warning':
        color = AppColors.cautionBadge;
        icon = LucideIcons.alertCircle;
        break;
      default:
        color = AppColors.verified;
        icon = LucideIcons.checkCircle2;
    }
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, size: 14, color: color),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              note.message,
              style: GoogleFonts.plusJakartaSans(fontSize: 13, color: AppColors.onBackground.withValues(alpha: 0.7), height: 1.3),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildSummaryCard(ScanResult result) {
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
                    'Summary',
                    style: GoogleFonts.plusJakartaSans(fontSize: 18, fontWeight: FontWeight.w700, color: AppColors.onBackground),
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
              result.summary,
              style: GoogleFonts.plusJakartaSans(
                fontSize: 15,
                color: AppColors.onBackground.withValues(alpha: 0.7),
                height: 1.4,
              ),
            ),
            if (result.ocr != null && result.ocr!.text.isNotEmpty) ...[
              const SizedBox(height: 12),
              Text(
                'Extracted label text:',
                style: GoogleFonts.plusJakartaSans(fontSize: 13, fontWeight: FontWeight.w600, color: AppColors.onBackground.withValues(alpha: 0.6)),
              ),
              const SizedBox(height: 4),
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  color: AppColors.muted.withValues(alpha: 0.2),
                  borderRadius: WobblyBorders.standard,
                ),
                child: Text(
                  result.ocr!.text,
                  style: GoogleFonts.plusJakartaSans(fontSize: 12, color: AppColors.onBackground.withValues(alpha: 0.6), height: 1.3),
                ),
              ),
            ],
          ],
        ],
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
}
