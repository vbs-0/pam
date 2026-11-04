import 'package:flutter/material.dart';

import '../api.dart';
import '../format.dart';
import '../theme.dart';
import '../ui/widgets.dart';

class Folio extends StatefulWidget {
  const Folio({super.key});
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
    ]);
    return {'summary': r[0], 'budgets': r[1], 'insights': r[2], 'profile': r[3]};
  }

  @override
  Widget build(BuildContext context) {
    final k = Palette.of(context);
    return RefreshIndicator(
      onRefresh: () async => setState(() {}),
      child: ListView(padding: const EdgeInsets.fromLTRB(16, 16, 16, 24), children: [
        const Text('Folio', style: TextStyle(fontSize: 26, fontWeight: FontWeight.w700, letterSpacing: -.4)),
        const SizedBox(height: 12),
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
            final spend = s['spend_paise'] as int, naive = s['naive_spend_paise'] as int, income = s['income_paise'] as int;
            final rate = s['savings_rate'] as num?;
            final lines = ((b['lines'] as List).cast<Map<String, dynamic>>())
              ..sort((x, y) => ((y['ratio'] as num?) ?? -1).compareTo((x['ratio'] as num?) ?? -1));
            final empty = spend == 0 && income == 0 && naive == 0;
            return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              if (profile['sample'] == true) Padding(padding: const EdgeInsets.only(top: 10), child: Stamp('Sample household · read-only', k.blue)),
              if (empty) const EmptyState('Nothing written for this month yet', hint: 'Add an account in Books, then your first entry.') else ...[
                Container(
                  margin: const EdgeInsets.only(top: 12),
                  padding: const EdgeInsets.symmetric(vertical: 16),
                  decoration: BoxDecoration(border: Border.symmetric(horizontal: BorderSide(color: k.ruleStrong))),
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Text('TRUE SPEND', style: TextStyle(color: k.muted, fontWeight: FontWeight.w800, fontSize: 12, letterSpacing: 1)),
                    const SizedBox(height: 4),
                    DefaultTextStyle.merge(style: const TextStyle(fontSize: 40, fontWeight: FontWeight.w700, letterSpacing: -1), child: _BigMoney(spend, k.blue)),
                    if (naive > spend) Padding(
                      padding: const EdgeInsets.only(top: 8),
                      child: Wrap(crossAxisAlignment: WrapCrossAlignment.center, spacing: 6, children: [
                        Text('A plain ledger shows', style: TextStyle(color: k.muted)),
                        Money(naive, struck: true, big: true),
                        Text('· PAM leaves out ${inr(naive - spend)}', style: TextStyle(color: k.muted)),
                      ]),
                    ),
                    const SizedBox(height: 14),
                    Row(children: [
                      Expanded(child: _Fig('INCOME', Money(income, big: true))),
                      Expanded(child: _Fig('KEPT', Text(rate == null ? '—' : '${(rate * 100).round()}%', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 18, color: rate != null && rate < 0 ? k.red : k.ink)))),
                    ]),
                  ]),
                ),
              ],
              const SectionTitle('Against budget'),
              if (lines.isEmpty) const EmptyState('No budgets or spending this month') else
                for (final l in lines.take(8)) _BudgetRow(l),
              if (ins.isNotEmpty) ...[
                const SectionTitle('Margin notes'),
                for (final i in ins.take(5)) _Note(i),
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
  const _Fig(this.label, this.child);
  @override
  Widget build(BuildContext context) => Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(label, style: TextStyle(color: Palette.of(context).muted, fontWeight: FontWeight.w800, fontSize: 11, letterSpacing: 1)),
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
      padding: const EdgeInsets.symmetric(vertical: 10),
      decoration: BoxDecoration(border: Border(bottom: BorderSide(color: k.rule))),
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
      padding: const EdgeInsets.symmetric(vertical: 10),
      decoration: BoxDecoration(border: Border(bottom: BorderSide(color: k.rule))),
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Container(margin: const EdgeInsets.only(top: 6, right: 10), width: 8, height: 8, decoration: BoxDecoration(color: c, shape: BoxShape.circle)),
        Expanded(child: Text(i['message'] as String)),
      ]),
    );
  }
}
