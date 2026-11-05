import 'package:flutter/material.dart';

import '../api.dart';
import '../format.dart';
import '../theme.dart';

class Money extends StatelessWidget {
  final int paise;
  final bool sign, struck, big;
  final Color? color;
  const Money(this.paise, {super.key, this.sign = false, this.struck = false, this.big = false, this.color});
  @override
  Widget build(BuildContext context) {
    final k = Palette.of(context);
    final txt = inr(paise, sign: sign);
    final dot = txt.lastIndexOf('.');
    final c = struck ? k.muted : (color ?? k.ink);
    final style = TextStyle(color: c, fontFeatures: tabular, fontWeight: big ? FontWeight.w700 : FontWeight.w500, fontSize: big ? 18 : 15,
        decoration: struck ? TextDecoration.lineThrough : null, decorationColor: k.red, decorationThickness: 1.5);
    return Semantics(
      label: txt.replaceAll('₹', 'rupees '),
      child: ExcludeSemantics(
        child: Text.rich(TextSpan(children: [
          TextSpan(text: txt.substring(0, dot), style: style),
          TextSpan(text: txt.substring(dot), style: style.copyWith(color: c.withValues(alpha: .6))),
        ])),
      ),
    );
  }
}

class Stamp extends StatelessWidget {
  final String text;
  final Color color;
  const Stamp(this.text, this.color, {super.key});
  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 1),
        decoration: BoxDecoration(border: Border.all(color: color), borderRadius: BorderRadius.circular(1)),
        child: Text(text.toUpperCase(), style: TextStyle(color: color, fontSize: 10.5, fontWeight: FontWeight.w800, letterSpacing: .9)),
      );
}

Widget statusStamp(BuildContext context, String status) {
  final k = Palette.of(context);
  final m = {
    'OVER': (k.red, 'Over'), 'NEAR': (k.amber, 'Near'), 'UNDER': (k.green, 'Under'), 'NO_BUDGET': (k.muted, 'No budget'),
    'ACTIVE': (k.green, 'Active'), 'MISSED': (k.red, 'Missed'), 'ENDED': (k.muted, 'Ended'),
    'TRANSFER': (k.muted, 'Contra'), 'REFUND': (k.blue, 'Refund'), 'REVERSAL': (k.muted, 'Reversed'), 'UNKNOWN': (k.red, 'Unsorted'),
  };
  final e = m[status] ?? (k.muted, titleCase(status));
  return Stamp(e.$2, e.$1);
}

class SectionTitle extends StatelessWidget {
  final String text;
  final Widget? trailing;
  const SectionTitle(this.text, {super.key, this.trailing});
  @override
  Widget build(BuildContext context) {
    final k = Palette.of(context);
    return Container(
      margin: const EdgeInsets.only(top: 24, bottom: 4),
      padding: const EdgeInsets.only(bottom: 6),
      decoration: BoxDecoration(border: Border(bottom: BorderSide(color: k.ruleStrong))),
      child: Row(children: [
        Expanded(child: Text(text.toUpperCase(), style: TextStyle(color: k.muted, fontWeight: FontWeight.w800, fontSize: 12, letterSpacing: 1))),
        if (trailing != null) trailing!,
      ]),
    );
  }
}

/// Bar length is exact; the red tick is the limit.
class LimitBar extends StatelessWidget {
  final int actual;
  final int? budget;
  final String status;
  const LimitBar({super.key, required this.actual, required this.budget, required this.status});
  @override
  Widget build(BuildContext context) {
    final k = Palette.of(context);
    final max = ([actual, budget ?? 0, 1]..sort()).last * 1.04;
    final color = status == 'OVER' ? k.red : status == 'NEAR' ? k.amber : k.blue;
    return Semantics(
      label: budget == null ? 'No budget set' : 'Spent ${(actual / (budget == 0 ? 1 : budget!) * 100).round()} percent of budget',
      child: SizedBox(
        height: 14,
        child: LayoutBuilder(builder: (context, c) {
          final w = c.maxWidth;
          return Stack(clipBehavior: Clip.none, children: [
            Positioned.fill(child: Container(decoration: BoxDecoration(border: Border.symmetric(horizontal: BorderSide(color: k.rule))))),
            Positioned(left: 0, top: 1, bottom: 1, width: (actual.clamp(0, 1 << 60) / max) * w, child: Container(decoration: BoxDecoration(color: color, borderRadius: const BorderRadius.horizontal(right: Radius.circular(4))))),
            if (budget != null) Positioned(left: (budget! / max) * w - 1, top: -3, bottom: -3, width: 2, child: ColoredBox(color: k.red)),
          ]);
        }),
      ),
    );
  }
}

class Skeleton extends StatefulWidget {
  final int rows;
  const Skeleton({super.key, this.rows = 5});
  @override
  State<Skeleton> createState() => _SkeletonState();
}

class _SkeletonState extends State<Skeleton> with SingleTickerProviderStateMixin {
  late final AnimationController _c = AnimationController(vsync: this, duration: const Duration(milliseconds: 1200))..repeat(reverse: true);
  @override
  void dispose() { _c.dispose(); super.dispose(); }
  @override
  Widget build(BuildContext context) {
    final k = Palette.of(context);
    final reduce = MediaQuery.of(context).disableAnimations;
    return Semantics(
      label: 'Loading',
      child: AnimatedBuilder(
        animation: _c,
        builder: (_, __) => Column(children: [
          for (var i = 0; i < widget.rows; i++)
            Container(
              margin: const EdgeInsets.symmetric(vertical: 7), height: 18, width: double.infinity,
              alignment: Alignment.centerLeft,
              child: FractionallySizedBox(widthFactor: .96 - (i % 3) * .11, child: Container(color: Color.lerp(k.rule, k.blueSoft, reduce ? .5 : _c.value))),
            ),
        ]),
      ),
    );
  }
}

class ErrorBox extends StatelessWidget {
  final Object error;
  final VoidCallback? retry;
  const ErrorBox(this.error, {super.key, this.retry});
  @override
  Widget build(BuildContext context) {
    final k = Palette.of(context);
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(color: k.redSoft, border: Border.all(color: k.red)),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(error is ApiException ? (error as ApiException).message : 'Something went wrong.', style: TextStyle(color: k.red, fontWeight: FontWeight.w700)),
        if (retry != null) Padding(padding: const EdgeInsets.only(top: 10), child: OutlinedButton(onPressed: retry, child: const Text('Try again'))),
      ]),
    );
  }
}

class EmptyState extends StatelessWidget {
  final String title;
  final String? hint;
  const EmptyState(this.title, {super.key, this.hint});
  @override
  Widget build(BuildContext context) {
    final k = Palette.of(context);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 36, horizontal: 12),
      child: Column(children: [
        Text(title, style: const TextStyle(fontWeight: FontWeight.w700), textAlign: TextAlign.center),
        if (hint != null) Padding(padding: const EdgeInsets.only(top: 6), child: Text(hint!, style: TextStyle(color: k.muted), textAlign: TextAlign.center)),
      ]),
    );
  }
}

/// FutureBuilder with skeleton, error and retry; `reload` re-runs the loader.
class Loader<T> extends StatefulWidget {
  final Future<T> Function() load;
  final Widget Function(BuildContext, T) builder;
  final int rows;
  const Loader({super.key, required this.load, required this.builder, this.rows = 4});
  @override
  State<Loader<T>> createState() => _LoaderState<T>();
}

class _LoaderState<T> extends State<Loader<T>> {
  late Future<T> _f = widget.load();
  @override
  void didUpdateWidget(covariant Loader<T> old) {
    super.didUpdateWidget(old);
    _f = widget.load();
  }
  @override
  Widget build(BuildContext context) => FutureBuilder<T>(
        future: _f,
        builder: (context, s) {
          if (s.connectionState != ConnectionState.done) return Skeleton(rows: widget.rows);
          if (s.hasError) return ErrorBox(s.error!, retry: () => setState(() => _f = widget.load()));
          return widget.builder(context, s.data as T);
        },
      );
}

class MonthBar extends StatelessWidget {
  final String month;
  final ValueChanged<String> onChange;
  const MonthBar(this.month, this.onChange, {super.key});
  @override
  Widget build(BuildContext context) {
    final k = Palette.of(context);
    return Container(
      decoration: BoxDecoration(color: k.sheet, border: Border.all(color: k.ruleStrong), borderRadius: BorderRadius.circular(2)),
      child: Row(children: [
        IconButton(tooltip: 'Previous month', onPressed: () => onChange(shiftMonth(month, -1)), icon: const Icon(Icons.chevron_left)),
        Expanded(child: Text(monthName(month), textAlign: TextAlign.center, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16))),
        IconButton(tooltip: 'Next month', onPressed: () => onChange(shiftMonth(month, 1)), icon: const Icon(Icons.chevron_right)),
      ]),
    );
  }
}

Future<void> showError(BuildContext context, Object e) async {
  if (!context.mounted) return;
  ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e is ApiException ? e.message : 'Something went wrong.'), behavior: SnackBarBehavior.floating));
}

/// Start-up screen: the logo breathes above a sliding bar while the saved session is checked.
class BootSplash extends StatefulWidget {
  const BootSplash({super.key});
  @override
  State<BootSplash> createState() => _BootSplashState();
}

class _BootSplashState extends State<BootSplash> with SingleTickerProviderStateMixin {
  late final AnimationController _c = AnimationController(vsync: this, duration: const Duration(milliseconds: 1400))..repeat();
  @override
  void dispose() { _c.dispose(); super.dispose(); }
  @override
  Widget build(BuildContext context) {
    final k = Palette.of(context);
    final dark = Theme.of(context).brightness == Brightness.dark;
    return Scaffold(
      body: Center(
        child: AnimatedBuilder(
          animation: _c,
          builder: (_, __) {
            final t = Curves.easeInOut.transform((_c.value < .5 ? _c.value : 1 - _c.value) * 2);
            return Column(mainAxisSize: MainAxisSize.min, children: [
              Transform.scale(scale: 1 + .08 * t, child: Opacity(opacity: 1 - .2 * t, child: Image.asset(dark ? 'assets/logo-dark.png' : 'assets/logo-light.png', width: 84, height: 84))),
              const SizedBox(height: 14),
              Text('PAM', style: TextStyle(color: k.blue, fontWeight: FontWeight.w800, letterSpacing: 3)),
              const SizedBox(height: 14),
              SizedBox(width: 120, child: LinearProgressIndicator(minHeight: 3, backgroundColor: k.rule, color: k.blue)),
            ]);
          },
        ),
      ),
    );
  }
}

/// Animates a whole number from its previous value (0 on first show) to [value]; re-animates when [value] changes.
class CountUp extends StatelessWidget {
  final int value;
  final Widget Function(int) builder;
  const CountUp(this.value, this.builder, {super.key});
  @override
  Widget build(BuildContext context) {
    if (MediaQuery.of(context).disableAnimations) return builder(value);
    return TweenAnimationBuilder<double>(
      tween: Tween<double>(begin: 0, end: value.toDouble()),
      duration: const Duration(milliseconds: 750),
      curve: Curves.easeOutCubic,
      builder: (_, v, __) => builder(v.round()),
    );
  }
}
