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

/// Home screen — hero banner, quick actions, recent scans, recommendations, health tip.
class HomeScreen extends StatelessWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      body: DotGridBackground(
        child: SafeArea(
          child: CustomScrollView(
            slivers: [
              // App bar
              SliverToBoxAdapter(child: _buildAppBar(context)),
              // Hero banner
              SliverToBoxAdapter(child: _buildHeroBanner()),
              // Quick actions
              SliverToBoxAdapter(child: _buildQuickActionsHeader()),
              SliverToBoxAdapter(child: _buildQuickActionsGrid(context)),
              // Recent scans
              SliverToBoxAdapter(child: _buildSectionHeader('Recent Scans')),
              SliverToBoxAdapter(child: _buildRecentScans(context)),
              // Today's recommendations
              SliverToBoxAdapter(child: _buildSectionHeader("Today's Recommendations")),
              SliverToBoxAdapter(child: _buildRecommendations()),
              // Health tip
              SliverToBoxAdapter(child: _buildHealthTip()),
              const SliverToBoxAdapter(child: SizedBox(height: 24)),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildAppBar(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 12, 20, 8),
      child: Row(
        children: [
          // Logo
          Container(
            width: 36,
            height: 36,
            decoration: BoxDecoration(
              color: AppColors.surface,
              shape: BoxShape.circle,
              border: Border.all(color: AppColors.border, width: 2),
            ),
            child: const Icon(LucideIcons.scan, size: 18, color: AppColors.primary),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Text(
              'Good morning, User \uD83D\uDC4B',
              style: GoogleFonts.plusJakartaSans(
                fontSize: 18,
                fontWeight: FontWeight.w700,
                color: AppColors.onBackground,
              ),
            ),
          ),
          GestureDetector(
            child: Container(
              width: 40,
              height: 40,
              decoration: BoxDecoration(
                color: AppColors.surface,
                shape: BoxShape.circle,
                border: Border.all(color: AppColors.border, width: 2),
              ),
              child: const Icon(LucideIcons.bell, size: 18, color: AppColors.onBackground),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildHeroBanner() {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 8),
      child: WobblyCard(
        gradient: AppGradients.primary,
        borderColor: Colors.transparent,
        borderWidth: 0,
        borderRadius: AppBorders.hero,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const SizedBox(height: 8),
            Text(
              'Scan anything.\nKnow everything.',
              style: GoogleFonts.plusJakartaSans(
                fontSize: 24,
                fontWeight: FontWeight.w700,
                color: Colors.white,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              'Tap the scan button below to verify a medicine or check a food label.',
              style: GoogleFonts.plusJakartaSans(
                fontSize: 16,
                color: Colors.white.withValues(alpha: 0.85),
              ),
            ),
            const SizedBox(height: 4),
            Align(
              alignment: Alignment.centerRight,
              child: Icon(
                LucideIcons.search,
                size: 36,
                color: Colors.white.withValues(alpha: 0.4),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildQuickActionsHeader() {
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 16, 20, 8),
      child: Text(
        'Quick Actions',
        style: GoogleFonts.plusJakartaSans(
          fontSize: 20,
          fontWeight: FontWeight.w700,
          color: AppColors.onBackground,
        ),
      ),
    );
  }

  Widget _buildQuickActionsGrid(BuildContext context) {
    final actions = [
      _QuickAction('Medicine\nVerifier', LucideIcons.pill, -1.5, () {}),
      _QuickAction('Food\nScanner', LucideIcons.utensilsCrossed, 1.5, () {}),
      _QuickAction('AI Health\nChat', LucideIcons.messageCircle, 1.5, () => context.push('/ai-chat')),
      _QuickAction('My Health\nProfile', LucideIcons.heartPulse, -1.5, () => context.go('/profile')),
    ];

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 20),
      child: GridView.count(
        crossAxisCount: 2,
        shrinkWrap: true,
        physics: const NeverScrollableScrollPhysics(),
        mainAxisSpacing: 12,
        crossAxisSpacing: 12,
        childAspectRatio: 1.3,
        children: actions.map((a) => _buildActionCard(a)).toList(),
      ),
    );
  }

  Widget _buildActionCard(_QuickAction action) {
    return WobblyCard(
      rotation: action.rotation,
      onTap: action.onTap,
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Container(
            width: 44,
            height: 44,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: AppColors.primary.withValues(alpha: 0.1),
              border: Border.all(color: AppColors.border, width: 1.5),
            ),
            child: Icon(action.icon, size: 22, color: AppColors.primary),
          ),
          const SizedBox(height: 8),
          Text(
            action.title,
            textAlign: TextAlign.center,
            style: GoogleFonts.plusJakartaSans(
              fontSize: 14,
              fontWeight: FontWeight.w700,
              color: AppColors.onBackground,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildSectionHeader(String title) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 20, 20, 8),
      child: Text(
        title,
        style: GoogleFonts.plusJakartaSans(
          fontSize: 20,
          fontWeight: FontWeight.w700,
          color: AppColors.onBackground,
        ),
      ),
    );
  }

  Widget _buildRecentScans(BuildContext context) {
    // Mock data for recent scans
    final scans = [
      _MockScan('Dolo-650', ScanType.medicine, VerdictResult.verified, '2 hours ago'),
      _MockScan('Maggi Noodles', ScanType.food, VerdictResult.caution, 'Yesterday'),
      _MockScan('Crocin Advance', ScanType.medicine, VerdictResult.unverified, '3 days ago'),
    ];

    return SizedBox(
      height: 130,
      child: ListView.builder(
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.symmetric(horizontal: 16),
        itemCount: scans.length,
        itemBuilder: (context, index) {
          final scan = scans[index];
          return Padding(
            padding: const EdgeInsets.symmetric(horizontal: 4),
            child: SizedBox(
              width: 180,
              child: WobblyCard(
                onTap: () => context.push('/scan-result'),
                padding: const EdgeInsets.all(12),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      scan.name,
                      style: GoogleFonts.plusJakartaSans(
                        fontSize: 15,
                        fontWeight: FontWeight.w700,
                        color: AppColors.onBackground,
                      ),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                    const SizedBox(height: 6),
                    ScanTypeBadge(type: scan.type),
                    const Spacer(),
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        _buildMiniResultBadge(scan.result),
                        Text(
                          scan.time,
                          style: GoogleFonts.plusJakartaSans(
                            fontSize: 12,
                            color: AppColors.onBackground.withValues(alpha: 0.5),
                          ),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            ),
          );
        },
      ),
    );
  }

  Widget _buildMiniResultBadge(VerdictResult result) {
    Color color;
    String label;
    switch (result) {
      case VerdictResult.verified:
        color = AppColors.verified;
        label = '\u2713';
        break;
      case VerdictResult.caution:
        color = AppColors.cautionBadge;
        label = '\u26A0';
        break;
      case VerdictResult.unverified:
        color = AppColors.unverified;
        label = '\u2717';
        break;
    }
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.15),
        borderRadius: WobblyBorders.pill,
        border: Border.all(color: color, width: 1.5),
      ),
      child: Text(
        label,
        style: TextStyle(fontSize: 12, color: color, fontWeight: FontWeight.bold),
      ),
    );
  }

  Widget _buildRecommendations() {
    final recs = [
      _MockRec('Oats with Almonds', 'Good for blood sugar control', true),
      _MockRec('Spinach Salad', 'Rich in iron, supports heart health', true),
      _MockRec('Low-fat Yogurt', 'Good source of probiotics', true),
    ];

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 20),
      child: Column(
        children: recs
            .map(
              (r) => Padding(
                padding: const EdgeInsets.only(bottom: 8),
                child: WobblyCard(
                  decoration: CardDecoration.none,
                  padding: const EdgeInsets.all(14),
                  child: Row(
                    children: [
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              r.name,
                              style: GoogleFonts.plusJakartaSans(
                                fontSize: 16,
                                fontWeight: FontWeight.w700,
                                color: AppColors.onBackground,
                              ),
                            ),
                            const SizedBox(height: 4),
                            Text(
                              r.reason,
                              style: GoogleFonts.plusJakartaSans(
                                fontSize: 14,
                                color: AppColors.onBackground.withValues(alpha: 0.6),
                              ),
                            ),
                          ],
                        ),
                      ),
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                        decoration: BoxDecoration(
                          color: AppColors.verified.withValues(alpha: 0.15),
                          borderRadius: WobblyBorders.pill,
                          border: Border.all(color: AppColors.verified, width: 1.5),
                        ),
                        child: Text(
                          'Safe \u2713',
                          style: GoogleFonts.plusJakartaSans(
                            fontSize: 12,
                            color: AppColors.verified,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            )
            .toList(),
      ),
    );
  }

  Widget _buildHealthTip() {
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 12, 20, 0),
      child: WobblyCard(
          backgroundColor: AppColors.warning.withValues(alpha: 0.08),
          borderColor: AppColors.warning.withValues(alpha: 0.2),
          padding: const EdgeInsets.all(16),
          child: Row(
            children: [
              const Icon(LucideIcons.lightbulb, size: 28, color: AppColors.cautionBadge),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Health Tip of the Day',
                      style: GoogleFonts.plusJakartaSans(
                        fontSize: 16,
                        fontWeight: FontWeight.w700,
                        color: AppColors.onBackground,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      'Drinking water 30 minutes before meals can help with digestion and nutrient absorption.',
                      style: GoogleFonts.plusJakartaSans(
                        fontSize: 14,
                        color: AppColors.onBackground.withValues(alpha: 0.7),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
    );
  }
}

class _QuickAction {
  final String title;
  final IconData icon;
  final double rotation;
  final VoidCallback onTap;
  _QuickAction(this.title, this.icon, this.rotation, this.onTap);
}

class _MockScan {
  final String name;
  final ScanType type;
  final VerdictResult result;
  final String time;
  _MockScan(this.name, this.type, this.result, this.time);
}

class _MockRec {
  final String name;
  final String reason;
  final bool isSafe;
  _MockRec(this.name, this.reason, this.isSafe);
}
