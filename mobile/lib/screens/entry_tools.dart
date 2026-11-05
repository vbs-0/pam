import 'dart:convert';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../api.dart';
import '../format.dart';
import '../theme.dart';
import '../ui/widgets.dart';
import 'entries.dart';

Future<List<Map<String, dynamic>>> activeAccounts() async =>
    ((await Api.instance.get('/me/accounts')) as List).cast<Map<String, dynamic>>().where((a) => a['status'] == 'ACTIVE').toList();

Widget _head(BuildContext c, String title, [bool? result]) => Row(children: [
      Expanded(child: Text(title, style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w700))),
      IconButton(tooltip: 'Close', onPressed: () => Navigator.pop(c, result ?? false), icon: const Icon(Icons.close)),
    ]);

Widget _err(Palette k, String? e) => e == null ? const SizedBox.shrink() : Padding(padding: const EdgeInsets.only(top: 12), child: Text(e, style: TextStyle(color: k.red, fontWeight: FontWeight.w600)));

EdgeInsets _pad(BuildContext c) => EdgeInsets.fromLTRB(20, 20, 20, 20 + MediaQuery.of(c).viewInsets.bottom);

// ---------------------------------------------------------------- edit amount / date / narration / direction

class EditEntrySheet extends StatefulWidget {
  final Map<String, dynamic> txn;
  const EditEntrySheet({super.key, required this.txn});
  @override
  State<EditEntrySheet> createState() => _EditEntrySheetState();
}

class _EditEntrySheetState extends State<EditEntrySheet> {
  late final _desc = TextEditingController(text: widget.txn['descriptor'] as String);
  late final _amount = TextEditingController(text: '${(widget.txn['amount_paise'] as int).abs() / 100}'.replaceAll(RegExp(r'\.0$'), ''));
  late String _date = widget.txn['local_date'] as String;
  late bool _out = (widget.txn['amount_paise'] as int) < 0;
  String? _error;
  bool _busy = false;

  @override
  void dispose() { _desc.dispose(); _amount.dispose(); super.dispose(); }

  Future<void> _pick() async {
    final d = await showDatePicker(context: context, initialDate: DateTime.parse(_date), firstDate: DateTime(2020), lastDate: DateTime.parse(todayIso()));
    if (d != null) setState(() => _date = d.toIso8601String().substring(0, 10));
  }

  Future<void> _save() async {
    final p = toPaise(_amount.text);
    if (p == null || p == 0) { setState(() => _error = 'Enter an amount like 1,250.50'); return; }
    if (_desc.text.trim().isEmpty) { setState(() => _error = 'Say what it was for'); return; }
    setState(() { _busy = true; _error = null; });
    try {
      await Api.instance.patch('/me/transactions/${widget.txn['txn_id']}', {'description': _desc.text.trim(), 'amount_paise': p, 'date': _date, 'direction': _out ? 'DR' : 'CR'});
      if (mounted) Navigator.pop(context, true);
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    } finally { if (mounted) setState(() => _busy = false); }
  }

  @override
  Widget build(BuildContext context) {
    final k = Palette.of(context);
    return Padding(
      padding: _pad(context),
      child: SingleChildScrollView(
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          _head(context, 'Edit entry'),
          const SizedBox(height: 8),
          SegmentedButton<bool>(segments: const [ButtonSegment(value: true, label: Text('Money out')), ButtonSegment(value: false, label: Text('Money in'))], selected: {_out}, showSelectedIcon: false, onSelectionChanged: (v) => setState(() => _out = v.first)),
          const SizedBox(height: 14),
          TextField(controller: _amount, keyboardType: const TextInputType.numberWithOptions(decimal: true), style: const TextStyle(fontSize: 24, fontWeight: FontWeight.w700), decoration: const InputDecoration(labelText: 'Amount (₹)')),
          const SizedBox(height: 12),
          TextField(controller: _desc, maxLength: 160, textCapitalization: TextCapitalization.sentences, decoration: const InputDecoration(labelText: 'Narration')),
          OutlinedButton.icon(onPressed: _pick, icon: const Icon(Icons.calendar_today, size: 18), label: Text('${dayLabel(_date)} ${_date.substring(0, 4)}')),
          _err(k, _error),
          const SizedBox(height: 16),
          SizedBox(width: double.infinity, child: FilledButton(onPressed: _busy ? null : _save, child: Text(_busy ? 'Saving…' : 'Save changes'))),
        ]),
      ),
    );
  }
}

// ---------------------------------------------------------------- split across categories

class SplitSheet extends StatefulWidget {
  final Map<String, dynamic> txn;
  const SplitSheet({super.key, required this.txn});
  @override
  State<SplitSheet> createState() => _SplitSheetState();
}

class _SplitSheetState extends State<SplitSheet> {
  final _amounts = [TextEditingController(), TextEditingController()];
  final _cats = <String?>[null, null];
  String? _error;
  bool _busy = false;

  int get _total => (widget.txn['amount_paise'] as int).abs();
  int get _sum => _amounts.fold(0, (s, c) => s + (toPaise(c.text) ?? 0));

  @override
  void dispose() { for (final c in _amounts) { c.dispose(); } super.dispose(); }

  Future<void> _save() async {
    final parts = <Map<String, dynamic>>[];
    for (var i = 0; i < _amounts.length; i++) {
      final p = toPaise(_amounts[i].text);
      if (p == null || p == 0) { setState(() => _error = 'Part ${i + 1} needs an amount'); return; }
      parts.add({'amount_paise': p, if (_cats[i] != null) 'category_code': _cats[i]});
    }
    setState(() { _busy = true; _error = null; });
    try {
      await Api.instance.post('/me/transactions/${widget.txn['txn_id']}/split', {'parts': parts});
      if (mounted) Navigator.pop(context, true);
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    } finally { if (mounted) setState(() => _busy = false); }
  }

  @override
  Widget build(BuildContext context) {
    final k = Palette.of(context);
    final left = _total - _sum;
    return Padding(
      padding: _pad(context),
      child: SingleChildScrollView(
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          _head(context, 'Split ${inr(_total)}'),
          Text('Each part becomes its own entry in its own category. The parts must add up to the original.', style: TextStyle(color: k.muted)),
          const SizedBox(height: 12),
          for (var i = 0; i < _amounts.length; i++)
            Padding(
              padding: const EdgeInsets.only(bottom: 10),
              child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                SizedBox(width: 108, child: TextField(controller: _amounts[i], keyboardType: const TextInputType.numberWithOptions(decimal: true), onChanged: (_) => setState(() {}), decoration: InputDecoration(labelText: 'Part ${i + 1} ₹'))),
                const SizedBox(width: 8),
                Expanded(child: CategoryDropdown(value: _cats[i], blank: 'Let PAM decide', onChanged: (v) => setState(() => _cats[i] = v))),
                if (_amounts.length > 2) IconButton(tooltip: 'Remove part', onPressed: () => setState(() { _amounts.removeAt(i).dispose(); _cats.removeAt(i); }), icon: const Icon(Icons.close)),
              ]),
            ),
          if (_amounts.length < 10) TextButton.icon(onPressed: () => setState(() { _amounts.add(TextEditingController()); _cats.add(null); }), icon: const Icon(Icons.add), label: const Text('Add a part')),
          Text(left == 0 ? 'Adds up.' : left > 0 ? '${inr(left)} still to place' : '${inr(-left)} too much', style: TextStyle(color: left == 0 ? k.green : k.amber, fontWeight: FontWeight.w700)),
          _err(k, _error),
          const SizedBox(height: 14),
          SizedBox(width: double.infinity, child: FilledButton(onPressed: _busy || left != 0 ? null : _save, child: Text(_busy ? 'Splitting…' : 'Split entry'))),
        ]),
      ),
    );
  }
}

// ---------------------------------------------------------------- note and tags

class NoteSection extends StatefulWidget {
  final Map<String, dynamic> txn;
  final bool canWrite;
  final VoidCallback onSaved;
  const NoteSection({super.key, required this.txn, required this.canWrite, required this.onSaved});
  @override
  State<NoteSection> createState() => _NoteSectionState();
}

class _NoteSectionState extends State<NoteSection> {
  late final _note = TextEditingController(text: (widget.txn['note'] as String?) ?? '');
  late final _tags = TextEditingController(text: ((widget.txn['tags'] as List?) ?? const []).join(', '));
  bool _busy = false;

  @override
  void dispose() { _note.dispose(); _tags.dispose(); super.dispose(); }

  Future<void> _save() async {
    setState(() => _busy = true);
    try {
      final tags = _tags.text.split(RegExp(r'[,\s]+')).map((t) => t.replaceFirst('#', '').trim()).where((t) => t.isNotEmpty).take(8).toList();
      await Api.instance.put('/me/transactions/${widget.txn['txn_id']}/note', {'note': _note.text.trim(), 'tags': tags});
      widget.onSaved();
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Note saved'), behavior: SnackBarBehavior.floating));
    } catch (e) { if (mounted) showError(context, e); }
    if (mounted) setState(() => _busy = false);
  }

  @override
  Widget build(BuildContext context) {
    final k = Palette.of(context);
    if (!widget.canWrite) {
      final n = (widget.txn['note'] as String?) ?? '';
      return n.isEmpty ? const SizedBox.shrink() : Padding(padding: const EdgeInsets.only(top: 8), child: Text('Note: $n', style: TextStyle(color: k.muted)));
    }
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const SectionTitle('Note and tags'),
      const SizedBox(height: 10),
      TextField(controller: _note, maxLength: 300, minLines: 1, maxLines: 3, decoration: const InputDecoration(labelText: 'Private note', hintText: 'Shared with Riya', counterText: '')),
      const SizedBox(height: 10),
      TextField(controller: _tags, decoration: const InputDecoration(labelText: 'Tags', hintText: 'trip, tax, reimbursable')),
      const SizedBox(height: 10),
      OutlinedButton(onPressed: _busy ? null : _save, child: Text(_busy ? 'Saving…' : 'Save note')),
    ]);
  }
}

// ---------------------------------------------------------------- transfer between own accounts

class TransferSheet extends StatefulWidget {
  const TransferSheet({super.key});
  @override
  State<TransferSheet> createState() => _TransferSheetState();
}

class _TransferSheetState extends State<TransferSheet> {
  final _amount = TextEditingController();
  String? _from, _to, _error;
  String _date = todayIso();
  bool _busy = false;
  late final Future<List<Map<String, dynamic>>> _accounts = activeAccounts();

  @override
  void dispose() { _amount.dispose(); super.dispose(); }

  Future<void> _go() async {
    final p = toPaise(_amount.text);
    if (p == null || p == 0) { setState(() => _error = 'Enter an amount'); return; }
    if (_from == _to) { setState(() => _error = 'Pick two different accounts'); return; }
    setState(() { _busy = true; _error = null; });
    try {
      await Api.instance.post('/me/transfers', {'from_account_id': _from, 'to_account_id': _to, 'amount_paise': p, 'date': _date});
      HapticFeedback.mediumImpact();
      if (mounted) Navigator.pop(context, true);
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    } finally { if (mounted) setState(() => _busy = false); }
  }

  @override
  Widget build(BuildContext context) {
    final k = Palette.of(context);
    return Padding(
      padding: _pad(context),
      child: SingleChildScrollView(
        child: FutureBuilder<List<Map<String, dynamic>>>(
          future: _accounts,
          builder: (context, s) {
            if (s.connectionState != ConnectionState.done) return const Skeleton(rows: 4);
            if (s.hasError) return ErrorBox(s.error!);
            final a = s.data!;
            if (a.length < 2) return Column(children: [_head(context, 'Move money'), const EmptyState('You need two accounts', hint: 'Add another account in Books, then move money between them.')]);
            _from ??= a[0]['account_id'] as String;
            _to ??= a[1]['account_id'] as String;
            DropdownButtonFormField<String> pick(String label, String? v, ValueChanged<String?> f) => DropdownButtonFormField<String>(
                  key: ValueKey('$label$v'), initialValue: v, isExpanded: true, decoration: InputDecoration(labelText: label),
                  items: [for (final x in a) DropdownMenuItem(value: x['account_id'] as String, child: Text(x['display_name'] as String, overflow: TextOverflow.ellipsis))], onChanged: f);
            return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              _head(context, 'Move money between accounts'),
              Text('Written as a matched pair. It is never counted as spending.', style: TextStyle(color: k.muted)),
              const SizedBox(height: 12),
              pick('From', _from, (v) => setState(() => _from = v)),
              const SizedBox(height: 12),
              pick('To', _to, (v) => setState(() => _to = v)),
              const SizedBox(height: 12),
              TextField(controller: _amount, autofocus: true, keyboardType: const TextInputType.numberWithOptions(decimal: true), style: const TextStyle(fontSize: 24, fontWeight: FontWeight.w700), decoration: const InputDecoration(labelText: 'Amount (₹)')),
              const SizedBox(height: 10),
              OutlinedButton.icon(
                onPressed: () async { final d = await showDatePicker(context: context, initialDate: DateTime.parse(_date), firstDate: DateTime(2020), lastDate: DateTime.parse(todayIso())); if (d != null) setState(() => _date = d.toIso8601String().substring(0, 10)); },
                icon: const Icon(Icons.calendar_today, size: 18), label: Text('${dayLabel(_date)} ${_date.substring(0, 4)}'),
              ),
              _err(k, _error),
              const SizedBox(height: 16),
              SizedBox(width: double.infinity, child: FilledButton(onPressed: _busy ? null : _go, child: Text(_busy ? 'Moving…' : 'Move money'))),
            ]);
          },
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------- CSV statement import

class ImportSheet extends StatefulWidget {
  const ImportSheet({super.key});
  @override
  State<ImportSheet> createState() => _ImportSheetState();
}

class _ImportSheetState extends State<ImportSheet> {
  String? _text, _name, _account, _error;
  Map<String, dynamic>? _preview, _dry;
  Map<String, String> _map = {};
  bool _busy = false, _done = false;
  int _imported = 0, _skipped = 0;
  late final Future<List<Map<String, dynamic>>> _accounts = activeAccounts();

  static const _fields = [('date', 'Date'), ('description', 'Narration'), ('amount', 'Amount (one column)'), ('debit', 'Debit (money out)'), ('credit', 'Credit (money in)')];

  Future<void> _pickFile() async {
    setState(() { _error = null; _preview = null; _dry = null; });
    final f = await FilePicker.pickFile(type: FileType.custom, allowedExtensions: const ['csv', 'txt']);
    if (f == null) return;
    final size = await f.length() ?? 0;
    if (size > 2000000) { setState(() => _error = 'That file is over 2 MB. Split it by year and import each part.'); return; }
    setState(() { _busy = true; _name = f.name; });
    try {
      _text = utf8.decode(await f.readAsBytes(), allowMalformed: true);
      final p = await Api.instance.post('/me/import/preview', {'csv_text': _text}) as Map<String, dynamic>;
      _preview = p;
      _map = (p['suggested_mapping'] as Map).map((k, v) => MapEntry(k as String, v as String));
    } on ApiException catch (e) {
      _error = e.message;
    }
    if (mounted) setState(() => _busy = false);
  }

  Future<void> _run(bool dry) async {
    setState(() { _busy = true; _error = null; });
    try {
      final r = await Api.instance.post('/me/import', {'account_id': _account, 'csv_text': _text, 'mapping': _map, 'dry_run': dry}) as Map<String, dynamic>;
      if (dry) { _dry = r; } else { _done = true; _imported = r['imported'] as int; _skipped = r['skipped_duplicates'] as int; HapticFeedback.mediumImpact(); }
    } on ApiException catch (e) {
      _error = e.message;
    }
    if (mounted) setState(() => _busy = false);
  }

  @override
  Widget build(BuildContext context) {
    final k = Palette.of(context);
    return Padding(
      padding: _pad(context),
      child: SingleChildScrollView(
        child: FutureBuilder<List<Map<String, dynamic>>>(
          future: _accounts,
          builder: (context, s) {
            if (s.connectionState != ConnectionState.done) return const Skeleton(rows: 4);
            final a = s.data ?? const [];
            if (a.isEmpty) return Column(children: [_head(context, 'Import a statement'), const EmptyState('Add an account first')]);
            _account ??= a.first['account_id'] as String;
            if (_done) {
              return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text('Imported $_imported entr${_imported == 1 ? 'y' : 'ies'}${_skipped > 0 ? '; $_skipped already in your register were skipped' : ''}.', style: TextStyle(color: k.green, fontWeight: FontWeight.w700, fontSize: 18)),
                const SizedBox(height: 16),
                FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Done')),
              ]);
            }
            final headers = ((_preview?['headers'] as List?) ?? const []).cast<String>();
            return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              _head(context, 'Import a bank statement'),
              Text('Download the statement as CSV from your bank, then choose it here. Nothing is saved until you confirm; rows you already have are skipped, so importing twice is safe.', style: TextStyle(color: k.muted)),
              const SizedBox(height: 12),
              DropdownButtonFormField<String>(
                initialValue: _account, isExpanded: true, decoration: const InputDecoration(labelText: 'Into which account?'),
                items: [for (final x in a) DropdownMenuItem(value: x['account_id'] as String, child: Text(x['display_name'] as String, overflow: TextOverflow.ellipsis))],
                onChanged: (v) => setState(() { _account = v; _dry = null; }),
              ),
              const SizedBox(height: 12),
              OutlinedButton.icon(onPressed: _busy ? null : _pickFile, icon: const Icon(Icons.upload_file), label: Text(_name ?? 'Choose CSV file')),
              if (_preview != null) ...[
                const SizedBox(height: 12),
                Text('Found ${_preview!['rows_total']} rows. Check each column is matched.', style: const TextStyle(fontWeight: FontWeight.w600)),
                for (final f in _fields)
                  Padding(
                    padding: const EdgeInsets.only(top: 10),
                    child: DropdownButtonFormField<String>(
                      key: ValueKey('${f.$1}${_map[f.$1]}'), initialValue: headers.contains(_map[f.$1]) ? _map[f.$1] : null, isExpanded: true, decoration: InputDecoration(labelText: f.$2),
                      items: [const DropdownMenuItem<String>(value: '', child: Text('— none —')), for (final h in headers) DropdownMenuItem(value: h, child: Text(h, overflow: TextOverflow.ellipsis))],
                      onChanged: (v) => setState(() { if (v == null || v.isEmpty) { _map.remove(f.$1); } else { _map[f.$1] = v; } _dry = null; }),
                    ),
                  ),
                const SizedBox(height: 12),
                OutlinedButton(onPressed: _busy ? null : () => _run(true), child: Text(_busy ? 'Checking…' : 'Check before importing')),
              ],
              if (_dry != null) Container(
                margin: const EdgeInsets.only(top: 14), padding: const EdgeInsets.all(12), decoration: BoxDecoration(border: Border.all(color: k.ruleStrong)),
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text('${_dry!['to_import']} will be imported · ${_dry!['skipped_duplicates']} duplicates skipped · ${_dry!['error_count']} rows with problems', style: const TextStyle(fontWeight: FontWeight.w700)),
                  for (final e in ((_dry!['errors'] as List).cast<Map<String, dynamic>>()).take(6)) Text('Row ${e['row']}: ${e['message']}', style: TextStyle(color: k.red, fontSize: 13)),
                  for (final r in ((_dry!['sample'] as List).cast<Map<String, dynamic>>()).take(4)) Text('${r['date']} · ${r['description']} · ${inr(r['amount_paise'] as int, sign: true)}', style: TextStyle(color: k.muted, fontSize: 13)),
                  const SizedBox(height: 10),
                  SizedBox(width: double.infinity, child: FilledButton(onPressed: _busy || (_dry!['to_import'] as int) == 0 ? null : () => _run(false), child: Text(_busy ? 'Importing…' : 'Import ${_dry!['to_import']} entries'))),
                ]),
              ),
              _err(k, _error),
            ]);
          },
        ),
      ),
    );
  }
}

