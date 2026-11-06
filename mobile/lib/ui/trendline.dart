import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flutter/material.dart';

import '../format.dart';
import '../theme.dart';

/// Spend per month as one line against income (the Vestox graph). On open the line draws itself from January while a dot rides it
/// to the selected month; touch or drag a month and the dot glides there. Where spend rises above income the line glows red,
/// where it stays below income it glows green.
class TrendLine extends StatefulWidget {
  final List<Map<String, dynamic>> data;
  final String current;
  const TrendLine({super.key, required this.data, required this.current});
  @override
  State<TrendLine> createState() => _TrendLineState();
}

class _TrendLineState extends State<TrendLine> with TickerProviderStateMixin {
  static const _l = 18.0, _r = 18.0;
  late final AnimationController _draw = AnimationController(vsync: this, duration: const Duration(milliseconds: 2000));
  late final AnimationController _move = AnimationController(vsync: this, duration: const Duration(milliseconds: 650));
  late final AnimationController _pulse = AnimationController(vsync: this, duration: const Duration(milliseconds: 1400))..repeat(reverse: true);
  late int _now = _index(widget.current);
  int _from = 0, _at = 0;
  bool _ready = false;

  int _index(String m) {
    final i = widget.data.indexWhere((d) => d['month'] == m);
    return i < 0 ? widget.data.length - 1 : i;
  }

  @override
  void initState() {
    super.initState();
    _at = _now;
    _start();
  }

  void _start() {
    _ready = false;
    if (MediaQuery.maybeOf(context)?.disableAnimations ?? false) { _draw.value = 1; _ready = true; return; }
    _draw.forward(from: 0).whenComplete(() { if (mounted) setState(() => _ready = true); });
  }

  @override
  void didUpdateWidget(covariant TrendLine old) {
    super.didUpdateWidget(old);
    if (old.current != widget.current || old.data != widget.data) {
      _now = _index(widget.current); _at = _now; _from = _now;
      _draw.forward(from: 0).whenComplete(() { if (mounted) setState(() => _ready = true); });
    }
  }

  @override
  void dispose() { _draw.dispose(); _move.dispose(); _pulse.dispose(); super.dispose(); }

  void _pick(double dx, double w) {
    final n = widget.data.length;
    final i = (((dx - _l) / (w - _l - _r)) * (n - 1)).round().clamp(0, n - 1);
    if (i == _at || !_ready) return;
    setState(() { _from = _at; _at = i; });
    _move.forward(from: 0);
  }

  @override
  Widget build(BuildContext context) {
    final k = Palette.of(context);
    final d = widget.data;
    final spend = [for (final x in d) (x['spend_paise'] as int).toDouble()];
    final income = [for (final x in d) (x['income_paise'] as int).toDouble()];
    final peakI = spend.indexOf(spend.reduce(math.max));
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Semantics(
        label: 'Spend per month, ${d.length} months. Highest ${monthName(d[peakI]['month'] as String)} at ₹${rupeesShort(spend[peakI].round())}. Drag across to read each month.',
        child: LayoutBuilder(builder: (context, c) {
          final w = c.maxWidth;
          return GestureDetector(
            behavior: HitTestBehavior.opaque,
            onTapDown: (e) => _pick(e.localPosition.dx, w),
            onHorizontalDragUpdate: (e) => _pick(e.localPosition.dx, w),
            child: SizedBox(
              height: 210, width: w,
              child: CustomPaint(
                painter: _Painter(
                  k: k, spend: spend, income: income, months: [for (final x in d) (x['month'] as String).substring(5, 7)],
                  nowIdx: _now, at: _at, from: _from, ready: _ready,
                  draw: _draw, move: _move, pulse: _pulse,
                ),
              ),
            ),
          );
        }),
      ),
      const SizedBox(height: 6),
      Wrap(spacing: 16, runSpacing: 4, children: [
        _Key(k.ink, 'Spend'), _Key(k.orange, 'Income'), _Key(k.red, 'Above income'), _Key(k.ok, 'Below income'),
      ]),
    ]);
  }
}

class _Key extends StatelessWidget {
  final Color c;
  final String t;
  const _Key(this.c, this.t);
  @override
  Widget build(BuildContext context) => Row(mainAxisSize: MainAxisSize.min, children: [
        Container(width: 14, height: 3, decoration: BoxDecoration(color: c, borderRadius: BorderRadius.circular(2))),
        const SizedBox(width: 6),
        Text(t, style: TextStyle(fontSize: 12, color: Palette.of(context).muted)),
      ]);
}

class _Painter extends CustomPainter {
  final Palette k;
  final List<double> spend, income;
  final List<String> months;
  final int nowIdx, at, from;
  final bool ready;
  final Animation<double> draw, move, pulse;
  _Painter({required this.k, required this.spend, required this.income, required this.months, required this.nowIdx, required this.at, required this.from,
      required this.ready, required this.draw, required this.move, required this.pulse})
      : super(repaint: Listenable.merge([draw, move, pulse]));

  static const _l = 18.0, _r = 18.0, _t = 36.0, _b = 28.0;

  Path _curve(List<double> v, double Function(int) x, double Function(double) y) {
    final p = Path()..moveTo(x(0), y(v[0]));
    for (var i = 1; i < v.length; i++) {
      final mx = (x(i - 1) + x(i)) / 2;
      p.cubicTo(mx, y(v[i - 1]), mx, y(v[i]), x(i), y(v[i]));
    }
    return p;
  }

  @override
  void paint(Canvas canvas, Size s) {
    final n = spend.length;
    final mx = math.max(1.0, [...spend, ...income].reduce(math.max));
    double x(int i) => _l + (s.width - _l - _r) * i / math.max(n - 1, 1);
    double y(double v) => _t + (s.height - _t - _b) * (1 - v / mx);
    final base = s.height - _b;

    // guides
    final guide = Paint()..color = k.ruleStrong..strokeWidth = 1;
    for (final f in [0.0, .5, 1.0]) {
      final yy = y(mx * f);
      for (double xx = _l; xx < s.width - _r; xx += 9) { canvas.drawLine(Offset(xx, yy), Offset(xx + 3, yy), guide); }
    }

    final sp = _curve(spend, x, y), inc = _curve(income, x, y);
    final dt = ease.transform(draw.value);

    // tints under the spend line, split by the income line
    final area = Path.from(sp)..lineTo(x(n - 1), base)..lineTo(x(0), base)..close();
    final above = Path.from(inc)..lineTo(x(n - 1), 0)..lineTo(x(0), 0)..close();
    final below = Path.from(inc)..lineTo(x(n - 1), s.height)..lineTo(x(0), s.height)..close();
    final reveal = Rect.fromLTWH(0, 0, s.width * dt, s.height);
    canvas.save();
    canvas.clipRect(reveal);
    canvas.save(); canvas.clipPath(above); canvas.drawPath(area, Paint()..color = k.red.withValues(alpha: .16)); canvas.restore();
    canvas.save(); canvas.clipPath(below); canvas.drawPath(area, Paint()..color = k.ok.withValues(alpha: .13)); canvas.restore();
    canvas.restore();

    // lines draw themselves
    Path part(Path p) {
      final out = Path();
      for (final m in p.computeMetrics()) { out.addPath(m.extractPath(0, m.length * draw.value.clamp(0, 1)), Offset.zero); }
      return out;
    }

    final stroke = Paint()..style = PaintingStyle.stroke..strokeCap = StrokeCap.round..strokeJoin = StrokeJoin.round;
    final incPart = part(inc), spPart = part(sp);
    canvas.drawPath(incPart, stroke..color = k.orange..strokeWidth = 1.8);
    canvas.drawPath(spPart, stroke..color = k.ink..strokeWidth = 3);
    final glow = 3 + 6 * Curves.easeInOut.transform(pulse.value);
    void overlay(Path clip, Color c) {
      canvas.save();
      canvas.clipPath(clip);
      canvas.drawPath(spPart, Paint()..style = PaintingStyle.stroke..strokeCap = StrokeCap.round..strokeWidth = 5..color = c.withValues(alpha: .55)..maskFilter = MaskFilter.blur(BlurStyle.normal, glow));
      canvas.drawPath(spPart, stroke..color = c..strokeWidth = 3.2);
      canvas.restore();
    }
    overlay(above, k.red);
    overlay(below, k.ok);

    // month labels
    for (var i = 0; i < n; i++) {
      final m = const ['J', 'F', 'M', 'A', 'M', 'J', 'J', 'A', 'S', 'O', 'N', 'D'][int.parse(months[i]) - 1];
      final sel = i == at;
      final tp = TextPainter(text: TextSpan(text: m, style: TextStyle(fontSize: 11, color: sel ? k.ink : k.muted, fontWeight: sel ? FontWeight.w800 : FontWeight.w400)), textDirection: TextDirection.ltr)..layout();
      tp.paint(canvas, Offset(x(i) - tp.width / 2, s.height - tp.height - 4));
    }

    // dot: rides the line while it draws, glides to a picked month afterwards
    final dotX = ready
        ? ui.lerpDouble(x(from), x(at), ease.transform(move.value))!
        : ui.lerpDouble(x(0), x(nowIdx), dt)!;
    final pm = sp.computeMetrics().first;
    var lo = 0.0, hi = pm.length;
    for (var i = 0; i < 26; i++) { final mid = (lo + hi) / 2; if (pm.getTangentForOffset(mid)!.position.dx < dotX) { lo = mid; } else { hi = mid; } }
    final p = pm.getTangentForOffset(hi)!.position;
    canvas.drawLine(Offset(p.dx, _t - 8), Offset(p.dx, base), Paint()..color = k.ruleStrong..strokeWidth = 1);
    canvas.drawCircle(p, 10, Paint()..color = k.orange.withValues(alpha: .18 + .12 * pulse.value));
    canvas.drawCircle(p, 7, Paint()..color = k.sheet);
    canvas.drawCircle(p, 7, Paint()..style = PaintingStyle.stroke..strokeWidth = 2.5..color = k.ink);
    canvas.drawCircle(p, 3.2, Paint()..color = k.orange);

    if (ready || draw.value >= 1) {
      final over = spend[at] > income[at];
      final tp = TextPainter(
        text: TextSpan(text: '₹${rupeesShort(spend[at].round())}${over ? ' · over income' : ''}', style: TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: over ? k.red : k.ink)),
        textDirection: TextDirection.ltr,
      )..layout();
      final lx = (p.dx - tp.width / 2).clamp(2.0, s.width - tp.width - 2);
      tp.paint(canvas, Offset(lx, math.max(p.dy - 32, 2)));
    }
  }

  @override
  bool shouldRepaint(covariant _Painter o) => o.at != at || o.from != from || o.ready != ready || o.k != k || o.nowIdx != nowIdx || o.spend != spend;
}
