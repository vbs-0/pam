import 'package:flutter/material.dart';

/// Hisaab Register palette (same tokens as the web console): register paper, ruled lines, ballpoint blue, margin red.
class Palette {
  final Color paper, sheet, rule, ruleStrong, ink, muted, blue, blueSoft, red, redSoft, amber, green;
  const Palette({
    required this.paper, required this.sheet, required this.rule, required this.ruleStrong, required this.ink,
    required this.muted, required this.blue, required this.blueSoft, required this.red, required this.redSoft,
    required this.amber, required this.green,
  });

  static const light = Palette(
    paper: Color(0xFFF7F9FC), sheet: Color(0xFFFFFFFF), rule: Color(0xFFC9D6EA), ruleStrong: Color(0xFF9DB4D6),
    ink: Color(0xFF14171F), muted: Color(0xFF475672), blue: Color(0xFF1E3A8A), blueSoft: Color(0xFFE4EBFA),
    red: Color(0xFFC8102E), redSoft: Color(0xFFFDE8EC), amber: Color(0xFF8A4B08), green: Color(0xFF14633F),
  );
  static const dark = Palette(
    paper: Color(0xFF0E1420), sheet: Color(0xFF131B2B), rule: Color(0xFF22304A), ruleStrong: Color(0xFF34486C),
    ink: Color(0xFFE6ECF8), muted: Color(0xFF9AA8C5), blue: Color(0xFF8FB0FF), blueSoft: Color(0xFF1A2744),
    red: Color(0xFFFF6B7E), redSoft: Color(0xFF3A1620), amber: Color(0xFFF2A33A), green: Color(0xFF5CCF9B),
  );

  static Palette of(BuildContext c) => Theme.of(c).brightness == Brightness.dark ? dark : light;
}

const tabular = [FontFeature.tabularFigures(), FontFeature.liningFigures()];

ThemeData buildTheme(Brightness b) {
  final k = b == Brightness.dark ? Palette.dark : Palette.light;
  final base = ThemeData(brightness: b, useMaterial3: true);
  return base.copyWith(
    scaffoldBackgroundColor: k.paper,
    colorScheme: ColorScheme.fromSeed(seedColor: k.blue, brightness: b).copyWith(
      primary: k.blue, onPrimary: k.paper, surface: k.paper, onSurface: k.ink, error: k.red, outline: k.ruleStrong,
      surfaceContainerHighest: k.blueSoft,
    ),
    appBarTheme: AppBarTheme(
      backgroundColor: k.paper, foregroundColor: k.ink, elevation: 0, scrolledUnderElevation: 0,
      shape: Border(bottom: BorderSide(color: k.ruleStrong)),
      titleTextStyle: TextStyle(color: k.ink, fontSize: 20, fontWeight: FontWeight.w700, letterSpacing: -0.2),
    ),
    dividerTheme: DividerThemeData(color: k.rule, space: 1, thickness: 1),
    inputDecorationTheme: InputDecorationTheme(
      filled: true, fillColor: k.sheet,
      border: OutlineInputBorder(borderRadius: BorderRadius.circular(2), borderSide: BorderSide(color: k.ruleStrong)),
      enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(2), borderSide: BorderSide(color: k.ruleStrong)),
      focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(2), borderSide: BorderSide(color: k.blue, width: 2)),
      contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 14),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        backgroundColor: k.blue, foregroundColor: k.paper, minimumSize: const Size(48, 48),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(2)), textStyle: const TextStyle(fontWeight: FontWeight.w700),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: k.blue, side: BorderSide(color: k.blue), minimumSize: const Size(48, 48),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(2)), textStyle: const TextStyle(fontWeight: FontWeight.w700),
      ),
    ),
    navigationBarTheme: NavigationBarThemeData(
      backgroundColor: k.sheet, indicatorColor: k.blueSoft, surfaceTintColor: Colors.transparent,
      labelTextStyle: WidgetStatePropertyAll(TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: k.ink)),
    ),
    textTheme: base.textTheme.apply(bodyColor: k.ink, displayColor: k.ink),
  );
}
