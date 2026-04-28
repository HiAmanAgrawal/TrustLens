import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:intl/intl.dart';
import 'package:lucide_icons/lucide_icons.dart';

import '../../models/scan_result.dart';
import '../../providers/history_provider.dart';
import '../../providers/scan_provider.dart';
import '../../theme/app_theme.dart';
import '../../theme/wobbly_borders.dart';
import '../../widgets/dot_grid_background.dart';
import '../../widgets/result_badge.dart';
import '../../widgets/scan_type_badge.dart';
import '../../widgets/wobbly_card.dart';

/// History screen — chronological scan cards with filter bar.
/// Reads from historyProvider which is populated by real scans.
class HistoryScreen extends ConsumerStatefulWidget {
  const HistoryScreen({super.key});

  @override
  ConsumerState<HistoryScreen> createState() => _HistoryScreenState();
}

class _HistoryScreenState extends ConsumerState<HistoryScreen> {
  String _activeFilter = 'All';

  final _filters = ['All', 'Medicine', 'Food', 'Verified', 'Flagged'];

  @override
  Widget build(BuildContext context) {
    // Watch the provider to rebuild on changes.
    ref.watch(historyProvider);
    final filteredScans = ref.read(historyProvider.notifier).filterByType(_activeFilter);

    return Scaffold(
      backgroundColor: AppColors.background,
      body: DotGridBackground(
        child: SafeArea(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(20, 16, 20, 8),
                child: Text(
                  'Scan History',
                  style: GoogleFonts.plusJakartaSans(
                    fontSize: 28,
                    fontWeight: FontWeight.w700,
                    color: AppColors.onBackground,
                  ),
                ),
              ),
              _buildFilterBar(),
              const SizedBox(height: 8),
              Expanded(
                child: filteredScans.isEmpty ? _buildEmptyState() : _buildScanList(filteredScans),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildFilterBar() {
    return SizedBox(
      height: 42,
      child: ListView.builder(
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.symmetric(horizontal: 16),
        itemCount: _filters.length,
        itemBuilder: (context, index) {
          final filter = _filters[index];
          final isActive = filter == _activeFilter;
          return Padding(
            padding: const EdgeInsets.symmetric(horizontal: 4),
            child: GestureDetector(
              onTap: () => setState(() => _activeFilter = filter),
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                decoration: BoxDecoration(
                  color: isActive ? AppColors.primary : AppColors.surface,
                  borderRadius: WobblyBorders.pill,
                  border: Border.all(
                    color: isActive ? AppColors.primary : AppColors.border,
                    width: 2,
                  ),
                ),
                child: Text(
                  filter,
                  style: GoogleFonts.plusJakartaSans(
                    fontSize: 14,
                    color: isActive ? AppColors.onPrimary : AppColors.onBackground,
                  ),
                ),
              ),
            ),
          );
        },
      ),
    );
  }

  Widget _buildScanList(List<ScanResult> scans) {
    final dateFmt = DateFormat('MMM d, yyyy');

    return ListView.builder(
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 8),
      itemCount: scans.length,
      itemBuilder: (context, index) {
        final scan = scans[index];
        final scanType = scan.isFood ? ScanType.food : ScanType.medicine;
        final verdict = scan.verdict == 'safe'
            ? VerdictResult.verified
            : scan.verdict == 'caution'
                ? VerdictResult.caution
                : VerdictResult.unverified;
        final dateStr = dateFmt.format(scan.scannedAt);

        return Padding(
          padding: const EdgeInsets.only(bottom: 12),
          child: WobblyCard(
            onTap: () {
              ref.read(scanProvider.notifier).restoreResult(scan);
              context.push('/scan-result');
            },
            padding: const EdgeInsets.all(14),
            child: Row(
              children: [
                Container(
                  width: 52,
                  height: 52,
                  decoration: BoxDecoration(
                    color: AppColors.muted.withValues(alpha: 0.5),
                    borderRadius: WobblyBorders.button,
                    border: Border.all(color: AppColors.border, width: 1.5),
                  ),
                  child: Icon(
                    scanType == ScanType.medicine
                        ? LucideIcons.pill
                        : LucideIcons.utensilsCrossed,
                    size: 22,
                    color: AppColors.onBackground.withValues(alpha: 0.5),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        scan.productName,
                        style: GoogleFonts.plusJakartaSans(
                          fontSize: 16,
                          fontWeight: FontWeight.w700,
                          color: AppColors.onBackground,
                        ),
                      ),
                      const SizedBox(height: 4),
                      Row(
                        children: [
                          ScanTypeBadge(type: scanType),
                          const SizedBox(width: 8),
                          Text(
                            dateStr,
                            style: GoogleFonts.plusJakartaSans(
                              fontSize: 13,
                              color: AppColors.onBackground.withValues(alpha: 0.5),
                            ),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
                _buildMiniResult(verdict),
              ],
            ),
          ),
        );
      },
    );
  }

  Widget _buildMiniResult(VerdictResult result) {
    Color color;
    String icon;
    switch (result) {
      case VerdictResult.verified:
        color = AppColors.verified;
        icon = '\u2713';
        break;
      case VerdictResult.caution:
        color = AppColors.cautionBadge;
        icon = '\u26A0';
        break;
      case VerdictResult.unverified:
        color = AppColors.unverified;
        icon = '\u2717';
        break;
    }
    return Container(
      width: 32,
      height: 32,
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.15),
        shape: BoxShape.circle,
        border: Border.all(color: color, width: 2),
      ),
      child: Center(
        child: Text(
          icon,
          style: TextStyle(
            fontSize: 16,
            color: color,
            fontWeight: FontWeight.bold,
          ),
        ),
      ),
    );
  }

  Widget _buildEmptyState() {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            LucideIcons.edit,
            size: 64,
            color: AppColors.onBackground.withValues(alpha: 0.2),
          ),
          const SizedBox(height: 16),
          Text(
            'No scans yet.',
            style: GoogleFonts.plusJakartaSans(
              fontSize: 22,
              fontWeight: FontWeight.w700,
              color: AppColors.onBackground.withValues(alpha: 0.4),
            ),
          ),
          const SizedBox(height: 8),
          Text(
            'Tap the scan button to get started!',
            style: GoogleFonts.plusJakartaSans(
              fontSize: 16,
              color: AppColors.onBackground.withValues(alpha: 0.4),
            ),
          ),
        ],
      ),
    );
  }
}

