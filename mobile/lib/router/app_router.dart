import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../features/auth/login_screen.dart';
import '../features/chat/ai_chat_screen.dart';
import '../features/history/history_screen.dart';
import '../features/home/home_screen.dart';
import '../features/onboarding/health_intake_screen.dart';
import '../features/profile/profile_screen.dart';
import '../features/recommendations/recommendations_screen.dart';
import '../features/scan/scan_result_screen.dart';
import '../features/splash/splash_screen.dart';
import '../widgets/custom_bottom_nav_bar.dart';

final GlobalKey<NavigatorState> _rootNavigatorKey = GlobalKey<NavigatorState>();
final GlobalKey<NavigatorState> _shellNavigatorKey = GlobalKey<NavigatorState>();

/// Custom slide + fade transition, 350ms, used for all page transitions.
CustomTransitionPage<void> _buildPageTransition({
  required BuildContext context,
  required GoRouterState state,
  required Widget child,
}) {
  return CustomTransitionPage<void>(
    key: state.pageKey,
    child: child,
    transitionDuration: const Duration(milliseconds: 350),
    reverseTransitionDuration: const Duration(milliseconds: 350),
    transitionsBuilder: (context, animation, secondaryAnimation, child) {
      final curvedAnimation = CurvedAnimation(
        parent: animation,
        curve: Curves.easeInOut,
      );
      return FadeTransition(
        opacity: curvedAnimation,
        child: SlideTransition(
          position: Tween<Offset>(
            begin: const Offset(0.15, 0),
            end: Offset.zero,
          ).animate(curvedAnimation),
          child: child,
        ),
      );
    },
  );
}

final GoRouter appRouter = GoRouter(
  navigatorKey: _rootNavigatorKey,
  initialLocation: '/splash',
  routes: [
    // Splash
    GoRoute(
      path: '/splash',
      parentNavigatorKey: _rootNavigatorKey,
      pageBuilder: (context, state) => _buildPageTransition(
        context: context,
        state: state,
        child: const SplashScreen(),
      ),
    ),

    // Auth
    GoRoute(
      path: '/login',
      parentNavigatorKey: _rootNavigatorKey,
      pageBuilder: (context, state) => _buildPageTransition(
        context: context,
        state: state,
        child: const LoginScreen(),
      ),
    ),

    // Health intake (first-time onboarding)
    GoRoute(
      path: '/health-intake',
      parentNavigatorKey: _rootNavigatorKey,
      pageBuilder: (context, state) => _buildPageTransition(
        context: context,
        state: state,
        child: const HealthIntakeScreen(),
      ),
    ),

    // Shell route for bottom nav
    ShellRoute(
      navigatorKey: _shellNavigatorKey,
      builder: (context, state, child) {
        return ScaffoldWithNavBar(child: child);
      },
      routes: [
        GoRoute(
          path: '/home',
          pageBuilder: (context, state) => _buildPageTransition(
            context: context,
            state: state,
            child: const HomeScreen(),
          ),
        ),
        GoRoute(
          path: '/history',
          pageBuilder: (context, state) => _buildPageTransition(
            context: context,
            state: state,
            child: const HistoryScreen(),
          ),
        ),
        GoRoute(
          path: '/recommendations',
          pageBuilder: (context, state) => _buildPageTransition(
            context: context,
            state: state,
            child: const RecommendationsScreen(),
          ),
        ),
        GoRoute(
          path: '/profile',
          pageBuilder: (context, state) => _buildPageTransition(
            context: context,
            state: state,
            child: const ProfileScreen(),
          ),
        ),
      ],
    ),

    // Scan result (full-screen, outside shell)
    GoRoute(
      path: '/scan-result',
      parentNavigatorKey: _rootNavigatorKey,
      pageBuilder: (context, state) => _buildPageTransition(
        context: context,
        state: state,
        child: const ScanResultScreen(),
      ),
    ),

    // AI Chat (full-screen, outside shell)
    GoRoute(
      path: '/ai-chat',
      parentNavigatorKey: _rootNavigatorKey,
      pageBuilder: (context, state) => _buildPageTransition(
        context: context,
        state: state,
        child: const AiChatScreen(),
      ),
    ),
  ],
);
