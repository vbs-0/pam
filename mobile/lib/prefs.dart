import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Version shown on the About screen. Keep in step with `version:` in pubspec.yaml.
const appVersion = '1.3.0';

/// Small on-device preferences (theme choice, which users have seen the walkthrough). Never throws: a storage
/// failure just means the default is used.
class Prefs {
  static const _s = FlutterSecureStorage();
  static final themeMode = ValueNotifier<ThemeMode>(ThemeMode.system);

  static Future<void> load() async {
    try {
      final t = await _s.read(key: 'theme');
      themeMode.value = t == 'light' ? ThemeMode.light : t == 'dark' ? ThemeMode.dark : ThemeMode.system;
    } catch (_) {/* default */}
  }

  static Future<void> setTheme(ThemeMode m) async {
    themeMode.value = m;
    try { await _s.write(key: 'theme', value: m == ThemeMode.light ? 'light' : m == ThemeMode.dark ? 'dark' : 'system'); } catch (_) {/* kept for this session */}
  }

  static Future<bool> seenWalkthrough(String userId) async {
    try { return await _s.read(key: 'walk_$userId') == '1'; } catch (_) { return true; }
  }

  static Future<void> markWalkthrough(String userId, {bool seen = true}) async {
    try { if (seen) { await _s.write(key: 'walk_$userId', value: '1'); } else { await _s.delete(key: 'walk_$userId'); } } catch (_) {/* ignore */}
  }
}
