import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../api.dart';
import '../format.dart';
import '../theme.dart';
import '../ui/widgets.dart';
import 'entries.dart';


Future<bool> _isSample() async => ((await Api.instance.get('/me/profile')) as Map<String, dynamic>)['sample'] == true;

// ---------------------------------------------------------------- Bills & alerts

class BillsScreen extends StatefulWidget {
  const BillsScreen({super.key});
  @override
  State<BillsScreen> createState() => _BillsScreenState();
}

class _BillsScreenState extends State<BillsScreen> {
  int _days = 30;

  Future<Map<String, dynamic>> _load() async {
    final r = await Future.wait([Api.instance.get('/me/alerts'), Api.instance.get('/me/upcoming', {'days': '$_days'}), Api.instance.get('/me/networth')]);
    return {'alerts': r[0], 'up': r[1], 'nw': r[2]};
  }

  @override
  Widget build(BuildContext context) {
    final k = Palette.of(context);
    return Scaffold(
      appBar: AppBar(title: const Text('Bills & alerts')),
      body: RefreshIndicator(
        onRefresh: () async => setState(() {}),
        child: ListView(padding: const EdgeInsets.fromLTRB(16, 8, 16, 24), children: [
          Loader<Map<String, dynamic>>(
            key: ValueKey(_days),
            rows: 8,
            load: _load,
            builder: (context, d) {
              final alerts = ((d['alerts'] as Map)['alerts'] as List).cast<Map<String, dynamic>>();
              final up = d['up'] as Map<String, dynamic>;
              final items = (up['items'] as List).cast<Map<String, dynamic>>();
              final nw = d['nw'] as Map<String, dynamic>;
              final cards = (nw['cards'] as List).cast<Map<String, dynamic>>();
              Color tone(String s) => s == 'ALERT' ? k.red : s == 'WARN' ? k.amber : k.blue;
              return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                const SectionTitle('Needs a look'),
                if (alerts.isEmpty) const EmptyState('All clear', hint: 'No bills due, no budget over its limit, no card close to its limit.'),
                for (final a in alerts)
                  Container(
                    padding: const EdgeInsets.symmetric(vertical: 11),
                    decoration: BoxDecoration(border: Border(bottom: BorderSide(color: k.rule))),
                    child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      Padding(padding: const EdgeInsets.only(top: 2), child: Stamp(a['severity'] == 'ALERT' ? 'Over' : a['severity'] == 'WARN' ? 'Watch' : 'Info', tone(a['severity'] as String))),
                      const SizedBox(width: 10),
                      Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [Text(a['title'] as String, style: const TextStyle(fontWeight: FontWeight.w600)), Text(a['detail'] as String, style: TextStyle(color: k.muted, fontSize: 13))])),
                    ]),
                  ),
                SectionTitle('Coming up', trailing: SegmentedButton<int>(
                  showSelectedIcon: false, style: const ButtonStyle(visualDensity: VisualDensity.compact),
                  segments: const [ButtonSegment(value: 7, label: Text('7d')), ButtonSegment(value: 30, label: Text('30d')), ButtonSegment(value: 90, label: Text('90d'))],
                  selected: {_days}, onSelectionChanged: (s) => setState(() => _days = s.first),
                )),
                if (items.isEmpty) EmptyState('Nothing due in the next $_days days', hint: 'Bills and income appear once PAM sees a payment repeat.') else ...[
                  Padding(padding: const EdgeInsets.symmetric(vertical: 8), child: Text('Going out ${inr(up['due_out_paise'] as int)}${(up['due_in_paise'] as int) > 0 ? ' · coming in ${inr(up['due_in_paise'] as int)}' : ''}', style: TextStyle(color: k.muted))),
                  for (final i in items)
                    Container(
                      padding: const EdgeInsets.symmetric(vertical: 11),
                      decoration: BoxDecoration(border: Border(bottom: BorderSide(color: k.rule))),
                      child: Row(children: [
                        SizedBox(width: 54, child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                          Text(i['overdue'] == true ? 'LATE' : (i['days_away'] as int) == 0 ? 'TODAY' : '${i['days_away']}d', style: TextStyle(color: i['overdue'] == true ? k.red : k.blue, fontWeight: FontWeight.w800, fontSize: 12)),
                          Text(dayLabel(i['due'] as String), style: TextStyle(color: k.muted, fontSize: 12)),
                        ])),
                        Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                          Text(i['name'] as String, maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(fontWeight: FontWeight.w600)),
                          Text(i['kind'] == 'CARD' ? 'Credit card bill' : '${i['series_type'] == 'INCOME' ? 'Income' : 'Recurring'} · ${titleCase(i['cadence'] as String)}', style: TextStyle(color: k.muted, fontSize: 12)),
                        ])),
                        Money(i['amount_paise'] as int, sign: i['direction'] == 'CR', color: i['direction'] == 'CR' ? k.blue : null),
                      ]),
                    ),
                ],
                const SectionTitle('Net worth'),
                const SizedBox(height: 10),
                Row(children: [
                  Expanded(child: _Fig('YOU OWN', CountUp(nw['assets_paise'] as int, (v) => Money(v, big: true)))),
                  Expanded(child: _Fig('YOU OWE', CountUp(nw['liabilities_paise'] as int, (v) => Money(v, big: true, color: k.red)))),
                  Expanded(child: _Fig('NET', CountUp(nw['net_worth_paise'] as int, (v) => Money(v, big: true, color: (nw['net_worth_paise'] as int) < 0 ? k.red : k.blue)))),
                ]),
                for (final c in cards) _CardTile(c),
              ]);
            },
          ),
        ]),
      ),
    );
  }
}

class _Fig extends StatelessWidget {
  final String label;
  final Widget child;
  const _Fig(this.label, this.child);
  @override
  Widget build(BuildContext context) => Column(crossAxisAlignment: CrossAxisAlignment.start, children: [Text(label, style: TextStyle(color: Palette.of(context).muted, fontWeight: FontWeight.w800, fontSize: 11, letterSpacing: 1)), const SizedBox(height: 2), child]);
}

class _CardTile extends StatelessWidget {
  final Map<String, dynamic> c;
  const _CardTile(this.c);
  @override
  Widget build(BuildContext context) {
    final k = Palette.of(context);
    final util = (c['utilisation'] as num?)?.toDouble();
    final due = c['due_date'] as String?;
    return Container(
      margin: const EdgeInsets.only(top: 12), padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(color: k.sheet, border: Border.all(color: k.ruleStrong)),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(c['display_name'] as String, style: const TextStyle(fontWeight: FontWeight.w700)),
        const SizedBox(height: 2),
        Text('${inr(c['used_paise'] as int)} used${c['limit_paise'] != null ? ' of ${inr(c['limit_paise'] as int)}' : ''}', style: TextStyle(color: k.muted)),
        if (util != null) ...[
          const SizedBox(height: 8),
          ClipRRect(borderRadius: BorderRadius.circular(2), child: LinearProgressIndicator(value: util.clamp(0, 1), minHeight: 9, backgroundColor: k.rule, color: util >= .8 ? k.red : util >= .5 ? k.amber : k.blue)),
        ],
        const SizedBox(height: 8),
        Text(due == null ? 'Set the due day in Books (Edit on the card).' : 'Due ${dayLabel(due)}${c['days_to_due'] != null ? ' · in ${c['days_to_due']} day${c['days_to_due'] == 1 ? '' : 's'}' : ''}', style: TextStyle(fontWeight: FontWeight.w600, color: due == null ? k.muted : k.ink)),
      ]),
    );
  }
}

// ---------------------------------------------------------------- Goals

class GoalsScreen extends StatefulWidget {
  const GoalsScreen({super.key});
  @override
  State<GoalsScreen> createState() => _GoalsScreenState();
}

class _GoalsScreenState extends State<GoalsScreen> {
  int _rev = 0;
  bool _sample = true;

  Future<List<Map<String, dynamic>>> _load() async {
    final sample = await _isSample();
    if (mounted && sample != _sample) setState(() => _sample = sample);
    return ((await Api.instance.get('/me/goals')) as List).cast<Map<String, dynamic>>();
  }

  Future<void> _edit([Map<String, dynamic>? g]) async {
    final ok = await showModalBottomSheet<bool>(context: context, isScrollControlled: true, useSafeArea: true, builder: (_) => _GoalSheet(goal: g));
    if (ok == true) setState(() => _rev++);
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('Savings goals')),
        floatingActionButton: FloatingActionButton.extended(
          onPressed: _sample ? null : () => _edit(), icon: const Icon(Icons.add), label: const Text('New goal'),
          backgroundColor: _sample ? Palette.of(context).rule : Palette.of(context).blue, foregroundColor: Palette.of(context).paper,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(2)),
        ),
        body: RefreshIndicator(
          onRefresh: () async => setState(() => _rev++),
          child: ListView(padding: const EdgeInsets.fromLTRB(16, 8, 16, 96), children: [
            Loader<List<Map<String, dynamic>>>(
              key: ValueKey(_rev), rows: 4, load: _load,
              builder: (context, goals) => goals.isEmpty
                  ? const EmptyState('No goals yet', hint: 'A trip, a laptop, an emergency fund. Give it a target and a date and PAM tells you how much to set aside each month.')
                  : Column(children: [for (final g in goals) _GoalCard(g, canWrite: !_sample, onEdit: () => _edit(g), onChanged: () => setState(() => _rev++))]),
            ),
          ]),
        ),
      );
}

class _GoalCard extends StatefulWidget {
  final Map<String, dynamic> g;
  final bool canWrite;
  final VoidCallback onEdit, onChanged;
  const _GoalCard(this.g, {required this.canWrite, required this.onEdit, required this.onChanged});
  @override
  State<_GoalCard> createState() => _GoalCardState();
}

class _GoalCardState extends State<_GoalCard> {
  Future<void> _contribute(int sign) async {
    final c = TextEditingController();
    final amount = await showDialog<int>(
      context: context,
      builder: (d) => AlertDialog(
        title: Text(sign > 0 ? 'Add to ${widget.g['name']}' : 'Take out of ${widget.g['name']}'),
        content: TextField(controller: c, autofocus: true, keyboardType: const TextInputType.numberWithOptions(decimal: true), decoration: const InputDecoration(labelText: 'Amount (₹)')),
        actions: [TextButton(onPressed: () => Navigator.pop(d), child: const Text('Cancel')), FilledButton(onPressed: () { final p = toPaise(c.text); if (p != null && p > 0) Navigator.pop(d, p); }, child: const Text('Save'))],
      ),
    );
    c.dispose();
    if (amount == null) return;
    try {
      await Api.instance.post('/me/goals/${widget.g['goal_id']}/contribute', {'amount_paise': sign * amount});
      HapticFeedback.mediumImpact();
      widget.onChanged();
    } catch (e) { if (mounted) showError(context, e); }
  }

  @override
  Widget build(BuildContext context) {
    final k = Palette.of(context);
    final g = widget.g;
    final done = g['completed'] == true;
    final progress = (g['progress'] as num).toDouble().clamp(0.0, 1.0);
    final monthly = g['monthly_needed_paise'] as int?;
    return Container(
      margin: const EdgeInsets.only(top: 14), padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(color: k.sheet, border: Border.all(color: k.ruleStrong)),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Expanded(child: Text(g['name'] as String, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 17))),
          if (done) Stamp('Reached', k.green),
          if (widget.canWrite) IconButton(tooltip: 'Edit goal', visualDensity: VisualDensity.compact, onPressed: widget.onEdit, icon: const Icon(Icons.edit_outlined, size: 20)),
        ]),
        Text.rich(TextSpan(children: [TextSpan(text: inr(g['saved_paise'] as int), style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 22)), TextSpan(text: '  of ${inr(g['target_paise'] as int)}', style: TextStyle(color: k.muted))])),
        const SizedBox(height: 10),
        TweenAnimationBuilder<double>(
          tween: Tween(begin: 0, end: progress), duration: const Duration(milliseconds: 700), curve: Curves.easeOutCubic,
          builder: (_, v, __) => ClipRRect(borderRadius: BorderRadius.circular(2), child: LinearProgressIndicator(value: v, minHeight: 11, backgroundColor: k.rule, color: done ? k.green : k.blue)),
        ),
        const SizedBox(height: 8),
        Text(done ? 'You made it.' : '${inr(g['remaining_paise'] as int)} to go${g['deadline'] != null ? ' · by ${dayLabel(g['deadline'] as String)} (${g['days_left']} days)' : ''}', style: TextStyle(color: k.muted)),
        if (!done && monthly != null) Padding(padding: const EdgeInsets.only(top: 4), child: Text('Set aside about ${inr(monthly)} a month.', style: const TextStyle(fontWeight: FontWeight.w600))),
        if (widget.canWrite) Padding(
          padding: const EdgeInsets.only(top: 12),
          child: Row(children: [
            Expanded(child: FilledButton(onPressed: () => _contribute(1), child: const Text('Add money'))),
            const SizedBox(width: 10),
            Expanded(child: OutlinedButton(onPressed: (g['saved_paise'] as int) == 0 ? null : () => _contribute(-1), child: const Text('Take out'))),
          ]),
        ),
      ]),
    );
  }
}

class _GoalSheet extends StatefulWidget {
  final Map<String, dynamic>? goal;
  const _GoalSheet({this.goal});
  @override
  State<_GoalSheet> createState() => _GoalSheetState();
}

class _GoalSheetState extends State<_GoalSheet> {
  late final _name = TextEditingController(text: widget.goal?['name'] as String? ?? '');
  late final _target = TextEditingController(text: widget.goal == null ? '' : '${(widget.goal!['target_paise'] as int) / 100}');
  late final _saved = TextEditingController();
  String? _deadline, _error;
  bool _busy = false;

  @override
  void initState() { super.initState(); _deadline = widget.goal?['deadline'] as String?; }
  @override
  void dispose() { _name.dispose(); _target.dispose(); _saved.dispose(); super.dispose(); }

  Future<void> _pick() async {
    final now = DateTime.parse(todayIso());
    final d = await showDatePicker(context: context, initialDate: _deadline == null ? now.add(const Duration(days: 90)) : DateTime.parse(_deadline!), firstDate: now, lastDate: now.add(const Duration(days: 3650)));
    if (d != null) setState(() => _deadline = d.toIso8601String().substring(0, 10));
  }

  Future<void> _save() async {
    final t = toPaise(_target.text);
    if (_name.text.trim().isEmpty) { setState(() => _error = 'Give the goal a name'); return; }
    if (t == null || t == 0) { setState(() => _error = 'Enter a target like 50,000'); return; }
    setState(() { _busy = true; _error = null; });
    try {
      if (widget.goal == null) {
        await Api.instance.post('/me/goals', {'name': _name.text.trim(), 'target_paise': t, 'deadline': _deadline, if (_saved.text.isNotEmpty) 'saved_paise': toPaise(_saved.text) ?? 0});
      } else {
        await Api.instance.patch('/me/goals/${widget.goal!['goal_id']}', {'name': _name.text.trim(), 'target_paise': t, 'deadline': _deadline});
      }
      if (mounted) Navigator.pop(context, true);
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    } finally { if (mounted) setState(() => _busy = false); }
  }

  Future<void> _delete() async {
    final ok = await showDialog<bool>(context: context, builder: (d) => AlertDialog(title: const Text('Delete this goal?'), content: const Text('The money you marked as saved stays wherever it is; only the goal is removed.'), actions: [TextButton(onPressed: () => Navigator.pop(d, false), child: const Text('Keep')), FilledButton(onPressed: () => Navigator.pop(d, true), child: const Text('Delete'))]));
    if (ok != true) return;
    try { await Api.instance.delete('/me/goals/${widget.goal!['goal_id']}'); if (mounted) Navigator.pop(context, true); } catch (e) { if (mounted) showError(context, e); }
  }

  @override
  Widget build(BuildContext context) {
    final k = Palette.of(context);
    return Padding(
      padding: EdgeInsets.fromLTRB(20, 20, 20, 20 + MediaQuery.of(context).viewInsets.bottom),
      child: SingleChildScrollView(
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [Expanded(child: Text(widget.goal == null ? 'New goal' : 'Edit goal', style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w700))), IconButton(tooltip: 'Close', onPressed: () => Navigator.pop(context, false), icon: const Icon(Icons.close))]),
          const SizedBox(height: 8),
          TextField(controller: _name, maxLength: 60, textCapitalization: TextCapitalization.sentences, decoration: const InputDecoration(labelText: 'What for?', hintText: 'Goa trip, new phone, emergency fund', counterText: '')),
          const SizedBox(height: 12),
          TextField(controller: _target, keyboardType: const TextInputType.numberWithOptions(decimal: true), decoration: const InputDecoration(labelText: 'Target amount (₹)')),
          if (widget.goal == null) ...[const SizedBox(height: 12), TextField(controller: _saved, keyboardType: const TextInputType.numberWithOptions(decimal: true), decoration: const InputDecoration(labelText: 'Already saved (₹, optional)'))],
          const SizedBox(height: 12),
          Row(children: [
            Expanded(child: OutlinedButton.icon(onPressed: _pick, icon: const Icon(Icons.event, size: 18), label: Text(_deadline == null ? 'Needed by (optional)' : '${dayLabel(_deadline!)} ${_deadline!.substring(0, 4)}'))),
            if (_deadline != null) IconButton(tooltip: 'Clear date', onPressed: () => setState(() => _deadline = null), icon: const Icon(Icons.clear)),
          ]),
          if (_error != null) Padding(padding: const EdgeInsets.only(top: 12), child: Text(_error!, style: TextStyle(color: k.red, fontWeight: FontWeight.w600))),
          const SizedBox(height: 16),
          SizedBox(width: double.infinity, child: FilledButton(onPressed: _busy ? null : _save, child: Text(_busy ? 'Saving…' : 'Save goal'))),
          if (widget.goal != null) Padding(padding: const EdgeInsets.only(top: 10), child: SizedBox(width: double.infinity, child: OutlinedButton(style: OutlinedButton.styleFrom(foregroundColor: k.red, side: BorderSide(color: k.red)), onPressed: _delete, child: const Text('Delete goal')))),
        ]),
      ),
    );
  }
}

// ---------------------------------------------------------------- Budgets

class BudgetsScreen extends StatefulWidget {
  final VoidCallback onChanged;
  const BudgetsScreen({super.key, required this.onChanged});
  @override
  State<BudgetsScreen> createState() => _BudgetsScreenState();
}

class _BudgetsScreenState extends State<BudgetsScreen> {
  String _month = currentMonth();
  int _rev = 0;
  bool _sample = true;

  Future<Map<String, dynamic>> _load() async {
    final sample = await _isSample();
    if (mounted && sample != _sample) setState(() => _sample = sample);
    return (await Api.instance.get('/me/budgets', {'month': _month})) as Map<String, dynamic>;
  }

  void _changed() { setState(() => _rev++); widget.onChanged(); }

  Future<void> _edit(String? code, String? name, int? current) async {
    final ok = await showModalBottomSheet<bool>(context: context, isScrollControlled: true, useSafeArea: true, builder: (_) => _LimitSheet(month: _month, code: code, name: name, current: current));
    if (ok == true) _changed();
  }

  Future<void> _carry(String code, bool on) async {
    try { await Api.instance.put('/me/budgets/carry', {'category_code': code, 'enabled': on}); HapticFeedback.selectionClick(); _changed(); } catch (e) { if (mounted) showError(context, e); }
  }

  Future<void> _remove(String code) async {
    try { await Api.instance.delete('/me/budgets/$_month/$code'); _changed(); } catch (e) { if (mounted) showError(context, e); }
  }

  @override
  Widget build(BuildContext context) {
    final k = Palette.of(context);
    return Scaffold(
      appBar: AppBar(title: const Text('Budgets')),
      floatingActionButton: _sample ? null : FloatingActionButton.extended(onPressed: () => _edit(null, null, null), backgroundColor: k.blue, foregroundColor: k.paper, shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(2)), icon: const Icon(Icons.add), label: const Text('Set a limit')),
      body: RefreshIndicator(
        onRefresh: () async => setState(() => _rev++),
        child: ListView(padding: const EdgeInsets.fromLTRB(16, 12, 16, 96), children: [
          MonthBar(_month, (m) => setState(() => _month = m)),
          Loader<Map<String, dynamic>>(
            key: ValueKey('$_month$_rev'), rows: 6, load: _load,
            builder: (context, b) {
              final lines = (b['lines'] as List).cast<Map<String, dynamic>>();
              final carry = ((b['carry_enabled'] as List?) ?? const []).cast<String>();
              if (lines.isEmpty) return const EmptyState('No budgets or spending this month', hint: 'Tap Set a limit to start tracking a category.');
              return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Padding(padding: const EdgeInsets.only(top: 12), child: Text('Budgeted ${inr(b['total_budget_paise'] as int)} · spent ${inr(b['total_actual_paise'] as int)}', style: TextStyle(color: k.muted))),
                for (final l in lines) _line(context, k, l, carry.contains(l['category_code'])),
                Padding(padding: const EdgeInsets.only(top: 14), child: Text('Roll over adds what you did not spend last month to this month\'s limit. Tap a line to change its limit.', style: TextStyle(color: k.muted, fontSize: 12))),
              ]);
            },
          ),
        ]),
      ),
    );
  }

  Widget _line(BuildContext context, Palette k, Map<String, dynamic> l, bool carryOn) {
    final code = l['category_code'] as String;
    final name = (l['category_name'] ?? titleCase(code)) as String;
    final budget = l['budget_paise'] as int?;
    final status = l['status'] as String;
    final carried = (l['carried_paise'] as int?) ?? 0;
    return InkWell(
      onTap: _sample ? null : () => _edit(code, name, budget),
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 10),
        decoration: BoxDecoration(border: Border(bottom: BorderSide(color: k.rule))),
        child: Column(children: [
          Row(children: [Expanded(child: Text(name, style: const TextStyle(fontWeight: FontWeight.w600))), statusStamp(context, status)]),
          const SizedBox(height: 6),
          LimitBar(actual: l['actual_paise'] as int, budget: budget, status: status),
          const SizedBox(height: 6),
          Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
            Money(l['actual_paise'] as int, color: status == 'OVER' ? k.red : null),
            Text(budget == null ? 'No limit' : 'of ${inr(budget)}${carried > 0 ? ' (incl. ${inr(carried)} rolled over)' : ''}', style: TextStyle(color: k.muted, fontSize: 13)),
          ]),
          if (!_sample && budget != null) Row(children: [
            Checkbox(visualDensity: VisualDensity.compact, value: carryOn, onChanged: (v) => _carry(code, v ?? false)),
            const Text('Roll over unspent money'),
            const Spacer(),
            IconButton(tooltip: 'Remove limit', visualDensity: VisualDensity.compact, onPressed: () => _remove(code), icon: Icon(Icons.delete_outline, size: 20, color: k.red)),
          ]),
        ]),
      ),
    );
  }
}

class _LimitSheet extends StatefulWidget {
  final String month;
  final String? code, name;
  final int? current;
  const _LimitSheet({required this.month, this.code, this.name, this.current});
  @override
  State<_LimitSheet> createState() => _LimitSheetState();
}

class _LimitSheetState extends State<_LimitSheet> {
  late final _amount = TextEditingController(text: widget.current == null ? '' : '${widget.current! / 100}'.replaceAll(RegExp(r'\.0$'), ''));
  String? _cat, _error;
  bool _busy = false;

  @override
  void initState() { super.initState(); _cat = widget.code; }
  @override
  void dispose() { _amount.dispose(); super.dispose(); }

  Future<void> _save() async {
    final p = toPaise(_amount.text);
    if (_cat == null) { setState(() => _error = 'Choose a category'); return; }
    if (p == null) { setState(() => _error = 'Enter a limit like 5,000'); return; }
    setState(() { _busy = true; _error = null; });
    try {
      await Api.instance.put('/me/budgets', {'month': widget.month, 'category_code': _cat, 'amount_paise': p});
      if (mounted) Navigator.pop(context, true);
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    } finally { if (mounted) setState(() => _busy = false); }
  }

  @override
  Widget build(BuildContext context) {
    final k = Palette.of(context);
    return Padding(
      padding: EdgeInsets.fromLTRB(20, 20, 20, 20 + MediaQuery.of(context).viewInsets.bottom),
      child: SingleChildScrollView(
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [Expanded(child: Text(widget.name == null ? 'Set a limit' : 'Limit for ${widget.name}', style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w700))), IconButton(tooltip: 'Close', onPressed: () => Navigator.pop(context, false), icon: const Icon(Icons.close))]),
          Text(monthName(widget.month), style: TextStyle(color: k.muted)),
          const SizedBox(height: 12),
          if (widget.code == null) ...[CategoryDropdown(value: _cat, onChanged: (v) => setState(() => _cat = v)), const SizedBox(height: 12)],
          TextField(controller: _amount, autofocus: true, keyboardType: const TextInputType.numberWithOptions(decimal: true), style: const TextStyle(fontSize: 24, fontWeight: FontWeight.w700), decoration: const InputDecoration(labelText: 'Monthly limit (₹)', hintText: '5,000')),
          if (_error != null) Padding(padding: const EdgeInsets.only(top: 12), child: Text(_error!, style: TextStyle(color: k.red, fontWeight: FontWeight.w600))),
          const SizedBox(height: 16),
          SizedBox(width: double.infinity, child: FilledButton(onPressed: _busy ? null : _save, child: Text(_busy ? 'Saving…' : 'Save limit'))),
          const SizedBox(height: 8),
          Text('A limit of ₹0 means you plan to spend nothing there. Setting one again replaces it and keeps the old version in history.', style: TextStyle(color: k.muted, fontSize: 12)),
        ]),
      ),
    );
  }
}

