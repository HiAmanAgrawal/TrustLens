import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'service_providers.dart';

/// Authentication state.
enum AuthStatus { unknown, authenticated, unauthenticated }

class AuthState {
  final AuthStatus status;
  final String? userName;
  final String? userEmail;
  final bool isFirstTime;

  const AuthState({
    this.status = AuthStatus.unknown,
    this.userName,
    this.userEmail,
    this.isFirstTime = true,
  });

  AuthState copyWith({
    AuthStatus? status,
    String? userName,
    String? userEmail,
    bool? isFirstTime,
  }) {
    return AuthState(
      status: status ?? this.status,
      userName: userName ?? this.userName,
      userEmail: userEmail ?? this.userEmail,
      isFirstTime: isFirstTime ?? this.isFirstTime,
    );
  }
}

class AuthNotifier extends StateNotifier<AuthState> {
  final Ref ref;

  AuthNotifier(this.ref) : super(const AuthState());

  /// Check if user is already logged in.
  Future<void> checkAuth() async {
    final storage = ref.read(storageServiceProvider);
    final token = await storage.getAuthToken();
    final isFirst = await storage.isFirstTime();
    final name = await storage.getUserName();
    final email = await storage.getUserEmail();

    if (token != null) {
      state = AuthState(
        status: AuthStatus.authenticated,
        userName: name,
        userEmail: email,
        isFirstTime: isFirst,
      );
    } else {
      state = const AuthState(status: AuthStatus.unauthenticated);
    }
  }

  /// Sign in with email/password (mock — stores a fake token).
  Future<void> signInWithEmail(String email, String password) async {
    final storage = ref.read(storageServiceProvider);
    await storage.setAuthToken('mock_token_${DateTime.now().millisecondsSinceEpoch}');
    await storage.setUserInfo(name: email.split('@').first, email: email);
    final isFirst = await storage.isFirstTime();

    state = AuthState(
      status: AuthStatus.authenticated,
      userName: email.split('@').first,
      userEmail: email,
      isFirstTime: isFirst,
    );
  }

  /// Register with email/password (mock).
  Future<void> register(String name, String email, String password) async {
    final storage = ref.read(storageServiceProvider);
    await storage.setAuthToken('mock_token_${DateTime.now().millisecondsSinceEpoch}');
    await storage.setUserInfo(name: name, email: email);

    state = AuthState(
      status: AuthStatus.authenticated,
      userName: name,
      userEmail: email,
      isFirstTime: true,
    );
  }

  /// Sign in with Google (mock).
  Future<void> signInWithGoogle() async {
    final storage = ref.read(storageServiceProvider);
    await storage.setAuthToken('google_mock_token_${DateTime.now().millisecondsSinceEpoch}');
    await storage.setUserInfo(name: 'Google User', email: 'user@gmail.com');
    final isFirst = await storage.isFirstTime();

    state = AuthState(
      status: AuthStatus.authenticated,
      userName: 'Google User',
      userEmail: 'user@gmail.com',
      isFirstTime: isFirst,
    );
  }

  /// Complete onboarding.
  Future<void> completeOnboarding() async {
    final storage = ref.read(storageServiceProvider);
    await storage.setFirstTimeDone();
    state = state.copyWith(isFirstTime: false);
  }

  /// Sign out.
  Future<void> signOut() async {
    final storage = ref.read(storageServiceProvider);
    await storage.clearAuthToken();
    state = const AuthState(status: AuthStatus.unauthenticated);
  }
}

final authProvider = StateNotifierProvider<AuthNotifier, AuthState>((ref) {
  return AuthNotifier(ref);
});
