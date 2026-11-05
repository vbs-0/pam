import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../api.dart';
import '../format.dart';
import '../theme.dart';
import '../ui/widgets.dart';

List<Map<String, dynamic>>? _categories;
Future<List<Map<String, dynamic>>> loadCategories() async =>
    _categories ??= ((await Api.instance.get('/categories')) as List).cast<Map<String, dynamic>>().where((c) => c['active'] == true).toList();

class Entries extends StatefulWidget {
  final VoidCallback onChanged;
  const Entries({super.key, required this.onChanged});
  @override
  State<Entries> createState() => _EntriesState();
}

class _EntriesState extends State<Entries> {
  String _month = currentMonth();
  String _q = '';
  final _items = <Map<String, dynamic>>[];
  String? _cursor;
  bool _loading = true, _more = false, _sample = true;
  Object? _error;

  @override
  void initState() { super.initState(); _reload(); }

  Future<void> _reload() async {
    setState(() { _loading = true; _error = null; _items.clear(); _cursor = null; });
    try {
      final p = await Api.instance.get('/me/profile') as Map<String, dynamic>;
      _sample = p['sample'] == true;
      await _page();
    } catch (e) {
      _error = e;
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _page() async {
    final r = await Api.instance.get('/me/transactions', {'month': _month, 'q': _q, 'cursor': _cursor, 'limit': '40'}) as Map<String, dynamic>;
    _items.addAll((r['items'] as List).cast<Map<String, dynamic>>());
    _cursor = r['next_cursor'] as String?;
  }

  Future<void> _loadMore() async {
    setState(() => _more = true);
    try { await _page(); } catch (e) { if (mounted) showError(context, e); }
    if (mounted) setState(() => _more = false);
  }

  Future<void> _open(Map<String, dynamic> t) async {
    final changed = await showModalBottomSheet<bool>(
      context: context, isScrollControlled: true, useSafeArea: true,
      builder: (_) => EntrySheet(txnId: t['txn_id'] as String, canWrite: !_sample),
    );
    if (changed == true) { widget.onChanged(); }
  }

  /// Swipe right to change the category, swipe left to delete (with a five-second undo). Sample households are read-only.
  Widget _swipeable(Map<String, dynamic> t) {
    final k = Palette.of(context);
    Widget bg(Alignment a, Color c, IconData i, String label) => Container(
          color: c, alignment: a, padding: const EdgeInsets.symmetric(horizontal: 20),
          child: Row(mainAxisSize: MainAxisSize.min, children: [Icon(i, color: Colors.white), const SizedBox(width: 8), Text(label, style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w700))]),
        );
    return Dismissible(
      key: ValueKey(t['txn_id']),
      direction: _sample ? DismissDirection.startToEnd : DismissDirection.horizontal,
      background: bg(Alignment.centerLeft, k.blue, Icons.sell_outlined, 'Category'),
      secondaryBackground: bg(Alignment.centerRight, k.red, Icons.delete_outline, 'Delete'),
      confirmDismiss: (dir) async {
        HapticFeedback.selectionClick();
        if (dir == DismissDirection.startToEnd) { await _open(t); return false; }
        return true;
      },
      onDismissed: (_) => _deleteWithUndo(t),
      child: _Row(t, onTap: () => _open(t)),
    );
  }

  void _deleteWithUndo(Map<String, dynamic> t) {
    final at = _items.indexOf(t);
    setState(() => _items.remove(t));
    HapticFeedback.mediumImpact();
    final messenger = ScaffoldMessenger.of(context);
    messenger.clearSnackBars();
    messenger.showSnackBar(SnackBar(
      content: const Text('Entry deleted'), behavior: SnackBarBehavior.floating, duration: const Duration(seconds: 5),
      action: SnackBarAction(label: 'Undo', onPressed: () {}),
    )).closed.then((reason) async {
      if (reason == SnackBarClosedReason.action) {
        if (mounted) setState(() => _items.insert(at.clamp(0, _items.length), t));
        return;
      }
      try {
        await Api.instance.delete('/me/transactions/${t['txn_id']}');
        widget.onChanged();
      } catch (e) {
        if (mounted) { setState(() => _items.insert(at.clamp(0, _items.length), t)); showError(context, e); }
      }
    });
  }

  Future<void> _add() async {
    final added = await showModalBottomSheet<bool>(context: context, isScrollControlled: true, useSafeArea: true, builder: (_) => const AddEntrySheet());
    if (added == true) widget.onChanged();
  }

  @override
  Widget build(BuildContext context) {
    final k = Palette.of(context);
    return Scaffold(
      backgroundColor: Colors.transparent,
      floatingActionButton: _sample || _loading ? null : FloatingActionButton.extended(onPressed: _add, backgroundColor: k.blue, foregroundColor: k.paper, shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(2)), icon: const Icon(Icons.add), label: const Text('Add entry')),
      body: RefreshIndicator(
        onRefresh: _reload,
        child: ListView(padding: const EdgeInsets.fromLTRB(16, 16, 16, 90), children: [
          const Text('Entries', style: TextStyle(fontSize: 26, fontWeight: FontWeight.w700, letterSpacing: -.4)),
          const SizedBox(height: 12),
          MonthBar(_month, (m) { _month = m; _reload(); }),
          const SizedBox(height: 10),
          TextField(
            decoration: const InputDecoration(hintText: 'Search narration', prefixIcon: Icon(Icons.search), isDense: true),
            textInputAction: TextInputAction.search, maxLength: 60, buildCounter: (_, {required currentLength, required isFocused, maxLength}) => null,
            onSubmitted: (v) { _q = v.trim(); _reload(); },
          ),
          if (_loading) const Padding(padding: EdgeInsets.only(top: 12), child: Skeleton(rows: 8))
          else if (_error != null) Padding(padding: const EdgeInsets.only(top: 12), child: ErrorBox(_error!, retry: _reload))
          else if (_items.isEmpty) EmptyState(_q.isEmpty ? 'No entries this month' : 'No entries match “$_q”', hint: _sample || _q.isNotEmpty ? null : 'Tap Add entry to write your first one.')
          else ...[
            for (final t in _items) _swipeable(t),
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 16),
              child: Center(child: _cursor != null
                  ? OutlinedButton(onPressed: _more ? null : _loadMore, child: Text(_more ? 'Loading…' : 'Load more'))
                  : Text('End of the register · ${_items.length} entries', style: TextStyle(color: k.muted, fontSize: 13))),
            ),
          ],
        ]),
      ),
    );
  }
}

class _Row extends StatelessWidget {
  final Map<String, dynamic> t;
  final VoidCallback onTap;
  const _Row(this.t, {required this.onTap});
  @override
  Widget build(BuildContext context) {
    final k = Palette.of(context);
    final kind = t['kind'] as String;
    final struck = kind == 'TRANSFER' || kind == 'REVERSAL';
    final amt = t['amount_paise'] as int;
    return InkWell(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 11),
        decoration: BoxDecoration(border: Border(bottom: BorderSide(color: k.rule))),
        child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Container(
            width: 52, padding: const EdgeInsets.only(left: 8), margin: const EdgeInsets.only(right: 10),
            decoration: BoxDecoration(border: Border(left: BorderSide(color: k.red))),
            child: Text(dayLabel(t['local_date'] as String), style: TextStyle(color: k.blue, fontWeight: FontWeight.w700, fontSize: 13)),
          ),
          Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text((t['merchant_name'] ?? t['descriptor']) as String, maxLines: 2, overflow: TextOverflow.ellipsis,
                style: TextStyle(fontWeight: FontWeight.w600, decoration: struck ? TextDecoration.lineThrough : null, decorationColor: k.red, color: struck ? k.muted : k.ink)),
            const SizedBox(height: 3),
            Wrap(spacing: 6, runSpacing: 4, crossAxisAlignment: WrapCrossAlignment.center, children: [
              Text(titleCase(t['category_code'] as String), style: TextStyle(color: k.muted, fontSize: 13)),
              if (kind == 'UNKNOWN' || kind == 'TRANSFER' || kind == 'REFUND' || kind == 'REVERSAL') statusStamp(context, kind),
              if (t['overridden'] == true) Stamp('By hand', k.blue),
            ]),
          ])),
          const SizedBox(width: 8),
          Money(amt, sign: true, struck: struck, color: amt > 0 ? k.blue : null),
        ]),
      ),
    );
  }
}

class CategoryDropdown extends StatelessWidget {
  final String? value;
  final ValueChanged<String?> onChanged;
  final String blank;
  const CategoryDropdown({super.key, required this.value, required this.onChanged, this.blank = 'Choose a category'});
  @override
  Widget build(BuildContext context) => FutureBuilder<List<Map<String, dynamic>>>(
        future: loadCategories(),
        builder: (context, s) {
          final cats = s.data ?? const [];
          return DropdownButtonFormField<String>(
            initialValue: value, isExpanded: true, decoration: InputDecoration(labelText: 'Category', hintText: blank),
            items: [for (final c in cats) DropdownMenuItem(value: c['code'] as String, child: Text(c['name'] as String, overflow: TextOverflow.ellipsis))],
            onChanged: s.hasData ? onChanged : null,
          );
        },
      );
}

class EntrySheet extends StatefulWidget {
  final String txnId;
  final bool canWrite;
  const EntrySheet({super.key, required this.txnId, required this.canWrite});
  @override
  State<EntrySheet> createState() => _EntrySheetState();
}

class _EntrySheetState extends State<EntrySheet> {
  String? _cat;
  bool _busy = false, _changed = false, _confirm = false;
  late Future<Map<String, dynamic>> _f = _load();
  Future<Map<String, dynamic>> _load() async => (await Api.instance.get('/me/transactions/${widget.txnId}')) as Map<String, dynamic>;

  Future<void> _save() async {
    setState(() => _busy = true);
    try {
      await Api.instance.post('/me/transactions/${widget.txnId}/category', {'category_code': _cat});
      _changed = true; _cat = null; _f = _load();
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Saved. Budgets are already updated.'), behavior: SnackBarBehavior.floating));
    } catch (e) { if (mounted) showError(context, e); }
    if (mounted) setState(() => _busy = false);
  }

  Future<void> _delete() async {
    setState(() => _busy = true);
    try { await Api.instance.delete('/me/transactions/${widget.txnId}'); if (mounted) Navigator.pop(context, true); }
    catch (e) { if (mounted) { showError(context, e); setState(() => _busy = false); } }
  }

  @override
  Widget build(BuildContext context) {
    final k = Palette.of(context);
    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) { if (!didPop) Navigator.pop(context, _changed); },
      child: Padding(
        padding: EdgeInsets.fromLTRB(20, 20, 20, 20 + MediaQuery.of(context).viewInsets.bottom),
        child: SingleChildScrollView(
          child: FutureBuilder<Map<String, dynamic>>(
            future: _f,
            builder: (context, s) {
              if (s.connectionState != ConnectionState.done) return const Skeleton(rows: 6);
              if (s.hasError) return ErrorBox(s.error!, retry: () => setState(() => _f = _load()));
              final t = s.data!;
              final amt = t['amount_paise'] as int;
              return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Row(children: [Expanded(child: Text('${dayLabel(t['local_date'] as String)} · ${t['channel']}', style: TextStyle(color: k.muted))), IconButton(tooltip: 'Close', onPressed: () => Navigator.pop(context, _changed), icon: const Icon(Icons.close))]),
                DefaultTextStyle.merge(style: const TextStyle(fontSize: 30, fontWeight: FontWeight.w700), child: Money(amt, sign: true, big: true, color: amt > 0 ? k.blue : null)),
                const SizedBox(height: 8),
                Text((t['merchant_name'] ?? t['descriptor']) as String, style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 16)),
                if (t['merchant_name'] != null) Text(t['descriptor'] as String, style: TextStyle(color: k.muted, fontSize: 13)),
                const SizedBox(height: 12),
                Wrap(spacing: 8, crossAxisAlignment: WrapCrossAlignment.center, children: [
                  Text('Filed under ${titleCase(t['category_code'] as String)}'),
                  if (t['kind'] != 'EXPENSE') statusStamp(context, t['kind'] as String),
                ]),
                Text(t['overridden'] == true ? 'Set by hand.' : t['rule_id'] != null ? 'Rule ${t['rule_id']} v${t['rule_version']}.' : 'No rule matched.', style: TextStyle(color: k.muted, fontSize: 13)),
                const SectionTitle('Change category'),
                const SizedBox(height: 10),
                CategoryDropdown(value: _cat, onChanged: (v) => setState(() => _cat = v)),
                const SizedBox(height: 12),
                SizedBox(width: double.infinity, child: FilledButton(onPressed: _cat == null || _busy ? null : _save, child: const Text('Save category'))),
                if (widget.canWrite) ...[
                  const SizedBox(height: 18),
                  if (!_confirm) OutlinedButton(style: OutlinedButton.styleFrom(foregroundColor: k.red, side: BorderSide(color: k.red)), onPressed: () => setState(() => _confirm = true), child: const Text('Delete entry'))
                  else Row(children: [
                    Expanded(child: FilledButton(style: FilledButton.styleFrom(backgroundColor: k.red), onPressed: _busy ? null : _delete, child: const Text('Yes, delete'))),
                    const SizedBox(width: 10),
                    TextButton(onPressed: () => setState(() => _confirm = false), child: const Text('Keep')),
                  ]),
                ],
              ]);
            },
          ),
        ),
      ),
    );
  }
}

class AddEntrySheet extends StatefulWidget {
  const AddEntrySheet({super.key});
  @override
  State<AddEntrySheet> createState() => _AddEntrySheetState();
}

class _AddEntrySheetState extends State<AddEntrySheet> {
  final _amount = TextEditingController(), _desc = TextEditingController();
  bool _out = true, _busy = false;
  String? _account, _cat;
  String _date = todayIso();
  String? _error;
  Map<String, dynamic>? _saved;
  late final Future<List<Map<String, dynamic>>> _accounts = Api.instance.get('/me/accounts').then((r) => (r as List).cast<Map<String, dynamic>>().where((a) => a['status'] == 'ACTIVE').toList());

  @override
  void dispose() { _amount.dispose(); _desc.dispose(); super.dispose(); }

  Future<void> _pickDate() async {
    final now = DateTime.parse(todayIso());
    final d = await showDatePicker(context: context, initialDate: DateTime.parse(_date), firstDate: DateTime(2020), lastDate: now);
    if (d != null) setState(() => _date = d.toIso8601String().substring(0, 10));
  }

  Future<void> _submit() async {
    final paise = toPaise(_amount.text);
    if (paise == null || paise == 0) { setState(() => _error = 'Enter an amount like 1,250.50'); return; }
    if (_desc.text.trim().isEmpty) { setState(() => _error = 'Say what it was for'); return; }
    setState(() { _busy = true; _error = null; });
    try {
      final r = await Api.instance.post('/me/transactions', {
        'account_id': _account, 'date': _date, 'amount_paise': paise, 'direction': _out ? 'DR' : 'CR', 'description': _desc.text.trim(),
        if (_cat != null) 'category_code': _cat,
      }) as Map<String, dynamic>;
      setState(() => _saved = r);
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final k = Palette.of(context);
    return Padding(
      padding: EdgeInsets.fromLTRB(20, 20, 20, 20 + MediaQuery.of(context).viewInsets.bottom),
      child: SingleChildScrollView(
        child: _saved != null ? _done(k) : FutureBuilder<List<Map<String, dynamic>>>(
          future: _accounts,
          builder: (context, s) {
            if (s.connectionState != ConnectionState.done) return const Skeleton(rows: 5);
            if (s.hasError) return ErrorBox(s.error!);
            final accts = s.data!;
            if (accts.isEmpty) return const EmptyState('Add an account first', hint: 'Entries live inside a savings account or credit card. Open Books to add one.');
            _account ??= accts.first['account_id'] as String;
            return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Row(children: [const Expanded(child: Text('Add entry', style: TextStyle(fontSize: 20, fontWeight: FontWeight.w700))), IconButton(tooltip: 'Close', onPressed: () => Navigator.pop(context, false), icon: const Icon(Icons.close))]),
              const SizedBox(height: 8),
              SegmentedButton<bool>(
                segments: const [ButtonSegment(value: true, label: Text('Money out')), ButtonSegment(value: false, label: Text('Money in'))],
                selected: {_out}, onSelectionChanged: (v) => setState(() => _out = v.first), showSelectedIcon: false,
              ),
              const SizedBox(height: 14),
              TextField(controller: _amount, autofocus: true, keyboardType: const TextInputType.numberWithOptions(decimal: true), style: const TextStyle(fontSize: 24, fontWeight: FontWeight.w700), decoration: const InputDecoration(labelText: 'Amount (₹)', hintText: '0.00')),
              const SizedBox(height: 12),
              TextField(controller: _desc, maxLength: 160, textCapitalization: TextCapitalization.sentences, decoration: const InputDecoration(labelText: 'What was it for?', helperText: 'Bank narration or your own words')),
              const SizedBox(height: 6),
              Row(children: [
                Expanded(child: OutlinedButton.icon(onPressed: _pickDate, icon: const Icon(Icons.calendar_today, size: 18), label: Text(dayLabel(_date) + ' ${_date.substring(0, 4)}'))),
                const SizedBox(width: 10),
                Expanded(child: DropdownButtonFormField<String>(
                  initialValue: _account, isExpanded: true, decoration: const InputDecoration(labelText: 'Account'),
                  items: [for (final a in accts) DropdownMenuItem(value: a['account_id'] as String, child: Text(a['display_name'] as String, overflow: TextOverflow.ellipsis))],
                  onChanged: (v) => setState(() => _account = v),
                )),
              ]),
              const SizedBox(height: 12),
              CategoryDropdown(value: _cat, onChanged: (v) => setState(() => _cat = v), blank: 'Let PAM decide'),
              if (_error != null) Padding(padding: const EdgeInsets.only(top: 12), child: Text(_error!, style: TextStyle(color: k.red, fontWeight: FontWeight.w600))),
              const SizedBox(height: 16),
              SizedBox(width: double.infinity, child: FilledButton(onPressed: _busy ? null : _submit, child: Text(_busy ? 'Writing…' : 'Write entry'))),
            ]);
          },
        ),
      ),
    );
  }

  Widget _done(Palette k) {
    final t = _saved!['transaction'] as Map<String, dynamic>?;
    final dup = _saved!['possible_duplicate_of'] as String?;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text(_saved!['processed'] == true ? 'Saved and sorted.' : 'Saved; it will be sorted in the next run.', style: TextStyle(color: k.green, fontWeight: FontWeight.w700, fontSize: 18)),
      if (t != null) Padding(padding: const EdgeInsets.only(top: 8), child: Text('Filed under ${titleCase(t['category_code'] as String)}${t['kind'] == 'TRANSFER' ? ' · Contra, paired with your other account, not counted as spend' : ''}.')),
      if (dup != null) Container(
        margin: const EdgeInsets.only(top: 14), padding: const EdgeInsets.all(12), decoration: BoxDecoration(border: Border.all(color: k.amber)),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text('This looks like a duplicate of $dup.', style: TextStyle(color: k.amber, fontWeight: FontWeight.w700)),
          const Text('Same account, day, amount and narration. Two identical payments in a day do happen, so it was kept.'),
          const SizedBox(height: 8),
          OutlinedButton(onPressed: () async { try { await Api.instance.delete('/me/transactions/${_saved!['txn_id']}'); if (mounted) Navigator.pop(context, true); } catch (e) { if (mounted) showError(context, e); } }, child: const Text('Remove the new one')),
        ]),
      ),
      const SizedBox(height: 18),
      Row(children: [
        Expanded(child: FilledButton(onPressed: () { _amount.clear(); _desc.clear(); setState(() { _saved = null; }); }, child: const Text('Add another'))),
        const SizedBox(width: 10),
        TextButton(onPressed: () => Navigator.pop(context, true), child: const Text('Done')),
      ]),
    ]);
  }
}
