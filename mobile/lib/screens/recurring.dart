import 'package:flutter/material.dart';

import '../api.dart';
import '../format.dart';
import '../theme.dart';
import '../ui/widgets.dart';

class Recurring extends StatefulWidget {
  const Recurring({super.key});
  @override
  State<Recurring> createState() => _RecurringState();
}

class _RecurringState extends State<Recurring> {
  String _filter = 'ALL';

  @override
  Widget build(BuildContext context) {
    final k = Palette.of(context);
    return RefreshIndicator(
      onRefresh: () async => setState(() {}),
      child: ListView(padding: const EdgeInsets.fromLTRB(16, 16, 16, 24), children: [
        const Text('Recurring', style: TextStyle(fontSize: 26, fontWeight: FontWeight.w700, letterSpacing: -.4)),
        const SizedBox(height: 4),
        Text('Bills, EMIs, subscriptions and salary that repeat. A missed one is flagged.', style: TextStyle(color: k.muted)),
        const SizedBox(height: 12),
        Wrap(spacing: 8, children: [
          for (final f in const ['ALL', 'ACTIVE', 'MISSED', 'ENDED'])
            ChoiceChip(label: Text(titleCase(f)), selected: _filter == f, onSelected: (_) => setState(() => _filter = f), shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(2), side: BorderSide(color: k.ruleStrong))),
        ]),
        Loader<List<dynamic>>(
          load: () async => (await Api.instance.get('/me/recurring')) as List<dynamic>,
          builder: (context, all) {
            final rows = all.cast<Map<String, dynamic>>().where((s) => _filter == 'ALL' || s['status'] == _filter).toList();
            if (rows.isEmpty) return EmptyState(all.isEmpty ? 'No recurring payments yet' : 'Nothing here', hint: all.isEmpty ? 'They appear once a payment repeats three times.' : null);
            return Column(children: [
              for (final s in rows)
                Container(
                  padding: const EdgeInsets.symmetric(vertical: 12),
                  decoration: BoxDecoration(border: Border(bottom: BorderSide(color: k.rule))),
                  child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      Text((s['merchant_name'] ?? titleCase(s['category_code'] as String)) as String, style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 16)),
                      Text('${titleCase(s['cadence'] as String)} · ${titleCase(s['series_type'] as String)}', style: TextStyle(color: k.muted, fontSize: 13)),
                      const SizedBox(height: 4),
                      Text(s['next_expected'] == null ? 'Last paid ${dayLabel(s['last_seen'] as String)}' : 'Next ${dayLabel(s['next_expected'] as String)} · last ${dayLabel(s['last_seen'] as String)}',
                          style: TextStyle(color: s['status'] == 'MISSED' ? k.red : k.muted, fontWeight: s['status'] == 'MISSED' ? FontWeight.w700 : FontWeight.w400)),
                    ])),
                    Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
                      Money(s['typical_amount_paise'] as int, big: true),
                      const SizedBox(height: 6),
                      statusStamp(context, s['status'] as String),
                    ]),
                  ]),
                ),
            ]);
          },
        ),
      ]),
    );
  }
}
