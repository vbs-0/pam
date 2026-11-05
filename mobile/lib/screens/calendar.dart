import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../api.dart';
import '../format.dart';
import '../theme.dart';
import '../ui/widgets.dart';
import 'entries.dart';

/// A month as a calendar: each day is shaded by how much was spent, tap a day to see what it was.
class CalendarScreen extends StatefulWidget {
  final VoidCallback onChanged;
  const CalendarScreen({super.key, required this.onChanged});
  @override
  State<CalendarScreen> createState() => _CalendarScreenState();
}

class _CalendarScreenState extends State<CalendarScreen> {
  String _month = currentMonth();

  @override
  Widget build(BuildContext context) => RefreshIndicator(
        onRefresh: () async => setState(() {}),
        child: ListView(padding: const EdgeInsets.fromLTRB(16, 16, 16, 24), children: [
          const Text('Calendar', style: TextStyle(fontSize: 26, fontWeight: FontWeight.w700, letterSpacing: -.4)),
          const SizedBox(height: 12),
          MonthBar(_month, (m) => setState(() => _month = m)),
          const SizedBox(height: 8),
          Loader<Map<String, dynamic>>(
            key: ValueKey(_month),
            rows: 7,
            load: () async => (await Api.instance.get('/me/daily', {'month': _month})) as Map<String, dynamic>,
            builder: (context, d) => _Grid(month: _month, data: d, onOpen: (day) => _openDay(day)),
          ),
        ]),
      );

  Future<void> _openDay(String day) async {
    HapticFeedback.selectionClick();
    final changed = await showModalBottomSheet<bool>(context: context, isScrollControlled: true, useSafeArea: true, builder: (_) => _DaySheet(day: day));
    if (changed == true) { widget.onChanged(); }
  }
}

class _Grid extends StatelessWidget {
  final String month;
  final Map<String, dynamic> data;
  final ValueChanged<String> onOpen;
  const _Grid({required this.month, required this.data, required this.onOpen});

  @override
  Widget build(BuildContext context) {
    final k = Palette.of(context);
    final days = {for (final d in (data['days'] as List).cast<Map<String, dynamic>>()) d['date'] as String: d};
    final y = int.parse(month.substring(0, 4)), m = int.parse(month.substring(5, 7));
    final count = DateTime.utc(y, m + 1, 0).day;
    final lead = DateTime.utc(y, m, 1).weekday - 1; // Monday first
    final peak = days.values.fold<int>(1, (mx, d) => (d['spend_paise'] as int) > mx ? d['spend_paise'] as int : mx);
    final today = todayIso();
    final total = data['total_spend_paise'] as int;
    final avg = data['daily_average_paise'] as int;
    final left = data['days_left'] as int;
    final busiest = data['busiest'] as String?;

    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const SizedBox(height: 6),
      Row(children: [
        Expanded(child: _Fact('SPENT', CountUp(total, (v) => Money(v, big: true)))),
        Expanded(child: _Fact('A DAY', CountUp(avg, (v) => Money(v, big: true)))),
        Expanded(child: _Fact(left > 0 ? 'DAYS LEFT' : 'BUSIEST', left > 0 ? Text('$left', style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 18)) : Text(busiest == null ? '—' : dayLabel(busiest), style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 18)))),
      ]),
      const SizedBox(height: 14),
      Row(children: [for (final w in const ['M', 'T', 'W', 'T', 'F', 'S', 'S']) Expanded(child: Center(child: Text(w, style: TextStyle(color: k.muted, fontWeight: FontWeight.w800, fontSize: 12))))]),
      const SizedBox(height: 6),
      GridView.count(
        crossAxisCount: 7, shrinkWrap: true, physics: const NeverScrollableScrollPhysics(), mainAxisSpacing: 4, crossAxisSpacing: 4, childAspectRatio: .82,
        children: [
          for (var i = 0; i < lead; i++) const SizedBox.shrink(),
          for (var n = 1; n <= count; n++) _cell(context, k, n, '$month-${n.toString().padLeft(2, '0')}', days, peak, today),
        ],
      ),
      const SizedBox(height: 12),
      Row(children: [
        Text('Less', style: TextStyle(color: k.muted, fontSize: 12)),
        const SizedBox(width: 6),
        for (final a in const [.1, .3, .5, .75, 1.0]) Container(width: 22, height: 12, margin: const EdgeInsets.only(right: 2), color: k.blue.withValues(alpha: a * .85)),
        const SizedBox(width: 4),
        Text('More', style: TextStyle(color: k.muted, fontSize: 12)),
      ]),
      if (busiest != null) Padding(padding: const EdgeInsets.only(top: 10), child: Text('Biggest day: ${dayLabel(busiest)}, ${inr((days[busiest]?['spend_paise'] as int?) ?? 0)}.', style: TextStyle(color: k.muted))),
    ]);
  }

  Widget _cell(BuildContext context, Palette k, int n, String iso, Map<String, Map<String, dynamic>> days, int peak, String today) {
    final d = days[iso];
    final spend = (d?['spend_paise'] as int?) ?? 0;
    final has = d != null && ((d['count'] as int?) ?? 0) > 0;
    final shade = spend <= 0 ? 0.0 : (.12 + .73 * (spend / peak)).clamp(0.0, .85);
    final dark = shade > .5;
    final isToday = iso == today;
    return Semantics(
      button: true,
      label: '${dayLabel(iso)}, ${spend > 0 ? 'spent ${inr(spend)}' : has ? 'no spending' : 'no entries'}',
      child: InkWell(
        onTap: () => onOpen(iso),
        child: Container(
          padding: const EdgeInsets.all(3),
          decoration: BoxDecoration(
            color: shade > 0 ? k.blue.withValues(alpha: shade) : k.sheet,
            border: Border.all(color: isToday ? k.red : k.rule, width: isToday ? 2 : 1),
          ),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text('$n', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 12, color: dark ? k.paper : k.ink)),
            const Spacer(),
            if (spend > 0) FittedBox(fit: BoxFit.scaleDown, child: Text(rupeesShort(spend), style: TextStyle(fontSize: 11, fontWeight: FontWeight.w700, color: dark ? k.paper : k.ink, fontFeatures: tabular))),
            if (spend <= 0 && has) Container(width: 6, height: 6, decoration: BoxDecoration(color: k.green, shape: BoxShape.circle)),
          ]),
        ),
      ),
    );
  }
}

class _Fact extends StatelessWidget {
  final String label;
  final Widget child;
  const _Fact(this.label, this.child);
  @override
  Widget build(BuildContext context) => Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(label, style: TextStyle(color: Palette.of(context).muted, fontWeight: FontWeight.w800, fontSize: 11, letterSpacing: 1)),
        const SizedBox(height: 2),
        child,
      ]);
}

class _DaySheet extends StatefulWidget {
  final String day;
  const _DaySheet({required this.day});
  @override
  State<_DaySheet> createState() => _DaySheetState();
}

class _DaySheetState extends State<_DaySheet> {
  bool _changed = false;
  late Future<List<Map<String, dynamic>>> _f = _load();
  Future<List<Map<String, dynamic>>> _load() async {
    final r = await Api.instance.get('/me/transactions', {'date_from': widget.day, 'date_to': widget.day, 'limit': '100'}) as Map<String, dynamic>;
    return (r['items'] as List).cast<Map<String, dynamic>>();
  }

  @override
  Widget build(BuildContext context) {
    final k = Palette.of(context);
    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) { if (!didPop) Navigator.pop(context, _changed); },
      child: Padding(
        padding: const EdgeInsets.fromLTRB(20, 20, 20, 20),
        child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            Expanded(child: Text('${dayLabel(widget.day)} ${widget.day.substring(0, 4)}', style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w700))),
            IconButton(tooltip: 'Close', onPressed: () => Navigator.pop(context, _changed), icon: const Icon(Icons.close)),
          ]),
          Flexible(
            child: SingleChildScrollView(
              child: FutureBuilder<List<Map<String, dynamic>>>(
                future: _f,
                builder: (context, s) {
                  if (s.connectionState != ConnectionState.done) return const Skeleton(rows: 4);
                  if (s.hasError) return ErrorBox(s.error!, retry: () => setState(() => _f = _load()));
                  final rows = s.data!;
                  if (rows.isEmpty) return const EmptyState('Nothing written on this day');
                  final out = rows.where((t) => (t['amount_paise'] as int) < 0 && t['kind'] == 'EXPENSE').fold<int>(0, (a, t) => a - (t['amount_paise'] as int));
                  return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    if (out > 0) Padding(padding: const EdgeInsets.only(bottom: 8), child: Text('Spent ${inr(out)} across ${rows.length} entr${rows.length == 1 ? 'y' : 'ies'}', style: TextStyle(color: k.muted))),
                    for (final t in rows)
                      InkWell(
                        onTap: () async {
                          final c = await showModalBottomSheet<bool>(context: context, isScrollControlled: true, useSafeArea: true, builder: (_) => EntrySheet(txnId: t['txn_id'] as String, canWrite: true));
                          if (c == true) { _changed = true; if (mounted) setState(() => _f = _load()); }
                        },
                        child: Container(
                          padding: const EdgeInsets.symmetric(vertical: 11),
                          decoration: BoxDecoration(border: Border(bottom: BorderSide(color: k.rule))),
                          child: Row(children: [
                            Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                              Text((t['merchant_name'] ?? t['descriptor']) as String, maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(fontWeight: FontWeight.w600)),
                              Text(titleCase(t['category_code'] as String), style: TextStyle(color: k.muted, fontSize: 13)),
                            ])),
                            Money(t['amount_paise'] as int, sign: true, color: (t['amount_paise'] as int) > 0 ? k.blue : null),
                          ]),
                        ),
                      ),
                  ]);
                },
              ),
            ),
          ),
        ]),
      ),
    );
  }
}
