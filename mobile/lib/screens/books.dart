import 'package:flutter/material.dart';

import '../api.dart';
import '../format.dart';
import '../theme.dart';
import '../ui/widgets.dart';

const _banks = {'SBIN': 'State Bank of India', 'HDFC': 'HDFC Bank', 'ICIC': 'ICICI Bank', 'UTIB': 'Axis Bank', 'KKBK': 'Kotak Mahindra Bank', 'BARB': 'Bank of Baroda', 'PUNB': 'Punjab National Bank', 'CNRB': 'Canara Bank', 'OTHR': 'Other bank'};
const _upiApps = {'PHPE': 'PhonePe', 'GPAY': 'Google Pay', 'PTYM': 'Paytm', 'BHIM': 'BHIM', 'AMZN': 'Amazon Pay', 'OTHR': 'Other (type a name)'};

class Books extends StatefulWidget {
  final Me me;
  final VoidCallback onSignOut, onChanged;
  const Books({super.key, required this.me, required this.onSignOut, required this.onChanged});
  @override
  State<Books> createState() => _BooksState();
}

class _BooksState extends State<Books> {
  Future<void> _add() async {
    final ok = await showModalBottomSheet<bool>(context: context, isScrollControlled: true, useSafeArea: true, builder: (_) => const _AddAccount());
    if (ok == true) widget.onChanged();
  }

  @override
  Widget build(BuildContext context) {
    final k = Palette.of(context);
    return RefreshIndicator(
      onRefresh: () async => setState(() {}),
      child: ListView(padding: const EdgeInsets.fromLTRB(16, 16, 16, 24), children: [
        const Text('Books', style: TextStyle(fontSize: 26, fontWeight: FontWeight.w700, letterSpacing: -.4)),
        const SizedBox(height: 4),
        Text(widget.me.email, style: TextStyle(color: k.muted)),
        Loader<List<dynamic>>(
          load: () async {
            final r = await Future.wait([Api.instance.get('/me/accounts'), Api.instance.get('/me/profile')]);
            return r;
          },
          builder: (context, r) {
            final accts = (r[0] as List).cast<Map<String, dynamic>>();
            final sample = (r[1] as Map<String, dynamic>)['sample'] == true;
            return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              SectionTitle('Accounts', trailing: sample ? null : TextButton.icon(onPressed: _add, icon: const Icon(Icons.add, size: 18), label: const Text('Add'))),
              if (sample) Padding(padding: const EdgeInsets.only(top: 8), child: Stamp('Sample household · read-only', k.blue)),
              if (accts.isEmpty) const EmptyState('No accounts yet', hint: 'Add a savings account, credit card or UPI app to start writing entries.'),
              for (final a in accts)
                Container(
                  padding: const EdgeInsets.symmetric(vertical: 12),
                  decoration: BoxDecoration(border: Border(bottom: BorderSide(color: k.rule))),
                  child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      Text(a['display_name'] as String, style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 16)),
                      Text('${_upiApps[a['bank_code']] ?? _banks[a['bank_code']] ?? a['bank_code']}${a['vpa'] != null ? ' · ${a['vpa']}' : ''}', style: TextStyle(color: k.muted, fontSize: 13)),
                    ])),
                    Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
                      Money(a['balance_paise'] as int, big: true, color: (a['balance_paise'] as int) < 0 ? k.red : null),
                      const SizedBox(height: 4),
                      statusStamp(context, a['status'] as String),
                    ]),
                  ]),
                ),
            ]);
          },
        ),
        const SizedBox(height: 28),
        OutlinedButton.icon(onPressed: widget.onSignOut, icon: const Icon(Icons.logout), label: const Text('Sign out')),
        const SizedBox(height: 12),
        Text('Server: ${Uri.parse(apiBase).host}', style: TextStyle(color: k.muted, fontSize: 12)),
      ]),
    );
  }
}

class _AddAccount extends StatefulWidget {
  const _AddAccount();
  @override
  State<_AddAccount> createState() => _AddAccountState();
}

class _AddAccountState extends State<_AddAccount> {
  String _type = 'SAVINGS', _bank = 'HDFC';
  final _last4 = TextEditingController(), _vpa = TextEditingController(), _balance = TextEditingController(), _label = TextEditingController();
  bool _busy = false;
  String? _error;

  @override
  void dispose() { _last4.dispose(); _vpa.dispose(); _balance.dispose(); _label.dispose(); super.dispose(); }

  Future<void> _save() async {
    if (_type == 'UPI' && _bank == 'OTHR' && _label.text.trim().isEmpty) { setState(() => _error = 'Type a name for this UPI app'); return; }
    setState(() { _busy = true; _error = null; });
    try {
      await Api.instance.post('/me/accounts', {
        'account_type': _type, 'bank_code': _bank, if (_label.text.trim().isNotEmpty) 'label': _label.text.trim(),
        if (_last4.text.isNotEmpty && _type != 'UPI') 'last4': _last4.text,
        if (_vpa.text.trim().isNotEmpty && _type != 'CREDIT_CARD') 'vpa': _vpa.text.trim(),
        'opening_balance_paise': _balance.text.isEmpty ? 0 : (toPaise(_balance.text) ?? 0),
      });
      if (mounted) Navigator.pop(context, true);
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
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [const Expanded(child: Text('Add an account', style: TextStyle(fontSize: 20, fontWeight: FontWeight.w700))), IconButton(tooltip: 'Close', onPressed: () => Navigator.pop(context, false), icon: const Icon(Icons.close))]),
          const SizedBox(height: 8),
          SegmentedButton<String>(
            segments: const [ButtonSegment(value: 'SAVINGS', label: Text('Savings')), ButtonSegment(value: 'CREDIT_CARD', label: Text('Card')), ButtonSegment(value: 'UPI', label: Text('UPI app'))],
            selected: {_type}, showSelectedIcon: false,
            onSelectionChanged: (v) => setState(() { _type = v.first; _bank = _type == 'UPI' ? 'PHPE' : 'HDFC'; _label.clear(); }),
          ),
          const SizedBox(height: 14),
          DropdownButtonFormField<String>(
            key: ValueKey(_type), initialValue: _bank, isExpanded: true, decoration: InputDecoration(labelText: _type == 'UPI' ? 'UPI app' : 'Bank'),
            items: [for (final e in (_type == 'UPI' ? _upiApps : _banks).entries) DropdownMenuItem(value: e.key, child: Text(e.value))],
            onChanged: (v) => setState(() => _bank = v ?? _bank),
          ),
          if (_bank == 'OTHR') ...[const SizedBox(height: 12), TextField(controller: _label, maxLength: 40, decoration: InputDecoration(labelText: _type == 'UPI' ? 'App name' : 'Bank name (optional)', counterText: ''))],
          if (_type != 'UPI') ...[const SizedBox(height: 12), TextField(controller: _last4, keyboardType: TextInputType.number, maxLength: 4, decoration: const InputDecoration(labelText: 'Last 4 digits (optional)', counterText: ''))],
          if (_type != 'CREDIT_CARD') ...[const SizedBox(height: 12), TextField(controller: _vpa, autocorrect: false, decoration: InputDecoration(labelText: 'Your UPI ID (optional)', hintText: _type == 'UPI' ? 'name@ybl' : 'name@okhdfcbank', helperText: 'Lets PAM recognise payments between your own accounts'))],
          const SizedBox(height: 12),
          TextField(controller: _balance, keyboardType: const TextInputType.numberWithOptions(decimal: true), decoration: InputDecoration(labelText: _type == 'CREDIT_CARD' ? 'Amount owed today (₹, optional)' : _type == 'UPI' ? 'Wallet balance today (₹, optional)' : 'Balance when you start (₹, optional)')),
          if (_error != null) Padding(padding: const EdgeInsets.only(top: 12), child: Text(_error!, style: TextStyle(color: k.red, fontWeight: FontWeight.w600))),
          const SizedBox(height: 16),
          SizedBox(width: double.infinity, child: FilledButton(onPressed: _busy ? null : _save, child: Text(_busy ? 'Adding…' : 'Add account'))),
        ]),
      ),
    );
  }
}
