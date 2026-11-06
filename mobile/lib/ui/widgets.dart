import 'package:flutter/material.dart';

import '../api.dart';
import '../format.dart';
import '../offline.dart';
import '../theme.dart';
import 'motion.dart';

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
        padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 2),
        decoration: BoxDecoration(border: Border.all(color: color, width: 1.2), borderRadius: BorderRadius.circular(99)),
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
      margin: const EdgeInsets.only(top: 28, bottom: 6),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Expanded(child: Text(text.toUpperCase(), style: const TextStyle(fontFamily: serif, fontSize: 28, height: 1.05, letterSpacing: .2))),
          if (trailing != null) trailing!,
        ]),
        const SizedBox(height: 6),
        // the line draws itself under the heading
        TweenAnimationBuilder<double>(
          tween: Tween(begin: 0, end: 1), duration: const Duration(milliseconds: 900), curve: draw,
          builder: (_, v, __) => FractionallySizedBox(alignment: Alignment.centerLeft, widthFactor: v, child: Container(height: 1.5, color: k.ink)),
        ),
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
    final color = status == 'OVER' ? k.red : status == 'NEAR' ? k.amber : k.orange;
    return Semantics(
      label: budget == null ? 'No budget set' : 'Spent ${(actual / (budget == 0 ? 1 : budget!) * 100).round()} percent of budget',
      child: SizedBox(
        height: 14,
        child: LayoutBuilder(builder: (context, c) {
          final w = c.maxWidth;
          final target = (actual.clamp(0, 1 << 60) / max) * w;
          return Stack(clipBehavior: Clip.none, children: [
            Positioned.fill(child: Container(decoration: BoxDecoration(color: k.track, borderRadius: BorderRadius.circular(99)))),
            // grows in from the left, like the site's bars
            TweenAnimationBuilder<double>(
              tween: Tween(begin: 0, end: target), duration: const Duration(milliseconds: 1000), curve: draw,
              builder: (_, v, __) => Positioned(left: 0, top: 0, bottom: 0, width: v, child: Container(decoration: BoxDecoration(color: color, borderRadius: BorderRadius.circular(99)))),
            ),
            if (budget != null) Positioned(left: (budget! / max) * w - 1, top: -3, bottom: -3, width: 2.5, child: ColoredBox(color: k.ink)),
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
              child: FractionallySizedBox(widthFactor: .96 - (i % 3) * .11, child: Container(decoration: BoxDecoration(borderRadius: BorderRadius.circular(99), color: Color.lerp(k.track, k.bar, reduce ? .5 : _c.value)))),
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
      decoration: BoxDecoration(color: k.redSoft, border: Border.all(color: k.red), borderRadius: BorderRadius.circular(18)),
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
      decoration: BoxDecoration(color: k.sheet, border: Border.all(color: k.ink, width: 1.4), borderRadius: BorderRadius.circular(99)),
      child: Row(children: [
        _Round(Icons.chevron_left, 'Previous month', () => onChange(shiftMonth(month, -1))),
        Expanded(
          child: Press(
            onTap: () => _pick(context, k),
            child: Row(mainAxisAlignment: MainAxisAlignment.center, children: [
              Flexible(child: AnimatedSwitcher(
                duration: const Duration(milliseconds: 380), switchInCurve: ease,
                transitionBuilder: (c, a) => ClipRect(child: SlideTransition(position: Tween(begin: const Offset(0, .8), end: Offset.zero).animate(CurvedAnimation(parent: a, curve: ease)), child: c)),
                child: Text(monthName(month), key: ValueKey(month), overflow: TextOverflow.ellipsis, style: const TextStyle(fontFamily: serif, fontSize: 24)),
              )),
              const SizedBox(width: 6),
              Icon(Icons.calendar_month_outlined, size: 18, color: k.orange),
            ]),
          ),
        ),
        _Round(Icons.chevron_right, 'Next month', () => onChange(shiftMonth(month, 1))),
      ]),
    );
  }

  /// Twelve-month grid for the shown year; each month lifts and fills orange when pressed.
  Future<void> _pick(BuildContext context, Palette k) async {
    var year = int.parse(month.substring(0, 4));
    final picked = await showModalBottomSheet<String>(
      context: context,
      backgroundColor: k.sheet,
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(28))),
      builder: (ctx) => StatefulBuilder(builder: (ctx, set) {
        const names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
        return Padding(
          padding: const EdgeInsets.fromLTRB(20, 18, 20, 28),
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            Row(children: [
              _Round(Icons.chevron_left, 'Previous year', () => set(() => year--)),
              Expanded(child: Text('$year', textAlign: TextAlign.center, style: const TextStyle(fontFamily: serif, fontSize: 32))),
              _Round(Icons.chevron_right, 'Next year', () => set(() => year++)),
            ]),
            const SizedBox(height: 12),
            GridView.count(
              shrinkWrap: true, crossAxisCount: 4, mainAxisSpacing: 10, crossAxisSpacing: 10, childAspectRatio: 1.5, physics: const NeverScrollableScrollPhysics(),
              children: [
                for (var i = 0; i < 12; i++)
                  SlideUp(
                    index: i ~/ 2, distance: 22,
                    child: Press(
                      onTap: () => Navigator.pop(ctx, '$year-${(i + 1).toString().padLeft(2, '0')}'),
                      child: Builder(builder: (_) {
                        final m = '$year-${(i + 1).toString().padLeft(2, '0')}';
                        final sel = m == month;
                        return Container(
                          alignment: Alignment.center,
                          decoration: BoxDecoration(color: sel ? k.orange : k.paper, border: Border.all(color: sel ? k.orange : k.ruleStrong), borderRadius: BorderRadius.circular(16)),
                          child: Text(names[i], style: TextStyle(fontFamily: serif, fontSize: 22, color: sel ? Colors.white : k.ink)),
                        );
                      }),
                    ),
                  ),
              ],
            ),
          ]),
        );
      }),
    );
    if (picked != null) onChange(picked);
  }
}

class _Round extends StatelessWidget {
  final IconData icon;
  final String tip;
  final VoidCallback onTap;
  const _Round(this.icon, this.tip, this.onTap);
  @override
  Widget build(BuildContext context) => Press(
        onTap: onTap,
        child: Tooltip(message: tip, child: Container(
          width: 44, height: 44, margin: const EdgeInsets.all(3), alignment: Alignment.center,
          decoration: BoxDecoration(color: Palette.of(context).paper, shape: BoxShape.circle),
          child: Icon(icon, size: 22),
        )),
      );
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
              Text('PAM', style: TextStyle(fontFamily: serif, fontSize: 34, color: k.ink, letterSpacing: 4)),
              const SizedBox(height: 14),
              SizedBox(width: 120, child: ClipRRect(borderRadius: BorderRadius.circular(9), child: LinearProgressIndicator(minHeight: 3, backgroundColor: k.track, color: k.orange))),
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


/// One slim line that says what the phone is doing: working offline, sending saved changes, or a change the server
/// refused. Tapping it lists the changes so nothing disappears silently.
class SyncBanner extends StatelessWidget {
  const SyncBanner({super.key});
  @override
  Widget build(BuildContext context) => ValueListenableBuilder<bool>(
        valueListenable: Api.instance.offline,
        builder: (_, off, __) => ValueListenableBuilder<int>(
          valueListenable: Outbox.instance.changes,
          builder: (_, __, ___) => ValueListenableBuilder<bool>(
            valueListenable: Outbox.instance.syncing,
            builder: (context, busy, ____) {
              final k = Palette.of(context);
              final n = Outbox.instance.pending.length, bad = Outbox.instance.failed.length;
              if (!off && n == 0 && bad == 0) return const SizedBox.shrink();
              final (color, text) = bad > 0
                  ? (k.red, '$bad change${bad == 1 ? '' : 's'} could not be saved · tap to review')
                  : busy ? (k.blue, 'Syncing $n change${n == 1 ? '' : 's'}…')
                  : off ? (k.amber, n > 0 ? 'Offline · $n change${n == 1 ? '' : 's'} saved on this phone, will sync automatically' : 'Offline · everything still works and will sync when you are back')
                  : (k.blue, '$n change${n == 1 ? '' : 's'} waiting to sync');
              return InkWell(
                onTap: bad > 0 || n > 0 ? () => showModalBottomSheet<void>(context: context, isScrollControlled: true, useSafeArea: true, builder: (_) => const _SyncSheet()) : null,
                child: Container(width: double.infinity, color: color, padding: const EdgeInsets.symmetric(vertical: 5, horizontal: 12), child: Text(text, textAlign: TextAlign.center, style: TextStyle(color: k.paper, fontWeight: FontWeight.w700, fontSize: 12))),
              );
            },
          ),
        ),
      );
}

class _SyncSheet extends StatelessWidget {
  const _SyncSheet();
  String _label(Op o) {
    final p = o.path.replaceFirst('/me/', '');
    if (p.startsWith('transactions')) {
      if (o.method == 'POST' && p == 'transactions') return 'New entry: ${o.body?['description'] ?? ''}';
      if (o.method == 'DELETE') return 'Delete entry';
      if (p.endsWith('/category')) return 'Change category';
      if (p.endsWith('/note')) return 'Note';
      if (p.endsWith('/split')) return 'Split entry';
      if (p.endsWith('/duplicate')) return 'Duplicate entry';
      return 'Edit entry';
    }
    if (p.startsWith('transfers')) return 'Move money between accounts';
    if (p.startsWith('accounts')) return 'Account change';
    if (p.startsWith('goals')) return 'Savings goal';
    if (p.startsWith('budgets')) return 'Budget limit';
    return p;
  }

  @override
  Widget build(BuildContext context) {
    final k = Palette.of(context);
    return ValueListenableBuilder<int>(
      valueListenable: Outbox.instance.changes,
      builder: (context, _, __) {
        final ob = Outbox.instance;
        return Padding(
          padding: const EdgeInsets.all(20),
          child: SingleChildScrollView(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Row(children: [const Expanded(child: Text('Changes on this phone', style: TextStyle(fontSize: 20, fontWeight: FontWeight.w700))), IconButton(tooltip: 'Close', onPressed: () => Navigator.pop(context), icon: const Icon(Icons.close))]),
              if (ob.failed.isEmpty && ob.pending.isEmpty) const EmptyState('All synced'),
              if (ob.pending.isNotEmpty) ...[
                const SectionTitle('Waiting to sync'),
                for (final o in ob.pending) Padding(padding: const EdgeInsets.symmetric(vertical: 8), child: Row(children: [const Icon(Icons.schedule, size: 18), const SizedBox(width: 10), Expanded(child: Text(_label(o)))])),
                OutlinedButton.icon(onPressed: () => Outbox.instance.flush(), icon: const Icon(Icons.sync), label: const Text('Try now')),
              ],
              if (ob.failed.isNotEmpty) ...[
                const SectionTitle('Could not be saved'),
                for (final o in ob.failed)
                  Container(
                    margin: const EdgeInsets.only(top: 8), padding: const EdgeInsets.all(12), decoration: BoxDecoration(color: k.redSoft, border: Border.all(color: k.red)),
                    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      Text(_label(o), style: const TextStyle(fontWeight: FontWeight.w700)),
                      Text(o.error ?? 'The server refused this change.', style: TextStyle(color: k.red)),
                      Row(children: [TextButton(onPressed: () => Outbox.instance.retryFailed(o), child: const Text('Try again')), TextButton(onPressed: () => Outbox.instance.discard(o), child: const Text('Discard'))]),
                    ]),
                  ),
              ],
            ]),
          ),
        );
      },
    );
  }
}
