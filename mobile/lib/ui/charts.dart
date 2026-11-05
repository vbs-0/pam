import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../format.dart';
import '../theme.dart';

/// Categorical colours in fixed order (the same ramp the web console uses); a 9th slice folds into "Other".
const _lightRamp = [Color(0xFF1E3A8A), Color(0xFFC8102E), Color(0xFF14633F), Color(0xFF8A4B08), Color(0xFF5B3FA6), Color(0xFF0E7490), Color(0xFFA1306B), Color(0xFF52606D), Color(0xFF8A94A6)];
const _darkRamp = [Color(0xFF8FB0FF), Color(0xFFFF6B7E), Color(0xFF5CCF9B), Color(0xFFF2A33A), Color(0xFFB79CFF), Color(0xFF5FD0E8), Color(0xFFF08AB9), Color(0xFFA9B6C9), Color(0xFF7C879B)];
Color sliceColor(BuildContext c, int i) => (Theme.of(c).brightness == Brightness.dark ? _darkRamp : _lightRamp)[i.clamp(0, 8)];

class Slice {
  final String key, label;
  final int value;
  const Slice(this.key, this.label, this.value);
}

/// Donut with an animated sweep; tapping a slice reports its key.
class Donut extends StatefulWidget {
  final List<Slice> slices;
  final Widget centre;
  final ValueChanged<String>? onPick;
  const Donut({super.key, required this.slices, required this.centre, this.onPick});
  @override
  State<Donut> createState() => _DonutState();
}

class _DonutState extends State<Donut> with SingleTickerProviderStateMixin {
  late final AnimationController _c = AnimationController(vsync: this, duration: const Duration(milliseconds: 800))..forward();
  @override
  void dispose() { _c.dispose(); super.dispose(); }

  List<Slice> get _folded {
    final s = [...widget.slices]..sort((a, b) => b.value.compareTo(a.value));
    if (s.length <= 8) return s;
    final rest = s.skip(7).fold<int>(0, (t, e) => t + e.value);
    return [...s.take(7), Slice('_other', 'Other', rest)];
  }

  @override
  Widget build(BuildContext context) {
    final k = Palette.of(context);
    final s = _folded;
    final total = s.fold<int>(0, (t, e) => t + e.value);
    final reduce = MediaQuery.of(context).disableAnimations;
    if (reduce) _c.value = 1;
    return Column(children: [
      SizedBox(
        height: 210,
        child: LayoutBuilder(builder: (context, box) {
          final side = math.min(box.maxWidth, 210.0);
          return Center(
            child: SizedBox(
              width: side, height: side,
              child: GestureDetector(
                onTapUp: (d) {
                  if (widget.onPick == null || total == 0) return;
                  final c = Offset(side / 2, side / 2), v = d.localPosition - c;
                  final r = v.distance;
                  if (r < side * .27 || r > side / 2) return;
                  var a = math.atan2(v.dy, v.dx) + math.pi / 2;
                  if (a < 0) a += 2 * math.pi;
                  var acc = 0.0;
                  for (final e in s) {
                    acc += e.value / total * 2 * math.pi;
                    if (a <= acc) { if (e.key != '_other') widget.onPick!(e.key); return; }
                  }
                },
                child: AnimatedBuilder(
                  animation: _c,
                  builder: (_, __) => CustomPaint(
                    painter: _DonutPainter(s, total, Curves.easeOutCubic.transform(_c.value), [for (var i = 0; i < s.length; i++) sliceColor(context, i)], k.sheet),
                    child: Center(child: widget.centre),
                  ),
                ),
              ),
            ),
          );
        }),
      ),
      const SizedBox(height: 8),
      for (var i = 0; i < s.length; i++)
        InkWell(
          onTap: widget.onPick == null || s[i].key == '_other' ? null : () => widget.onPick!(s[i].key),
          child: Padding(
            padding: const EdgeInsets.symmetric(vertical: 7),
            child: Row(children: [
              Container(width: 12, height: 12, color: sliceColor(context, i)),
              const SizedBox(width: 10),
              Expanded(child: Text(s[i].label, overflow: TextOverflow.ellipsis)),
              Text('${total == 0 ? 0 : (s[i].value / total * 100).round()}%', style: TextStyle(color: k.muted, fontFeatures: tabular)),
              const SizedBox(width: 12),
              Text(inr(s[i].value), style: const TextStyle(fontWeight: FontWeight.w600, fontFeatures: tabular)),
            ]),
          ),
        ),
    ]);
  }
}

class _DonutPainter extends CustomPainter {
  final List<Slice> s;
  final int total;
  final double t;
  final List<Color> colors;
  final Color gap;
  _DonutPainter(this.s, this.total, this.t, this.colors, this.gap);
  @override
  void paint(Canvas canvas, Size size) {
    if (total == 0) return;
    final rect = Offset.zero & size;
    final w = size.width * .22;
    final r = rect.deflate(w / 2);
    var start = -math.pi / 2;
    for (var i = 0; i < s.length; i++) {
      final sweep = s[i].value / total * 2 * math.pi * t;
      canvas.drawArc(r, start, sweep, false, Paint()..color = colors[i]..style = PaintingStyle.stroke..strokeWidth = w);
      canvas.drawArc(r, start, .012, false, Paint()..color = gap..style = PaintingStyle.stroke..strokeWidth = w + 2);
      start += sweep;
    }
  }
  @override
  bool shouldRepaint(_DonutPainter o) => o.t != t || o.total != total || o.s != s;
}

/// Horizontal bars with a value on the right. Tapping a row reports its key.
class BarList extends StatelessWidget {
  final List<({String key, String label, String? sub, int value})> rows;
  final ValueChanged<String>? onPick;
  const BarList({super.key, required this.rows, this.onPick});
  @override
  Widget build(BuildContext context) {
    final k = Palette.of(context);
    final max = rows.fold<int>(1, (m, r) => math.max(m, r.value));
    return Column(children: [
      for (final r in rows)
        InkWell(
          onTap: onPick == null ? null : () => onPick!(r.key),
          child: Padding(
            padding: const EdgeInsets.symmetric(vertical: 7),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Row(children: [
                Expanded(child: Text(r.label, overflow: TextOverflow.ellipsis, style: const TextStyle(fontWeight: FontWeight.w600))),
                Text(inr(r.value), style: const TextStyle(fontWeight: FontWeight.w600, fontFeatures: tabular)),
              ]),
              const SizedBox(height: 4),
              TweenAnimationBuilder<double>(
                tween: Tween(begin: 0, end: r.value / max),
                duration: const Duration(milliseconds: 600),
                curve: Curves.easeOutCubic,
                builder: (_, v, __) => Align(alignment: Alignment.centerLeft, child: FractionallySizedBox(widthFactor: v.clamp(.01, 1), child: Container(height: 8, decoration: BoxDecoration(color: k.blue, borderRadius: const BorderRadius.horizontal(right: Radius.circular(3)))))),
              ),
              if (r.sub != null) Padding(padding: const EdgeInsets.only(top: 2), child: Text(r.sub!, style: TextStyle(color: k.muted, fontSize: 12))),
            ]),
          ),
        ),
    ]);
  }
}

/// Vertical bars with labels under them; the tallest is highlighted. Used for weekday pattern and 12-month trend.
class ColumnBars extends StatelessWidget {
  final List<({String label, int value, int? line})> cols;
  final double height;
  const ColumnBars({super.key, required this.cols, this.height = 150});
  @override
  Widget build(BuildContext context) {
    final k = Palette.of(context);
    final max = cols.fold<int>(1, (m, c) => math.max(m, math.max(c.value, c.line ?? 0)));
    final top = cols.fold<int>(0, (m, c) => math.max(m, c.value));
    return SizedBox(
      height: height + 34,
      child: Row(crossAxisAlignment: CrossAxisAlignment.end, children: [
        for (final c in cols)
          Expanded(
            child: Tooltip(
              message: '${c.label}: ${inr(c.value)}',
              child: Column(mainAxisAlignment: MainAxisAlignment.end, children: [
                SizedBox(
                  height: height,
                  child: Stack(alignment: Alignment.bottomCenter, children: [
                    TweenAnimationBuilder<double>(
                      tween: Tween(begin: 0, end: c.value / max),
                      duration: const Duration(milliseconds: 650),
                      curve: Curves.easeOutCubic,
                      builder: (_, v, __) => FractionallySizedBox(heightFactor: v.clamp(0.01, 1), widthFactor: .62, child: Container(decoration: BoxDecoration(color: c.value == top && top > 0 ? k.blue : k.blue.withValues(alpha: .55), borderRadius: const BorderRadius.vertical(top: Radius.circular(3))))),
                    ),
                    if (c.line != null && c.line! > 0) Positioned(bottom: c.line! / max * height, left: 0, right: 0, child: Container(height: 2, color: k.green)),
                  ]),
                ),
                const SizedBox(height: 6),
                Text(c.label, style: TextStyle(color: k.muted, fontSize: 11), maxLines: 1, overflow: TextOverflow.clip),
              ]),
            ),
          ),
      ]),
    );
  }
}

/// Up/down change against a previous figure. Spending going down is good (green), up is red.
class Delta extends StatelessWidget {
  final int paise;
  const Delta(this.paise, {super.key});
  @override
  Widget build(BuildContext context) {
    final k = Palette.of(context);
    if (paise == 0) return Text('no change', style: TextStyle(color: k.muted));
    final up = paise > 0;
    return Text('${up ? '▲' : '▼'} ${inr(paise.abs())}', style: TextStyle(color: up ? k.red : k.green, fontWeight: FontWeight.w700, fontFeatures: tabular));
  }
}
