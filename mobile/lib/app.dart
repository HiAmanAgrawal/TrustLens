import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'router/app_router.dart';
import 'theme/app_theme.dart';

/// Provider for dark/light theme toggle, persists via local storage.
final themeModeProvider = StateProvider<ThemeMode>((ref) => ThemeMode.light);

/// Root widget — configures theme, routing, and global overlays.
class TrustLensApp extends ConsumerWidget {
  const TrustLensApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final themeMode = ref.watch(themeModeProvider);

    return MaterialApp.router(
      title: 'TrustLens',
      debugShowCheckedModeBanner: false,
      theme: buildAppTheme(dark: false),
      darkTheme: buildAppTheme(dark: true),
      themeMode: themeMode,
      routerConfig: appRouter,
    );
  }
}
