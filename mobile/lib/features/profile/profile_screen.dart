import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:lucide_icons/lucide_icons.dart';

import '../../app.dart';
import '../../providers/service_providers.dart';
import '../../theme/app_theme.dart';
import '../../theme/wobbly_borders.dart';
import '../../widgets/dot_grid_background.dart';
import '../../widgets/wobbly_button.dart';
import '../../widgets/wobbly_card.dart';

/// Health profile screen — displays and edits collected health data
/// in organized, editable wobbly section cards.
class ProfileScreen extends ConsumerStatefulWidget {
  const ProfileScreen({super.key});

  @override
  ConsumerState<ProfileScreen> createState() => _ProfileScreenState();
}

class _ProfileScreenState extends ConsumerState<ProfileScreen> {
  // Mock profile data
  final _profile = {
    'name': 'User',
    'email': 'user@example.com',
    'age': '26-35',
    'sex': 'Male',
    'conditions': ['Diabetes', 'Hypertension'],
    'diet': ['Vegetarian', 'Low-Sodium'],
    'medications': 'Metformin 500mg',
  };

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      body: DotGridBackground(
        child: SafeArea(
          child: ListView(
            padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
            children: [
              // Header
              Text(
                'Health Profile',
                style: GoogleFonts.plusJakartaSans(
                  fontSize: 28,
                  fontWeight: FontWeight.w700,
                  color: AppColors.onBackground,
                ),
              ),
              const SizedBox(height: 4),
              // Privacy badge
              _buildPrivacyBadge(),
              const SizedBox(height: 20),
              // Avatar + name
              _buildProfileHeader(),
              const SizedBox(height: 20),
              // Personal Info section
              _buildSection(
                title: 'Personal Info',
                icon: LucideIcons.user,
                children: [
                  _buildInfoRow('Age Range', _profile['age'] as String),
                  _buildInfoRow('Biological Sex', _profile['sex'] as String),
                ],
              ),
              const SizedBox(height: 12),
              // Health Conditions section
              _buildSection(
                title: 'Health Conditions',
                icon: LucideIcons.heartPulse,
                children: [
                  _buildChipList(_profile['conditions'] as List<String>),
                ],
              ),
              const SizedBox(height: 12),
              // Dietary Preferences section
              _buildSection(
                title: 'Dietary Preferences',
                icon: LucideIcons.salad,
                children: [
                  _buildChipList(_profile['diet'] as List<String>),
                ],
              ),
              const SizedBox(height: 12),
              // Medications section
              _buildSection(
                title: 'Current Medications',
                icon: LucideIcons.pill,
                children: [
                  Text(
                    _profile['medications'] as String,
                    style: GoogleFonts.plusJakartaSans(
                      fontSize: 15,
                      color: AppColors.onBackground.withValues(alpha: 0.7),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              // Backend URL config
              _buildBackendUrlSection(),
              const SizedBox(height: 12),
              // Dark mode toggle
              _buildDarkModeToggle(),
              const SizedBox(height: 24),
              // Sign out
              Center(
                child: WobblyButton(
                  label: 'Sign Out',
                  variant: WobblyButtonVariant.secondary,
                  icon: LucideIcons.logOut,
                  onTap: () {
                    // TODO: Wire to auth in Phase 3
                  },
                ),
              ),
              const SizedBox(height: 24),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildPrivacyBadge() {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      decoration: BoxDecoration(
        color: AppColors.secondary.withValues(alpha: 0.08),
        borderRadius: WobblyBorders.pill,
        border: Border.all(color: AppColors.secondary, width: 1.5),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Icon(LucideIcons.lock, size: 14, color: AppColors.secondary),
          const SizedBox(width: 6),
          Text(
            'Your data is stored encrypted and never sold.',
            style: GoogleFonts.plusJakartaSans(
              fontSize: 13,
              color: AppColors.secondary,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildProfileHeader() {
    return Row(
      children: [
        Container(
          width: 60,
          height: 60,
          decoration: BoxDecoration(
            color: AppColors.primary.withValues(alpha: 0.12),
            shape: BoxShape.circle,
            border: Border.all(color: AppColors.border, width: 2),
          ),
          child: Center(
            child: Text(
              (_profile['name'] as String).substring(0, 1).toUpperCase(),
              style: GoogleFonts.plusJakartaSans(
                fontSize: 28,
                fontWeight: FontWeight.w700,
                color: AppColors.primary,
              ),
            ),
          ),
        ),
        const SizedBox(width: 16),
        Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              _profile['name'] as String,
              style: GoogleFonts.plusJakartaSans(
                fontSize: 22,
                fontWeight: FontWeight.w700,
                color: AppColors.onBackground,
              ),
            ),
            Text(
              _profile['email'] as String,
              style: GoogleFonts.plusJakartaSans(
                fontSize: 15,
                color: AppColors.onBackground.withValues(alpha: 0.5),
              ),
            ),
          ],
        ),
      ],
    );
  }

  Widget _buildSection({
    required String title,
    required IconData icon,
    required List<Widget> children,
  }) {
    return WobblyCard(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(icon, size: 18, color: AppColors.secondary),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  title,
                  style: GoogleFonts.plusJakartaSans(
                    fontSize: 18,
                    fontWeight: FontWeight.w700,
                    color: AppColors.onBackground,
                  ),
                ),
              ),
              GestureDetector(
                onTap: () {
                  // TODO: Inline edit mode in Phase 3
                },
                child: Container(
                  padding: const EdgeInsets.all(6),
                  decoration: BoxDecoration(
                    color: AppColors.muted.withValues(alpha: 0.5),
                    shape: BoxShape.circle,
                  ),
                  child: const Icon(LucideIcons.pencil, size: 14, color: AppColors.onBackground),
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          ...children,
        ],
      ),
    );
  }

  Widget _buildInfoRow(String label, String value) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(
        children: [
          SizedBox(
            width: 120,
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

  Widget _buildDarkModeToggle() {
    final isDark = ref.watch(themeModeProvider) == ThemeMode.dark;

    return WobblyCard(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      child: Row(
        children: [
          Icon(
            isDark ? LucideIcons.moon : LucideIcons.sun,
            size: 20,
            color: AppColors.primary,
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Text(
              'Dark Mode',
              style: GoogleFonts.plusJakartaSans(
                fontSize: 16,
                fontWeight: FontWeight.w600,
                color: AppColors.onBackground,
              ),
            ),
          ),
          Switch.adaptive(
            value: isDark,
            activeColor: AppColors.primary,
            onChanged: (value) {
              ref.read(themeModeProvider.notifier).state =
                  value ? ThemeMode.dark : ThemeMode.light;
            },
          ),
        ],
      ),
    );
  }

  Widget _buildBackendUrlSection() {
    final currentUrl = ref.watch(baseUrlProvider);

    return WobblyCard(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(LucideIcons.server, size: 18, color: AppColors.secondary),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  'Backend Server',
                  style: GoogleFonts.plusJakartaSans(
                    fontSize: 18,
                    fontWeight: FontWeight.w700,
                    color: AppColors.onBackground,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            'Set the backend URL (e.g. ngrok URL for local dev).',
            style: GoogleFonts.plusJakartaSans(
              fontSize: 13,
              color: AppColors.onBackground.withValues(alpha: 0.5),
            ),
          ),
          const SizedBox(height: 12),
          Container(
            decoration: BoxDecoration(
              color: AppColors.background,
              borderRadius: WobblyBorders.input,
              border: Border.all(color: AppColors.border, width: 1.5),
            ),
            child: TextField(
              controller: TextEditingController(text: currentUrl),
              style: GoogleFonts.plusJakartaSans(fontSize: 14, color: AppColors.onBackground),
              decoration: InputDecoration(
                hintText: 'http://10.0.2.2:8000',
                hintStyle: GoogleFonts.plusJakartaSans(
                  fontSize: 14,
                  color: AppColors.onBackground.withValues(alpha: 0.4),
                ),
                border: InputBorder.none,
                contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                suffixIcon: IconButton(
                  icon: const Icon(LucideIcons.check, size: 18, color: AppColors.secondary),
                  onPressed: () {},
                ),
              ),
              onSubmitted: (value) {
                final trimmed = value.trim();
                if (trimmed.isNotEmpty) {
                  ref.read(baseUrlProvider.notifier).state = trimmed;
                  ScaffoldMessenger.of(context).showSnackBar(
                    SnackBar(
                      content: Text('Backend URL updated to $trimmed'),
                      behavior: SnackBarBehavior.floating,
                    ),
                  );
                }
              },
            ),
          ),
          const SizedBox(height: 8),
          Text(
            'Current: $currentUrl',
            style: GoogleFonts.plusJakartaSans(
              fontSize: 12,
              color: AppColors.secondary,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildChipList(List<String> items) {
    return Wrap(
      spacing: 8,
      runSpacing: 8,
      children: items.map((item) {
        return Container(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
          decoration: BoxDecoration(
            color: AppColors.primary.withValues(alpha: 0.08),
            borderRadius: WobblyBorders.pill,
            border: Border.all(color: AppColors.primary, width: 1.5),
          ),
          child: Text(
            item,
            style: GoogleFonts.plusJakartaSans(
              fontSize: 14,
              color: AppColors.primary,
            ),
          ),
        );
      }).toList(),
    );
  }
}
