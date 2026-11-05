import 'package:flutter/material.dart';

import '../api.dart';
import '../format.dart';
import '../theme.dart';
import '../ui/charts.dart';
import '../ui/widgets.dart';

/// Where the money went: categories against last month, top payees, weekday rhythm and a year of months.
class SpendScreen extends StatefulWidget {
  final void Function(String filter) onOpenEntries;
  const SpendScreen({super.key, required this.onOpenEntries});
  @override
  State<SpendScreen> createState() => _SpendScreenState();
}

class _SpendScreenState extends State<SpendScreen> {
  String _month = currentMonth();

  Future<Map<String, dynamic>> _load() async {
    final r = await Future.wait([
      Api.instance.get('/me/spend-by-category', {'month': _month}),
      Api.instance.get('/me/merchants', {'months': '6', 'limit': '10'}),
      Api.instance.get('/me/weekday', {'months': '6'}),
      Api.instance.get('/me/trend', {'months': '12'}),
    ]);
    return {'cats': r[0], 'merchants': r[1], 'week': r[2], 'trend': r[3]};
  }

  @override
  Widget build(BuildContext context) {
    final k = Palette.of(context);
    return RefreshIndicator(
      onRefresh: () async => setState(() {}),
      child: ListView(padding: const EdgeInsets.fromLTRB(16, 16, 16, 24), children: [
        const Text('Spend', style: TextStyle(fontSize: 26, fontWeight: FontWeight.w700, letterSpacing: -.4)),
        const SizedBox(height: 12),
        MonthBar(_month, (m) => setState(() => _month = m)),
        Loader<Map<String, dynamic>>(
          key: ValueKey(_month),
          rows: 8,
          load: _load,
          builder: (context, d) {
            final c = d['cats'] as Map<String, dynamic>;
            final cats = (c['categories'] as List).cast<Map<String, dynamic>>();
            final merchants = (d['merchants'] as List).cast<Map<String, dynamic>>();
            final week = (d['week'] as List).cast<Map<String, dynamic>>();
            final trend = (d['trend'] as List).cast<Map<String, dynamic>>();
            final total = c['total_paise'] as int;
            final prevTotal = c['previous_total_paise'] as int;
            return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              const SectionTitle('By category'),
              if (cats.isEmpty) const EmptyState('No spending this month', hint: 'Entries you add show up here by category.') else ...[
                const SizedBox(height: 10),
                Donut(
                  slices: [for (final x in cats.where((x) => (x['spend_paise'] as int) > 0)) Slice(x['code'] as String, x['name'] as String, x['spend_paise'] as int)],
                  centre: Column(mainAxisSize: MainAxisSize.min, children: [Text('Spent', style: TextStyle(color: k.muted, fontSize: 12)), CountUp(total, (v) => Money(v, big: true))]),
                  onPick: (code) => widget.onOpenEntries('category=$code&month=$_month'),
                ),
                const SectionTitle('Against last month'),
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 10),
                  child: Row(children: [
                    Expanded(child: Text('${monthName(c['previous_month'] as String)}: ${inr(prevTotal)}', style: TextStyle(color: k.muted))),
                    Delta(c['change_paise'] as int),
                  ]),
                ),
                for (final x in cats.where((x) => (x['change_paise'] as int) != 0).take(6))
                  Container(
                    padding: const EdgeInsets.symmetric(vertical: 9),
                    decoration: BoxDecoration(border: Border(bottom: BorderSide(color: k.rule))),
                    child: Row(children: [
                      Expanded(child: Text(x['name'] as String)),
                      Delta(x['change_paise'] as int),
                    ]),
                  ),
              ],
              const SectionTitle('Top payees · 6 months'),
              if (merchants.isEmpty) const EmptyState('No payees yet') else
                BarList(
                  rows: [for (final m in merchants) (key: m['name'] as String, label: m['name'] as String, sub: '${m['count']} payment${m['count'] == 1 ? '' : 's'} · last ${dayLabel(m['last_date'] as String)}', value: m['spend_paise'] as int)],
                  onPick: (name) => widget.onOpenEntries('merchant=${Uri.encodeQueryComponent(name)}&month=all'),
                ),
              const SectionTitle('Which days you spend most'),
              if (week.every((w) => (w['spend_paise'] as int) == 0)) const EmptyState('Not enough yet', hint: 'A few weeks of entries show your weekly rhythm.') else ...[
                const SizedBox(height: 10),
                ColumnBars(cols: [for (final w in week) (label: (w['name'] as String).substring(0, 3), value: w['average_paise'] as int, line: null)]),
                Text('Average spend on each weekday over six months.', style: TextStyle(color: k.muted, fontSize: 13)),
              ],
              const SectionTitle('Twelve months'),
              if (trend.isEmpty) const EmptyState('No history yet') else ...[
                const SizedBox(height: 10),
                ColumnBars(cols: [for (final t in trend) (label: monthName(t['month'] as String).substring(0, 3), value: t['spend_paise'] as int, line: t['income_paise'] as int)]),
                Row(children: [
                  Container(width: 12, height: 12, color: k.blue), const SizedBox(width: 6), Text('Spent', style: TextStyle(color: k.muted, fontSize: 13)),
                  const SizedBox(width: 16), Container(width: 14, height: 2, color: k.green), const SizedBox(width: 6), Text('Income', style: TextStyle(color: k.muted, fontSize: 13)),
                ]),
              ],
            ]);
          },
        ),
      ]),
    );
  }
}

