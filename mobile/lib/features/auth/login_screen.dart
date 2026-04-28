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

/// Login / Register screen with two tabs: "Sign In" | "Create Account".
/// Google Sign-In + email/password auth.
class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen>
    with SingleTickerProviderStateMixin {
  late final TabController _tabController;

  // Sign in controllers
  final _signInEmail = TextEditingController();
  final _signInPassword = TextEditingController();

  // Register controllers
  final _regName = TextEditingController();
  final _regEmail = TextEditingController();
  final _regPassword = TextEditingController();
  final _regConfirmPassword = TextEditingController();

  bool _obscureSignIn = true;
  bool _obscureReg = true;
  bool _obscureRegConfirm = true;

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 2, vsync: this);
  }

  @override
  void dispose() {
    _tabController.dispose();
    _signInEmail.dispose();
    _signInPassword.dispose();
    _regName.dispose();
    _regEmail.dispose();
    _regPassword.dispose();
    _regConfirmPassword.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      body: DotGridBackground(
        child: SafeArea(
          child: SingleChildScrollView(
            padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
            child: Column(
              children: [
                const SizedBox(height: 32),
                // Logo + title
                Text(
                  'TrustLens',
                  style: GoogleFonts.plusJakartaSans(
                    fontSize: 36,
                    fontWeight: FontWeight.w700,
                    color: AppColors.onBackground,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  'Know what you consume.',
                  style: GoogleFonts.plusJakartaSans(
                    fontSize: 18,
                    color: AppColors.onBackground.withValues(alpha: 0.6),
                  ),
                ),
                const SizedBox(height: 32),
                // Tab bar
                _buildTabBar(),
                const SizedBox(height: 24),
                // Tab content
                SizedBox(
                  height: 420,
                  child: TabBarView(
                    controller: _tabController,
                    children: [
                      _buildSignInTab(),
                      _buildRegisterTab(),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildTabBar() {
    return Container(
      decoration: BoxDecoration(
        color: AppColors.muted.withValues(alpha: 0.5),
        borderRadius: WobblyBorders.button,
        border: Border.all(color: AppColors.border, width: 2),
      ),
      child: TabBar(
        controller: _tabController,
        indicator: BoxDecoration(
          color: AppColors.surface,
          borderRadius: WobblyBorders.button,
          border: Border.all(color: AppColors.border, width: 2),
          boxShadow: const [AppShadows.pressed],
        ),
        indicatorSize: TabBarIndicatorSize.tab,
        dividerColor: Colors.transparent,
        labelStyle: GoogleFonts.plusJakartaSans(fontSize: 16, fontWeight: FontWeight.w700),
        unselectedLabelStyle: GoogleFonts.plusJakartaSans(fontSize: 16),
        labelColor: AppColors.onBackground,
        unselectedLabelColor: AppColors.onBackground.withValues(alpha: 0.5),
        tabs: const [
          Tab(text: 'Sign In'),
          Tab(text: 'Create Account'),
        ],
      ),
    );
  }

  Widget _buildSignInTab() {
    return SingleChildScrollView(
      child: Column(
        children: [
          WobblyTextField(
            label: 'Email',
            hint: 'you@example.com',
            controller: _signInEmail,
            keyboardType: TextInputType.emailAddress,
          ),
          const SizedBox(height: 16),
          WobblyTextField(
            label: 'Password',
            hint: 'Your password',
            controller: _signInPassword,
            obscureText: _obscureSignIn,
            suffixIcon: IconButton(
              icon: Icon(
                _obscureSignIn ? LucideIcons.eyeOff : LucideIcons.eye,
                size: 20,
                color: AppColors.onBackground.withValues(alpha: 0.5),
              ),
              onPressed: () => setState(() => _obscureSignIn = !_obscureSignIn),
            ),
          ),
          const SizedBox(height: 24),
          WobblyButton(
            label: "Let's Go \u2192",
            onTap: () => _handleSignIn(),
            width: double.infinity,
          ),
          const SizedBox(height: 20),
          _buildDivider(),
          const SizedBox(height: 20),
          _buildSocialButtons(),
        ],
      ),
    );
  }

  Widget _buildRegisterTab() {
    return SingleChildScrollView(
      child: Column(
        children: [
          WobblyTextField(
            label: 'Full Name',
            hint: 'John Doe',
            controller: _regName,
          ),
          const SizedBox(height: 12),
          WobblyTextField(
            label: 'Email',
            hint: 'you@example.com',
            controller: _regEmail,
            keyboardType: TextInputType.emailAddress,
          ),
          const SizedBox(height: 12),
          WobblyTextField(
            label: 'Password',
            hint: 'Create a password',
            controller: _regPassword,
            obscureText: _obscureReg,
            suffixIcon: IconButton(
              icon: Icon(
                _obscureReg ? LucideIcons.eyeOff : LucideIcons.eye,
                size: 20,
                color: AppColors.onBackground.withValues(alpha: 0.5),
              ),
              onPressed: () => setState(() => _obscureReg = !_obscureReg),
            ),
          ),
          const SizedBox(height: 12),
          WobblyTextField(
            label: 'Confirm Password',
            hint: 'Repeat your password',
            controller: _regConfirmPassword,
            obscureText: _obscureRegConfirm,
            suffixIcon: IconButton(
              icon: Icon(
                _obscureRegConfirm ? LucideIcons.eyeOff : LucideIcons.eye,
                size: 20,
                color: AppColors.onBackground.withValues(alpha: 0.5),
              ),
              onPressed: () =>
                  setState(() => _obscureRegConfirm = !_obscureRegConfirm),
            ),
          ),
          const SizedBox(height: 20),
          WobblyButton(
            label: "Let's Go \u2192",
            onTap: () => _handleRegister(),
            width: double.infinity,
          ),
          const SizedBox(height: 16),
          _buildDivider(),
          const SizedBox(height: 16),
          _buildSocialButtons(),
        ],
      ),
    );
  }

  Widget _buildDivider() {
    return Row(
      children: [
        Expanded(child: Divider(color: AppColors.muted, thickness: 2)),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 12),
          child: Text(
            'or',
            style: GoogleFonts.plusJakartaSans(
              fontSize: 16,
              color: AppColors.onBackground.withValues(alpha: 0.5),
            ),
          ),
        ),
        Expanded(child: Divider(color: AppColors.muted, thickness: 2)),
      ],
    );
  }

  Widget _buildSocialButtons() {
    return Column(
      children: [
        _SocialAuthButton(
          label: 'Continue with Google',
          icon: LucideIcons.chrome,
          onTap: () => _handleGoogleSignIn(),
        ),
      ],
    );
  }

  void _handleSignIn() {
    // TODO: Wire to Firebase Auth in Phase 3
    context.go('/home');
  }

  void _handleRegister() {
    // TODO: Wire to Firebase Auth in Phase 3
    context.go('/health-intake');
  }

  void _handleGoogleSignIn() {
    // TODO: Wire to Google Sign-In in Phase 3
    context.go('/home');
  }
}

class _SocialAuthButton extends StatefulWidget {
  final String label;
  final IconData icon;
  final VoidCallback onTap;

  const _SocialAuthButton({
    required this.label,
    required this.icon,
    required this.onTap,
  });

  @override
  State<_SocialAuthButton> createState() => _SocialAuthButtonState();
}

class _SocialAuthButtonState extends State<_SocialAuthButton> {
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
          width: double.infinity,
          padding: const EdgeInsets.symmetric(vertical: 14),
          decoration: BoxDecoration(
            color: AppColors.surface,
            borderRadius: WobblyBorders.button,
            border: Border.all(color: AppColors.border),
            boxShadow: const [AppShadows.card],
          ),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(widget.icon, size: 20, color: AppColors.onBackground),
              const SizedBox(width: 10),
              Text(
                widget.label,
                style: GoogleFonts.plusJakartaSans(
                  fontSize: 16,
                  color: AppColors.onBackground,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
