import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../models/health_profile.dart';

/// Local storage service using flutter_secure_storage (for sensitive data)
/// and shared_preferences (for settings).
class StorageService {
  static const _healthProfileKey = 'health_profile';
  static const _authTokenKey = 'auth_token';
  static const _userNameKey = 'user_name';
  static const _userEmailKey = 'user_email';
  static const _isFirstTimeKey = 'is_first_time';
  static const _scanHistoryKey = 'scan_history';

  final FlutterSecureStorage _secureStorage;

  StorageService({FlutterSecureStorage? secureStorage})
      : _secureStorage = secureStorage ?? const FlutterSecureStorage();

  // --- Auth Token ---

  Future<String?> getAuthToken() => _secureStorage.read(key: _authTokenKey);

  Future<void> setAuthToken(String token) =>
      _secureStorage.write(key: _authTokenKey, value: token);

  Future<void> clearAuthToken() => _secureStorage.delete(key: _authTokenKey);

  // --- Health Profile (encrypted) ---

  Future<HealthProfile?> getHealthProfile() async {
    final json = await _secureStorage.read(key: _healthProfileKey);
    if (json == null) return null;
    return HealthProfile.fromJson(jsonDecode(json) as Map<String, dynamic>);
  }

  Future<void> setHealthProfile(HealthProfile profile) =>
      _secureStorage.write(key: _healthProfileKey, value: jsonEncode(profile.toJson()));

  // --- User Info ---

  Future<void> setUserInfo({required String name, required String email}) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_userNameKey, name);
    await prefs.setString(_userEmailKey, email);
  }

  Future<String?> getUserName() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(_userNameKey);
  }

  Future<String?> getUserEmail() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(_userEmailKey);
  }

  // --- First Time Flag ---

  Future<bool> isFirstTime() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getBool(_isFirstTimeKey) ?? true;
  }

  Future<void> setFirstTimeDone() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(_isFirstTimeKey, false);
  }

  // --- Scan History (local cache) ---

  Future<List<Map<String, dynamic>>> getScanHistory() async {
    final prefs = await SharedPreferences.getInstance();
    final jsonStr = prefs.getString(_scanHistoryKey);
    if (jsonStr == null) return [];
    final list = jsonDecode(jsonStr) as List<dynamic>;
    return list.map((e) => e as Map<String, dynamic>).toList();
  }

  Future<void> addScanToHistory(Map<String, dynamic> scan) async {
    final history = await getScanHistory();
    history.insert(0, scan);
    // Keep last 50 scans
    if (history.length > 50) history.removeRange(50, history.length);
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_scanHistoryKey, jsonEncode(history));
  }

  // --- Clear All ---

  Future<void> clearAll() async {
    await _secureStorage.deleteAll();
    final prefs = await SharedPreferences.getInstance();
    await prefs.clear();
  }
}
