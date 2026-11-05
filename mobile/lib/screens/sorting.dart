import 'package:flutter/material.dart';

import '../api.dart';
import '../theme.dart';
import '../ui/widgets.dart';

/// "Remember my choice" rules and the optional AI sorter. Both only touch entries PAM could not sort.
class SortingScreen extends StatefulWidget {
  const SortingScreen({super.key});
  @override
  State<SortingScreen> createState() => _SortingScreenState();
}

class _SortingScreenState extends State<SortingScreen> {
  int _rev = 0;
  bool _busy = false;
  String? _msg, _err;

  Future<void> _do(Future<void> Function() f) async {
    setState(() { _busy = true; _msg = null; _err = null; });
    try { await f(); } on ApiException catch (e) { _err = e.message; }
    if (mounted) setState(() { _busy = false; _rev++; });
  }

  @override
  Widget build(BuildContext context) {
    final k = Palette.of(context);
    return Scaffold(
      appBar: AppBar(title: const Text('Sorting')),
      body: ListView(padding: const EdgeInsets.fromLTRB(16, 8, 16, 32), children: [
        const SectionTitle('Rules you made'),
        const SizedBox(height: 6),
        Text('When you change an unsorted entry\'s category and keep "Remember" ticked, PAM files similar narrations the same way from then on. Removing a rule only affects future entries.', style: TextStyle(color: k.muted)),
        Loader<List<dynamic>>(
          key: ValueKey('r$_rev'), rows: 3,
          load: () async => (await Api.instance.get('/me/sorting-rules')) as List,
          builder: (context, rules) => rules.isEmpty
              ? const Padding(padding: EdgeInsets.only(top: 12), child: Text('None yet.'))
              : Column(children: [
                  for (final r in rules.cast<Map<String, dynamic>>())
                    Container(
                      padding: const EdgeInsets.symmetric(vertical: 10),
                      decoration: BoxDecoration(border: Border(bottom: BorderSide(color: k.rule))),
                      child: Row(children: [
                        Expanded(child: Text.rich(TextSpan(children: [
                          TextSpan(text: '“${r['phrase']}” ', style: const TextStyle(fontWeight: FontWeight.w700)),
                          TextSpan(text: '(${r['direction'] == 'DR' ? 'money out' : 'money in'}) goes to ', style: TextStyle(color: k.muted)),
                          TextSpan(text: '${r['category_name'] ?? r['category_code']}', style: const TextStyle(fontWeight: FontWeight.w700)),
                        ]))),
                        IconButton(tooltip: 'Remove rule', onPressed: _busy ? null : () => _do(() async { await Api.instance.delete('/me/sorting-rules/${r['rule_id']}'); }), icon: Icon(Icons.delete_outline, color: k.red)),
                      ]),
                    ),
                ]),
        ),
        const SectionTitle('AI sorting (optional)'),
        Loader<Map<String, dynamic>>(
          key: ValueKey('a$_rev'), rows: 3,
          load: () async => (await Api.instance.get('/me/ai')) as Map<String, dynamic>,
          builder: (context, a) {
            if (a['available'] != true) return const Padding(padding: EdgeInsets.only(top: 12), child: Text('Not set up on this server. The owner can switch it on by adding a Gemini API key.'));
            final on = a['enabled'] == true;
            return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              SwitchListTile(
                contentPadding: EdgeInsets.zero, value: on,
                onChanged: _busy ? null : (v) => _do(() async { await Api.instance.put('/me/ai', {'enabled': v}); }),
                title: Text('Let ${a['provider']} suggest categories for entries PAM could not sort', style: const TextStyle(fontWeight: FontWeight.w700)),
                subtitle: Text('${a['what_is_sent']} Suggestions only apply when you press the button, show as "AI" in the entry\'s history, and you can change any of them.'),
              ),
              if (on) FilledButton(onPressed: _busy ? null : () => _do(() async {
                final r = await Api.instance.post('/me/ai/sort', {}) as Map<String, dynamic>;
                _msg = '${r['sorted']} sorted${(r['left'] as int) > 0 ? ', ${r['left']} left for you' : ''}.';
              }), child: Text(_busy ? 'Asking…' : 'Sort my unsorted entries')),
              if (_msg != null) Padding(padding: const EdgeInsets.only(top: 10), child: Text(_msg!, style: TextStyle(color: k.green, fontWeight: FontWeight.w600))),
              if (_err != null) Padding(padding: const EdgeInsets.only(top: 10), child: Text(_err!, style: TextStyle(color: k.red, fontWeight: FontWeight.w600))),
            ]);
          },
        ),
      ]),
    );
  }
}

/// Shortcut above the Unsorted list when AI sorting is on.
class AiInline extends StatefulWidget {
  final VoidCallback onDone;
  const AiInline({super.key, required this.onDone});
  @override
  State<AiInline> createState() => _AiInlineState();
}

class _AiInlineState extends State<AiInline> {
  bool _on = false, _busy = false;
  String? _msg;
  @override
  void initState() {
    super.initState();
    Api.instance.get('/me/ai').then((a) { if (mounted) setState(() => _on = (a as Map)['available'] == true && a['enabled'] == true); }).catchError((_) {});
  }

  @override
  Widget build(BuildContext context) {
    if (!_on) return const SizedBox.shrink();
    final k = Palette.of(context);
    return Container(
      margin: const EdgeInsets.only(top: 10), padding: const EdgeInsets.all(12), decoration: BoxDecoration(color: k.sheet, border: Border.all(color: k.ruleStrong)),
      child: Row(children: [
        Expanded(child: Text(_msg ?? 'Let Gemini suggest categories for these. Sure answers are applied and marked "AI".', style: const TextStyle(fontSize: 13))),
        const SizedBox(width: 8),
        FilledButton(onPressed: _busy ? null : () async {
          setState(() => _busy = true);
          try {
            final r = await Api.instance.post('/me/ai/sort', {}) as Map<String, dynamic>;
            _msg = '${r['sorted']} sorted, ${r['left']} left.';
            widget.onDone();
          } catch (e) { if (mounted) showError(context, e); }
          if (mounted) setState(() => _busy = false);
        }, child: Text(_busy ? '…' : 'Sort with AI')),
      ]),
    );
  }
}
