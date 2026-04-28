import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:lucide_icons/lucide_icons.dart';

import '../../theme/app_theme.dart';
import '../../theme/wobbly_borders.dart';
import '../../widgets/dot_grid_background.dart';
import '../../widgets/wobbly_button.dart';
import '../../widgets/wobbly_card.dart';
import '../../widgets/wobbly_text_field.dart';

/// Health intake multi-step card flow (6 steps), all optional.
/// Skip available at every step.
class HealthIntakeScreen extends StatefulWidget {
  const HealthIntakeScreen({super.key});

  @override
  State<HealthIntakeScreen> createState() => _HealthIntakeScreenState();
}

class _HealthIntakeScreenState extends State<HealthIntakeScreen> {
  int _currentStep = 0;
  static const int _totalSteps = 6;

  // Step 2 data
  String? _ageRange;
  String? _biologicalSex;

  // Step 3 data
  final Set<String> _healthConditions = {};

  // Step 4 data
  final Set<String> _dietaryPreferences = {};

  // Step 5 data
  final _medicationsController = TextEditingController();

  @override
  void dispose() {
    _medicationsController.dispose();
    super.dispose();
  }

  void _next() {
    if (_currentStep < _totalSteps - 1) {
      setState(() => _currentStep++);
    } else {
      context.go('/home');
    }
  }

  void _skip() {
    context.go('/home');
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      body: DotGridBackground(
        child: SafeArea(
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
            child: Column(
              children: [
                // Progress indicator
                _buildProgressBar(),
                const SizedBox(height: 24),
                // Step content
                Expanded(
                  child: AnimatedSwitcher(
                    duration: const Duration(milliseconds: 350),
                    child: _buildStep(_currentStep),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildProgressBar() {
    return Row(
      children: List.generate(_totalSteps, (i) {
        return Expanded(
          child: Container(
            height: 6,
            margin: const EdgeInsets.symmetric(horizontal: 3),
            decoration: BoxDecoration(
              color: i <= _currentStep ? AppColors.primary : AppColors.muted,
              borderRadius: WobblyBorders.pill,
            ),
          ),
        );
      }),
    );
  }

  Widget _buildStep(int step) {
    switch (step) {
      case 0:
        return _buildIntroStep();
      case 1:
        return _buildBasicInfoStep();
      case 2:
        return _buildHealthConditionsStep();
      case 3:
        return _buildDietaryStep();
      case 4:
        return _buildMedicationsStep();
      case 5:
        return _buildConfirmationStep();
      default:
        return const SizedBox();
    }
  }

  Widget _buildIntroStep() {
    return _StepCard(
      key: const ValueKey(0),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Icon(LucideIcons.leafyGreen, size: 48, color: AppColors.verified),
          const SizedBox(height: 16),
          Text(
            'Help us personalize\nyour experience \uD83C\uDF3F',
            textAlign: TextAlign.center,
            style: GoogleFonts.plusJakartaSans(
              fontSize: 24,
              fontWeight: FontWeight.w700,
              color: AppColors.onBackground,
            ),
          ),
          const SizedBox(height: 12),
          Text(
            'Answer a few optional questions so we can tailor food recommendations and flag potential allergens for you.',
            textAlign: TextAlign.center,
            style: GoogleFonts.plusJakartaSans(
              fontSize: 16,
              color: AppColors.onBackground.withValues(alpha: 0.7),
            ),
          ),
          const SizedBox(height: 24),
          WobblyButton(
            label: "Let's do this \u2192",
            onTap: _next,
            width: double.infinity,
          ),
          const SizedBox(height: 12),
          GestureDetector(
            onTap: _skip,
            child: Text(
              "Skip for now \u2014 I'll set this up later",
              style: GoogleFonts.plusJakartaSans(
                fontSize: 15,
                color: AppColors.secondary,
                decoration: TextDecoration.underline,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildBasicInfoStep() {
    final ageRanges = ['18-25', '26-35', '36-45', '46-55', '56-65', '65+'];

    return _StepCard(
      key: const ValueKey(1),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Text('Basic Info', style: GoogleFonts.plusJakartaSans(fontSize: 22, fontWeight: FontWeight.w700)),
          const SizedBox(height: 4),
          Text(
            'All fields are optional',
            style: GoogleFonts.plusJakartaSans(
              fontSize: 14,
              color: AppColors.onBackground.withValues(alpha: 0.5),
            ),
          ),
          const SizedBox(height: 16),
          Text('Age Range', style: GoogleFonts.plusJakartaSans(fontSize: 16)),
          const SizedBox(height: 8),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: ageRanges
                .map((r) => _ChipSelector(
                      label: r,
                      isSelected: _ageRange == r,
                      onTap: () => setState(() => _ageRange = r),
                    ))
                .toList(),
          ),
          const SizedBox(height: 16),
          Text('Biological Sex (optional)', style: GoogleFonts.plusJakartaSans(fontSize: 16)),
          const SizedBox(height: 8),
          Wrap(
            spacing: 8,
            children: ['Male', 'Female', 'Prefer not to say']
                .map((s) => _ChipSelector(
                      label: s,
                      isSelected: _biologicalSex == s,
                      onTap: () => setState(() => _biologicalSex = s),
                    ))
                .toList(),
          ),
          const SizedBox(height: 24),
          _buildStepButtons(),
        ],
      ),
    );
  }

  Widget _buildHealthConditionsStep() {
    final conditions = [
      'Diabetes',
      'Hypertension',
      'Heart Disease',
      'Kidney Disease',
      'Lactose Intolerance',
      'Gluten Sensitivity',
      'Nut Allergy',
      'Thyroid Disorder',
      'Pregnancy',
      'Other',
    ];

    return _StepCard(
      key: const ValueKey(2),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Text('Health Conditions',
              style: GoogleFonts.plusJakartaSans(fontSize: 22, fontWeight: FontWeight.w700)),
          const SizedBox(height: 4),
          Text(
            'Select any that apply (optional)',
            style: GoogleFonts.plusJakartaSans(
              fontSize: 14,
              color: AppColors.onBackground.withValues(alpha: 0.5),
            ),
          ),
          const SizedBox(height: 16),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: conditions
                .map((c) => _ChipSelector(
                      label: c,
                      isSelected: _healthConditions.contains(c),
                      onTap: () => setState(() {
                        if (_healthConditions.contains(c)) {
                          _healthConditions.remove(c);
                        } else {
                          _healthConditions.add(c);
                        }
                      }),
                    ))
                .toList(),
          ),
          const SizedBox(height: 24),
          _buildStepButtons(),
        ],
      ),
    );
  }

  Widget _buildDietaryStep() {
    final prefs = [
      'Vegetarian',
      'Vegan',
      'Halal',
      'Kosher',
      'Keto',
      'Low-Sodium',
      'Other',
    ];

    return _StepCard(
      key: const ValueKey(3),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Text('Dietary Preferences',
              style: GoogleFonts.plusJakartaSans(fontSize: 22, fontWeight: FontWeight.w700)),
          const SizedBox(height: 4),
          Text(
            'Select any that apply (optional)',
            style: GoogleFonts.plusJakartaSans(
              fontSize: 14,
              color: AppColors.onBackground.withValues(alpha: 0.5),
            ),
          ),
          const SizedBox(height: 16),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: prefs
                .map((p) => _ChipSelector(
                      label: p,
                      isSelected: _dietaryPreferences.contains(p),
                      onTap: () => setState(() {
                        if (_dietaryPreferences.contains(p)) {
                          _dietaryPreferences.remove(p);
                        } else {
                          _dietaryPreferences.add(p);
                        }
                      }),
                    ))
                .toList(),
          ),
          const SizedBox(height: 24),
          _buildStepButtons(),
        ],
      ),
    );
  }

  Widget _buildMedicationsStep() {
    return _StepCard(
      key: const ValueKey(4),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Text('Current Medications',
              style: GoogleFonts.plusJakartaSans(fontSize: 22, fontWeight: FontWeight.w700)),
          const SizedBox(height: 4),
          Text(
            'List any medicines you currently take (optional)',
            style: GoogleFonts.plusJakartaSans(
              fontSize: 14,
              color: AppColors.onBackground.withValues(alpha: 0.5),
            ),
          ),
          const SizedBox(height: 16),
          WobblyTextField(
            hint: 'e.g. Metformin 500mg, Atorvastatin 10mg...',
            controller: _medicationsController,
            maxLines: 4,
          ),
          const SizedBox(height: 24),
          _buildStepButtons(),
        ],
      ),
    );
  }

  Widget _buildConfirmationStep() {
    return _StepCard(
      key: const ValueKey(5),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Text('Your Profile Summary',
              style: GoogleFonts.plusJakartaSans(fontSize: 22, fontWeight: FontWeight.w700)),
          const SizedBox(height: 16),
          if (_ageRange != null) _buildSummaryRow('Age', _ageRange!),
          if (_biologicalSex != null) _buildSummaryRow('Sex', _biologicalSex!),
          if (_healthConditions.isNotEmpty)
            _buildSummaryRow('Conditions', _healthConditions.join(', ')),
          if (_dietaryPreferences.isNotEmpty)
            _buildSummaryRow('Diet', _dietaryPreferences.join(', ')),
          if (_medicationsController.text.isNotEmpty)
            _buildSummaryRow('Medications', _medicationsController.text),
          if (_ageRange == null &&
              _biologicalSex == null &&
              _healthConditions.isEmpty &&
              _dietaryPreferences.isEmpty &&
              _medicationsController.text.isEmpty)
            Text(
              'No data entered yet. You can always update your profile later.',
              style: GoogleFonts.plusJakartaSans(
                fontSize: 15,
                color: AppColors.onBackground.withValues(alpha: 0.6),
              ),
            ),
          const SizedBox(height: 8),
          Row(
            children: [
              const Icon(LucideIcons.lock, size: 14, color: AppColors.secondary),
              const SizedBox(width: 6),
              Expanded(
                child: Text(
                  'Your data is stored encrypted and never sold.',
                  style: GoogleFonts.plusJakartaSans(
                    fontSize: 13,
                    color: AppColors.secondary,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 24),
          WobblyButton(
            label: 'Save My Profile \u2713',
            onTap: () {
              // TODO: Save to secure storage in Phase 3
              context.go('/home');
            },
            width: double.infinity,
          ),
          const SizedBox(height: 12),
          Center(
            child: GestureDetector(
              onTap: _skip,
              child: Text(
                'Skip for now',
                style: GoogleFonts.plusJakartaSans(
                  fontSize: 15,
                  color: AppColors.secondary,
                  decoration: TextDecoration.underline,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildSummaryRow(String label, String value) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 100,
            child: Text(
              label,
              style: GoogleFonts.plusJakartaSans(
                fontSize: 15,
                fontWeight: FontWeight.w700,
                color: AppColors.onBackground,
              ),
            ),
          ),
          Expanded(
            child: Text(
              value,
              style: GoogleFonts.plusJakartaSans(
                fontSize: 15,
                color: AppColors.onBackground.withValues(alpha: 0.7),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildStepButtons() {
    return Row(
      children: [
        Expanded(
          child: WobblyButton(
            label: 'Skip',
            variant: WobblyButtonVariant.secondary,
            onTap: _next,
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: WobblyButton(
            label: 'Next \u2192',
            onTap: _next,
          ),
        ),
      ],
    );
  }
}

class _StepCard extends StatelessWidget {
  final Widget child;

  const _StepCard({super.key, required this.child});

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      child: WobblyCard(
        padding: const EdgeInsets.all(24),
        child: child,
      ),
    );
  }
}

class _ChipSelector extends StatelessWidget {
  final String label;
  final bool isSelected;
  final VoidCallback onTap;

  const _ChipSelector({
    required this.label,
    required this.isSelected,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
        decoration: BoxDecoration(
          color: isSelected ? AppColors.primary.withValues(alpha: 0.12) : AppColors.surface,
          borderRadius: WobblyBorders.pill,
          border: Border.all(
            color: isSelected ? AppColors.primary : AppColors.border,
            width: isSelected ? 2.5 : 2,
          ),
        ),
        child: Text(
          label,
          style: GoogleFonts.plusJakartaSans(
            fontSize: 14,
            color: isSelected ? AppColors.primary : AppColors.onBackground,
          ),
        ),
      ),
    );
  }
}
