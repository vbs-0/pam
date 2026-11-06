import 'package:flutter/material.dart';

import '../api.dart';
import '../format.dart';
import '../theme.dart';
import '../ui/motion.dart';
import '../ui/trendline.dart';
import '../ui/widgets.dart';
import 'onboarding.dart';

class Folio extends StatefulWidget {
  final void Function(int tab) onGo;
  const Folio({super.key, required this.onGo});
  @override
  State<Folio> createState() => _FolioState();
}

class _FolioState extends State<Folio> {
  String _month = currentMonth();

  Future<Map<String, dynamic>> _load() async {
    final api = Api.instance;
    final r = await Future.wait([
      api.get('/me/summary', {'month': _month}),
      api.get('/me/budgets', {'month': _month}),
      api.get('/me/insights', {'month': _month}),
      api.get('/me/profile'),
      api.get('/me/trend', {'months': '12'}),
    ]);
    return {'summary': r[0], 'budgets': r[1], 'insights': r[2], 'profile': r[3], 'trend': r[4]};
  }

  @override
  Widget build(BuildContext context) {
    final k = Palette.of(context);
    return RefreshIndicator(
      onRefresh: () async => setState(() {}),
      child: ListView(padding: const EdgeInsets.fromLTRB(16, 16, 16, 24), children: [
        const SlideUp(child: Text('FOLIO', style: TextStyle(fontFamily: serif, fontSize: 64, height: .95, letterSpacing: -.5))),
        const SizedBox(height: 14),
        MonthBar(_month, (m) => setState(() => _month = m)),
        const SizedBox(height: 8),
        Loader<Map<String, dynamic>>(
          key: ValueKey(_month),
          load: _load,
          rows: 6,
          builder: (context, d) {
            final s = d['summary'] as Map<String, dynamic>;
            final b = d['budgets'] as Map<String, dynamic>;
            final ins = (d['insights'] as List).cast<Map<String, dynamic>>();
            final profile = d['profile'] as Map<String, dynamic>;
            final trend = (d['trend'] as List).cast<Map<String, dynamic>>();
            final spend = s['spend_paise'] as int, naive = s['naive_spend_paise'] as int, income = s['income_paise'] as int;
            final rate = s['savings_rate'] as num?;
            final lines = ((b['lines'] as List).cast<Map<String, dynamic>>())
              ..sort((x, y) => ((y['ratio'] as num?) ?? -1).compareTo((x['ratio'] as num?) ?? -1));
            final empty = spend == 0 && income == 0 && naive == 0;
            return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              if (profile['sample'] == true) Padding(padding: const EdgeInsets.only(top: 10), child: Stamp('Sample household · read-only', k.blue)) else SetupGuide(onGo: widget.onGo),
              if (empty) const EmptyState('Nothing written for this month yet', hint: 'Add an account in Books, then your first entry.') else ...[
                const SizedBox(height: 14),
                SlideUp(
                  child: ShapeCard(
                    shape: CardShape.hero, color: k.orange, stripes: true,
                    child: DefaultTextStyle.merge(
                      style: const TextStyle(color: Colors.white),
                      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        const Text('TRUE SPEND', style: TextStyle(fontWeight: FontWeight.w800, fontSize: 12, letterSpacing: 1.2)),
                        const SizedBox(height: 4),
                        DefaultTextStyle.merge(style: const TextStyle(fontFamily: serif, fontSize: 50, height: 1.05), child: CountUp(spend, (v) => _BigMoney(v, Colors.white))),
                        if (naive > spend) Padding(
                          padding: const EdgeInsets.only(top: 8),
                          child: Text('A plain ledger shows ${inr(naive)}. PAM leaves out ${inr(naive - spend)}.', style: const TextStyle(height: 1.35)),
                        ),
                      ]),
                    ),
                  ),
                ),
                const SizedBox(height: 12),
                Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Expanded(child: SlideUp(index: 1, child: ShapeCard(shape: CardShape.tab, color: k.sand, radius: 22, padding: const EdgeInsets.fromLTRB(16, 14, 16, 16),
                      child: _Fig('INCOME', CountUp(income, (v) => Text(inr(v), style: TextStyle(fontFamily: serif, fontSize: 24, color: k.ink))))))),
                  const SizedBox(width: 12),
                  Expanded(child: SlideUp(index: 2, child: ShapeCard(shape: CardShape.tab, color: const Color(0xFF191919), radius: 22, padding: const EdgeInsets.fromLTRB(16, 14, 16, 16),
                      child: _Fig('KEPT', rate == null ? const Text('—', style: TextStyle(fontFamily: serif, fontSize: 24, color: Color(0xFFFCF9EB))) : CountUp((rate * 100).round(), (v) => Text('$v%', style: TextStyle(fontFamily: serif, fontSize: 24, color: rate < 0 ? const Color(0xFFFF7A52) : const Color(0xFFFCF9EB)))), light: true)))),
                ]),
                if (trend.length >= 2) ...[
                  const SectionTitle('Twelve months'),
                  SlideUp(index: 3, child: Container(
                    padding: const EdgeInsets.fromLTRB(12, 14, 12, 12),
                    decoration: BoxDecoration(color: k.sheet, borderRadius: BorderRadius.circular(24), border: Border.all(color: k.rule)),
                    child: TrendLine(data: trend, current: _month),
                  )),
                ],
              ],
              const SectionTitle('Against budget'),
              if (lines.isEmpty) const EmptyState('No budgets or spending this month') else
                for (final (i, l) in lines.take(8).indexed) SlideUp(index: i, child: _BudgetRow(l)),
              if (ins.isNotEmpty) ...[
                const SectionTitle('Margin notes'),
                for (final (n, i) in ins.take(5).indexed) SlideUp(index: n, child: _Note(i)),
              ],
            ]);
          },
        ),
      ]),
    );
  }
}

class _BigMoney extends StatelessWidget {
  final int paise;
  final Color color;
  const _BigMoney(this.paise, this.color);
  @override
  Widget build(BuildContext context) {
    final t = inr(paise);
    final dot = t.lastIndexOf('.');
    final base = DefaultTextStyle.of(context).style.copyWith(color: color, fontFeatures: tabular);
    return Semantics(label: t.replaceAll('₹', 'rupees '), child: ExcludeSemantics(child: Text.rich(TextSpan(children: [TextSpan(text: t.substring(0, dot), style: base), TextSpan(text: t.substring(dot), style: base.copyWith(color: color.withValues(alpha: .6)))]))));
  }
}

class _Fig extends StatelessWidget {
  final String label;
  final Widget child;
  final bool light;
  const _Fig(this.label, this.child, {this.light = false});
  @override
  Widget build(BuildContext context) => Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(label, style: TextStyle(color: light ? const Color(0xFFBDB8A8) : Palette.of(context).muted, fontWeight: FontWeight.w800, fontSize: 11, letterSpacing: 1)),
        const SizedBox(height: 2),
        child,
      ]);
}

class _BudgetRow extends StatelessWidget {
  final Map<String, dynamic> l;
  const _BudgetRow(this.l);
  @override
  Widget build(BuildContext context) {
    final k = Palette.of(context);
    final status = l['status'] as String;
    final budget = l['budget_paise'] as int?;
    return Container(
      margin: const EdgeInsets.only(top: 10),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(color: k.sheet, borderRadius: BorderRadius.circular(22), border: Border.all(color: k.rule)),
      child: Column(children: [
        Row(children: [
          Expanded(child: Text((l['category_name'] ?? titleCase(l['category_code'] as String)) as String, style: const TextStyle(fontWeight: FontWeight.w600))),
          statusStamp(context, status),
        ]),
        const SizedBox(height: 6),
        LimitBar(actual: l['actual_paise'] as int, budget: budget, status: status),
        const SizedBox(height: 6),
        Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
          Money(l['actual_paise'] as int, color: status == 'OVER' ? k.red : null),
          if (budget != null) Text('of ${inr(budget)}', style: TextStyle(color: k.muted, fontFeatures: tabular)),
        ]),
      ]),
    );
  }
}

class _Note extends StatelessWidget {
  final Map<String, dynamic> i;
  const _Note(this.i);
  @override
  Widget build(BuildContext context) {
    final k = Palette.of(context);
    final c = i['severity'] == 'ALERT' ? k.red : i['severity'] == 'WARN' ? k.amber : k.muted;
    return Container(
      margin: const EdgeInsets.only(top: 10),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(color: k.sheet, borderRadius: BorderRadius.circular(22), border: Border.all(color: k.rule)),
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Container(margin: const EdgeInsets.only(top: 6, right: 10), width: 8, height: 8, decoration: BoxDecoration(color: c, shape: BoxShape.circle)),
        Expanded(child: Text(i['message'] as String)),
      ]),
    );
  }
}

