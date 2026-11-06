import 'package:flutter/material.dart';

/// Vestox look: off-white paper, ink black, orange, sand; light serif display; rounded cards.
/// Field names are the same tokens as the web console so every screen re-themes through them.
const serif = 'InstrumentSerif';

class Palette {
  final Color paper, sheet, rule, ruleStrong, ink, muted, blue, blueSoft, red, redSoft, amber, green, orange, sand, ok, bar, track;
  const Palette({
    required this.paper, required this.sheet, required this.rule, required this.ruleStrong, required this.ink,
    required this.muted, required this.blue, required this.blueSoft, required this.red, required this.redSoft,
    required this.amber, required this.green, required this.orange, required this.sand, required this.ok,
    required this.bar, required this.track,
  });

  static const light = Palette(
    paper: Color(0xFFF6F6F6), sheet: Color(0xFFFFFFFF), rule: Color(0xFFE3E0D8), ruleStrong: Color(0xFFCFCABD),
    ink: Color(0xFF191919), muted: Color(0xFF6A675F), blue: Color(0xFF191919), blueSoft: Color(0xFFEFECE4),
    red: Color(0xFFD63A12), redSoft: Color(0xFFFFDEDE), amber: Color(0xFFA85D00), green: Color(0xFF1F7A45),
    orange: Color(0xFFF75708), sand: Color(0xFFE4DCCF), ok: Color(0xFF12A150), bar: Color(0xFFD9D2C2), track: Color(0xFFECE8DD),
  );
  static const dark = Palette(
    paper: Color(0xFF121212), sheet: Color(0xFF1B1B1B), rule: Color(0xFF2C2B28), ruleStrong: Color(0xFF403E39),
    ink: Color(0xFFF4F1E8), muted: Color(0xFFA5A196), blue: Color(0xFFF4F1E8), blueSoft: Color(0xFF25231F),
    red: Color(0xFFFF7A52), redSoft: Color(0xFF3A1B14), amber: Color(0xFFF2A33A), green: Color(0xFF6FD39A),
    orange: Color(0xFFFF6A1F), sand: Color(0xFF2A2620), ok: Color(0xFF2BD36B), bar: Color(0xFF4A463D), track: Color(0xFF2A2824),
  );

  static Palette of(BuildContext c) => Theme.of(c).brightness == Brightness.dark ? dark : light;
}

const tabular = [FontFeature.tabularFigures(), FontFeature.liningFigures()];
const ease = Cubic(.215, .61, .355, 1);   // the site's cubic-bezier(0.215, 0.61, 0.355, 1)
const draw = Cubic(.645, .045, .355, 1);  // the line-draw curve

ThemeData buildTheme(Brightness b) {
  final k = b == Brightness.dark ? Palette.dark : Palette.light;
  final base = ThemeData(brightness: b, useMaterial3: true);
  final r14 = RoundedRectangleBorder(borderRadius: BorderRadius.circular(14));
  OutlineInputBorder ob(Color c, [double w = 1]) => OutlineInputBorder(borderRadius: BorderRadius.circular(14), borderSide: BorderSide(color: c, width: w));
  return base.copyWith(
    scaffoldBackgroundColor: k.paper,
    colorScheme: ColorScheme.fromSeed(seedColor: k.orange, brightness: b).copyWith(
      primary: k.blue, onPrimary: k.paper, surface: k.paper, onSurface: k.ink, error: k.red, outline: k.ruleStrong,
      surfaceContainerHighest: k.blueSoft, secondary: k.orange,
    ),
    pageTransitionsTheme: const PageTransitionsTheme(builders: {
      TargetPlatform.android: FadeForwardsPageTransitionsBuilder(),
    }),
    appBarTheme: AppBarTheme(
      backgroundColor: k.paper, foregroundColor: k.ink, elevation: 0, scrolledUnderElevation: 0,
      titleTextStyle: TextStyle(color: k.ink, fontFamily: serif, fontSize: 30, letterSpacing: -.3),
    ),
    dividerTheme: DividerThemeData(color: k.rule, space: 1, thickness: 1),
    inputDecorationTheme: InputDecorationTheme(
      filled: true, fillColor: k.sheet, border: ob(k.ruleStrong), enabledBorder: ob(k.ruleStrong), focusedBorder: ob(k.orange, 2),
      contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        backgroundColor: k.blue, foregroundColor: k.paper, minimumSize: const Size(48, 50), shape: r14,
        textStyle: const TextStyle(fontWeight: FontWeight.w700),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: k.ink, side: BorderSide(color: k.ink), minimumSize: const Size(48, 50), shape: r14,
        textStyle: const TextStyle(fontWeight: FontWeight.w700),
      ),
    ),
    navigationBarTheme: NavigationBarThemeData(
      backgroundColor: k.paper, indicatorColor: k.orange, surfaceTintColor: Colors.transparent, height: 68,
      indicatorShape: const StadiumBorder(),
      iconTheme: WidgetStateProperty.resolveWith((s) => IconThemeData(color: s.contains(WidgetState.selected) ? Colors.white : k.ink)),
      labelTextStyle: WidgetStatePropertyAll(TextStyle(fontSize: 14, fontFamily: serif, color: k.ink)),
    ),
    textTheme: base.textTheme.apply(bodyColor: k.ink, displayColor: k.ink),
  );
}
