import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../api.dart';
import '../theme.dart';

/// First-run walkthrough: four swipeable slides, then the caller opens the setup guide.
class Walkthrough extends StatefulWidget {
  final VoidCallback onDone;
  const Walkthrough({super.key, required this.onDone});
  @override
  State<Walkthrough> createState() => _WalkthroughState();
}

class _Slide {
  final IconData icon;
  final String title, body;
  const _Slide(this.icon, this.title, this.body);
}

const _slides = [
  _Slide(Icons.insights, 'Where did the month go?',
      'PAM reads your bank, card and UPI entries and tells you what you really spent, what repeats and whether you are inside budget.'),
  _Slide(Icons.filter_alt_outlined, 'True spend, not noise',
      'Money you move between your own accounts, refunds and reversed payments are struck out, so a transfer never looks like spending.'),
  _Slide(Icons.repeat, 'Budgets and repeats',
      'Set a monthly limit per category. PAM finds the salary, rent, EMIs and subscriptions that repeat and flags one that goes missing.'),
  _Slide(Icons.lock_outline, 'Your own register',
      'Add savings accounts, credit cards and UPI apps like PhonePe, Google Pay and Paytm. Everything stays in your household.'),
];

class _WalkthroughState extends State<Walkthrough> {
  final _c = PageController();
  int _i = 0;

  @override
  void dispose() { _c.dispose(); super.dispose(); }

  void _next() {
    HapticFeedback.selectionClick();
    if (_i == _slides.length - 1) { widget.onDone(); return; }
    _c.nextPage(duration: const Duration(milliseconds: 320), curve: Curves.easeOutCubic);
  }

  @override
  Widget build(BuildContext context) {
    final k = Palette.of(context);
    final last = _i == _slides.length - 1;
    return Scaffold(
      body: SafeArea(
        child: Column(children: [
          Align(
            alignment: Alignment.centerRight,
            child: AnimatedOpacity(
              opacity: last ? 0 : 1, duration: const Duration(milliseconds: 200),
              child: TextButton(onPressed: last ? null : widget.onDone, child: const Text('Skip')),
            ),
          ),
          Expanded(
            child: PageView.builder(
              controller: _c,
              itemCount: _slides.length,
              onPageChanged: (v) { HapticFeedback.selectionClick(); setState(() => _i = v); },
              itemBuilder: (_, i) {
                final s = _slides[i];
                return Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 28),
                  child: TweenAnimationBuilder<double>(
                    key: ValueKey(i == _i),
                    tween: Tween(begin: 0, end: 1), duration: const Duration(milliseconds: 520), curve: Curves.easeOutCubic,
                    builder: (_, t, child) => Opacity(opacity: t, child: Transform.translate(offset: Offset(0, 24 * (1 - t)), child: child)),
                    child: Column(mainAxisAlignment: MainAxisAlignment.center, crossAxisAlignment: CrossAxisAlignment.start, children: [
                      Container(
                        width: 84, height: 84,
                        decoration: BoxDecoration(color: k.blueSoft, border: Border.all(color: k.ruleStrong), borderRadius: BorderRadius.circular(4)),
                        child: Icon(s.icon, size: 42, color: k.blue),
                      ),
                      const SizedBox(height: 28),
                      Text(s.title, style: const TextStyle(fontSize: 30, fontWeight: FontWeight.w700, letterSpacing: -.6, height: 1.1)),
                      const SizedBox(height: 14),
                      Text(s.body, style: TextStyle(fontSize: 17, height: 1.45, color: k.muted)),
                    ]),
                  ),
                );
              },
            ),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(28, 8, 28, 24),
            child: Row(children: [
              for (var d = 0; d < _slides.length; d++)
                AnimatedContainer(
                  duration: const Duration(milliseconds: 250), curve: Curves.easeOut,
                  margin: const EdgeInsets.only(right: 6), height: 6, width: d == _i ? 26 : 6,
                  decoration: BoxDecoration(color: d == _i ? k.blue : k.ruleStrong, borderRadius: BorderRadius.circular(3)),
                ),
              const Spacer(),
              FilledButton(onPressed: _next, child: Text(last ? 'Set up my books' : 'Next')),
            ]),
          ),
        ]),
      ),
    );
  }
}

/// "Getting started": three steps that tick themselves off from the real data, shown on the Folio until done.
class SetupGuide extends StatefulWidget {
  final void Function(int tab) onGo;
  final VoidCallback? onAllDone;
  const SetupGuide({super.key, required this.onGo, this.onAllDone});
  @override
  State<SetupGuide> createState() => _SetupGuideState();
}

class _SetupGuideState extends State<SetupGuide> {
  late final Future<List<bool>> _f = _load();

  Future<List<bool>> _load() async {
    final r = await Future.wait([Api.instance.get('/me/accounts'), Api.instance.get('/me/transactions', {'limit': '1'})]);
    final accounts = (r[0] as List).isNotEmpty;
    final entries = ((r[1] as Map)['items'] as List).isNotEmpty;
    return [accounts, entries, accounts && entries];
  }

  @override
  Widget build(BuildContext context) {
    final k = Palette.of(context);
    return FutureBuilder<List<bool>>(
      future: _f,
      builder: (context, s) {
        final done = s.data;
        if (done == null || (done[0] && done[1])) return const SizedBox.shrink();
        const steps = [
          (Icons.account_balance_wallet_outlined, 'Add an account', 'A savings account, credit card or UPI app.', 3),
          (Icons.edit_note, 'Write your first entry', 'A payment, a salary credit or a bill.', 1),
        ];
        final count = done.take(2).where((x) => x).length;
        return Container(
          margin: const EdgeInsets.only(top: 12),
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(color: k.blueSoft, border: Border.all(color: k.ruleStrong)),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Row(children: [
              Expanded(child: Text('GETTING STARTED', style: TextStyle(color: k.blue, fontWeight: FontWeight.w800, fontSize: 12, letterSpacing: 1))),
              Text('$count of 2', style: TextStyle(color: k.muted, fontWeight: FontWeight.w700)),
            ]),
            const SizedBox(height: 8),
            TweenAnimationBuilder<double>(
              tween: Tween(begin: 0, end: count / 2), duration: const Duration(milliseconds: 500), curve: Curves.easeOut,
              builder: (_, v, __) => LinearProgressIndicator(value: v, minHeight: 4, backgroundColor: k.rule, color: k.blue),
            ),
            const SizedBox(height: 6),
            for (var i = 0; i < steps.length; i++)
              InkWell(
                onTap: done[i] ? null : () { HapticFeedback.selectionClick(); widget.onGo(steps[i].$4); },
                child: Padding(
                  padding: const EdgeInsets.symmetric(vertical: 10),
                  child: Row(children: [
                    AnimatedSwitcher(
                      duration: const Duration(milliseconds: 300),
                      child: Icon(done[i] ? Icons.check_circle : steps[i].$1, key: ValueKey(done[i]), color: done[i] ? k.green : k.blue),
                    ),
                    const SizedBox(width: 12),
                    Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      Text('${i + 1}. ${steps[i].$2}', style: TextStyle(fontWeight: FontWeight.w700, decoration: done[i] ? TextDecoration.lineThrough : null)),
                      Text(steps[i].$3, style: TextStyle(color: k.muted, fontSize: 13)),
                    ])),
                    if (!done[i]) Icon(Icons.chevron_right, color: k.muted),
                  ]),
                ),
              ),
          ]),
        );
      },
    );
  }
}
