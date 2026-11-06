import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../theme.dart';

/// Slides a child up into place (no fade, so text is never half transparent over its card), staggered by [index].
/// Plays once when the widget first appears, the way the site's scroll-into-view reveal does.
class SlideUp extends StatefulWidget {
  final Widget child;
  final int index;
  final double distance;
  const SlideUp({super.key, required this.child, this.index = 0, this.distance = 44});
  @override
  State<SlideUp> createState() => _SlideUpState();
}

class _SlideUpState extends State<SlideUp> with SingleTickerProviderStateMixin {
  late final AnimationController _c = AnimationController(vsync: this, duration: const Duration(milliseconds: 800));
  @override
  void initState() {
    super.initState();
    Future.delayed(Duration(milliseconds: math.min(widget.index, 7) * 80), () { if (mounted) _c.forward(); });
  }

  @override
  void dispose() { _c.dispose(); super.dispose(); }

  @override
  Widget build(BuildContext context) {
    if (MediaQuery.of(context).disableAnimations) return widget.child;
    return AnimatedBuilder(
      animation: _c,
      child: widget.child,
      builder: (_, child) {
        final t = ease.transform(_c.value);
        return Opacity(opacity: _c.value == 0 ? 0 : 1, child: Transform.translate(offset: Offset(0, (1 - t) * widget.distance), child: child));
      },
    );
  }
}

/// Press feedback: the child lifts and shrinks a little while a finger is down (the site's hover and press reactions).
class Press extends StatefulWidget {
  final Widget child;
  final VoidCallback? onTap;
  const Press({super.key, required this.child, this.onTap});
  @override
  State<Press> createState() => _PressState();
}

class _PressState extends State<Press> {
  bool _down = false;
  @override
  Widget build(BuildContext context) => GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTapDown: (_) => setState(() => _down = true),
        onTapCancel: () => setState(() => _down = false),
        onTapUp: (_) => setState(() => _down = false),
        onTap: widget.onTap,
        child: AnimatedScale(scale: _down ? .965 : 1, duration: const Duration(milliseconds: 180), curve: ease, child: widget.child),
      );
}

/// Card shapes from the site: [hero] has a cut top-left corner, [tab] a folder-tab notch at the top right.
enum CardShape { hero, tab, plain }

class _ShapeClipper extends CustomClipper<Path> {
  final CardShape shape;
  final double r;
  const _ShapeClipper(this.shape, this.r);
  @override
  Path getClip(Size s) {
    final w = s.width, h = s.height;
    final p = Path();
    switch (shape) {
      case CardShape.hero:
        const cut = 30.0;
        p.moveTo(cut, 0); p.lineTo(w - r, 0); p.arcToPoint(Offset(w, r), radius: Radius.circular(r));
        p.lineTo(w, h - r); p.arcToPoint(Offset(w - r, h), radius: Radius.circular(r));
        p.lineTo(r, h); p.arcToPoint(Offset(0, h - r), radius: Radius.circular(r));
        p.lineTo(0, cut); p.close();
      case CardShape.tab:
        const tabW = 84.0, tabH = 20.0;
        p.moveTo(r, 0); p.lineTo(w - tabW - 22, 0); p.lineTo(w - tabW, tabH); p.lineTo(w - r, tabH);
        p.arcToPoint(Offset(w, tabH + r), radius: Radius.circular(r));
        p.lineTo(w, h - r); p.arcToPoint(Offset(w - r, h), radius: Radius.circular(r));
        p.lineTo(r, h); p.arcToPoint(Offset(0, h - r), radius: Radius.circular(r));
        p.lineTo(0, r); p.arcToPoint(Offset(r, 0), radius: Radius.circular(r)); p.close();
      case CardShape.plain:
        p.addRRect(RRect.fromRectAndRadius(Rect.fromLTWH(0, 0, w, h), Radius.circular(r)));
    }
    return p;
  }

  @override
  bool shouldReclip(_ShapeClipper old) => old.shape != shape || old.r != r;
}

/// A coloured card with one of the site's shapes. [stripes] draws the diagonal hatch in the top-right corner.
class ShapeCard extends StatelessWidget {
  final CardShape shape;
  final Color color;
  final Widget child;
  final bool stripes;
  final EdgeInsets padding;
  final double radius;
  const ShapeCard({super.key, required this.shape, required this.color, required this.child, this.stripes = false, this.radius = 26, this.padding = const EdgeInsets.fromLTRB(22, 22, 22, 22)});
  @override
  Widget build(BuildContext context) => SizedBox(width: double.infinity, child: ClipPath(
        clipper: _ShapeClipper(shape, radius),
        child: Container(
          color: color,
          padding: shape == CardShape.tab ? padding.copyWith(top: padding.top + 20) : padding,
          child: stripes ? Stack(children: [Positioned(right: -22, top: -22, child: CustomPaint(size: const Size(90, 60), painter: _Stripes())), child]) : child,
        ),
      ));
}

class _Stripes extends CustomPainter {
  @override
  void paint(Canvas c, Size s) {
    final p = Paint()..color = Colors.white.withValues(alpha: .45)..strokeWidth = 1.6;
    for (double x = -s.height; x < s.width + s.height; x += 11) {
      c.drawLine(Offset(x, s.height), Offset(x + s.height * .6, 0), p);
    }
  }

  @override
  bool shouldRepaint(covariant CustomPainter old) => false;
}
