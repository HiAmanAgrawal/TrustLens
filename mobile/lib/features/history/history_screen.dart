import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:lucide_icons/lucide_icons.dart';

import '../../theme/app_theme.dart';
import '../../theme/wobbly_borders.dart';
import '../../widgets/dot_grid_background.dart';
import '../../widgets/result_badge.dart';
import '../../widgets/scan_type_badge.dart';
import '../../widgets/wobbly_card.dart';

/// History screen — chronological scan cards with filter bar.
class HistoryScreen extends StatefulWidget {
  const HistoryScreen({super.key});

  @override
  State<HistoryScreen> createState() => _HistoryScreenState();
}

class _HistoryScreenState extends State<HistoryScreen> {
  String _activeFilter = 'All';

  final _filters = ['All', 'Medicine', 'Food', 'Verified', 'Flagged'];

  // Mock data
  final _scans = [
    _ScanItem('Dolo-650', ScanType.medicine, VerdictResult.verified, 'Apr 27, 2026'),
    _ScanItem('Maggi Noodles', ScanType.food, VerdictResult.caution, 'Apr 26, 2026'),
    _ScanItem('Crocin Advance', ScanType.medicine, VerdictResult.unverified, 'Apr 24, 2026'),
    _ScanItem('Amul Butter', ScanType.food, VerdictResult.verified, 'Apr 23, 2026'),
    _ScanItem('Paracetamol IP', ScanType.medicine, VerdictResult.verified, 'Apr 22, 2026'),
  ];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      body: DotGridBackground(
        child: SafeArea(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // App bar
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
              // Filter bar
              _buildFilterBar(),
              const SizedBox(height: 8),
              // Scan list
              Expanded(
                child: _scans.isEmpty ? _buildEmptyState() : _buildScanList(),
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

  Widget _buildScanList() {
    return ListView.builder(
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 8),
      itemCount: _scans.length,
      itemBuilder: (context, index) {
        final scan = _scans[index];
        return Padding(
          padding: const EdgeInsets.only(bottom: 12),
          child: WobblyCard(
            onTap: () => context.push('/scan-result'),
            padding: const EdgeInsets.all(14),
            child: Row(
              children: [
                // Thumbnail placeholder
                Container(
                  width: 52,
                  height: 52,
                  decoration: BoxDecoration(
                    color: AppColors.muted.withValues(alpha: 0.5),
                    borderRadius: WobblyBorders.button,
                    border: Border.all(color: AppColors.border, width: 1.5),
                  ),
                  child: Icon(
                    scan.type == ScanType.medicine
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
                        scan.name,
                        style: GoogleFonts.plusJakartaSans(
                          fontSize: 16,
                          fontWeight: FontWeight.w700,
                          color: AppColors.onBackground,
                        ),
                      ),
                      const SizedBox(height: 4),
                      Row(
                        children: [
                          ScanTypeBadge(type: scan.type),
                          const SizedBox(width: 8),
                          Text(
                            scan.date,
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
                _buildMiniResult(scan.result),
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

class _ScanItem {
  final String name;
  final ScanType type;
  final VerdictResult result;
  final String date;
  _ScanItem(this.name, this.type, this.result, this.date);
}
