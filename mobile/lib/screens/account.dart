import 'dart:convert';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:share_plus/share_plus.dart';

import '../api.dart';
import '../format.dart';
import '../theme.dart';
import '../ui/widgets.dart';

Widget _field(TextEditingController c, String label, {bool secret = false, TextInputType? type, String? helper, bool autofocus = false}) =>
    TextField(controller: c, obscureText: secret, autocorrect: false, enableSuggestions: !secret, keyboardType: type, autofocus: autofocus, decoration: InputDecoration(labelText: label, helperText: helper));

Widget _msg(Palette k, String? error, String? ok) => Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      if (error != null) Padding(padding: const EdgeInsets.only(top: 12), child: Text(error, style: TextStyle(color: k.red, fontWeight: FontWeight.w600))),
      if (ok != null) Padding(padding: const EdgeInsets.only(top: 12), child: Text(ok, style: TextStyle(color: k.green, fontWeight: FontWeight.w600))),
    ]);

// ---------------------------------------------------------------- password, email, delete

class SecurityScreen extends StatefulWidget {
  final Me me;
  final Future<void> Function() onMeChanged;
  final VoidCallback onDeleted;
  const SecurityScreen({super.key, required this.me, required this.onMeChanged, required this.onDeleted});
  @override
  State<SecurityScreen> createState() => _SecurityScreenState();
}

class _SecurityScreenState extends State<SecurityScreen> {
  final _cur = TextEditingController(), _new = TextEditingController(), _again = TextEditingController();
  final _mailPw = TextEditingController(), _mail = TextEditingController();
  final _delMail = TextEditingController(), _delPw = TextEditingController();
  String? _pwErr, _pwOk, _mailErr, _mailOk, _delErr;
  bool _busy = false;

  @override
  void dispose() { for (final c in [_cur, _new, _again, _mailPw, _mail, _delMail, _delPw]) { c.dispose(); } super.dispose(); }

  Future<void> _password() async {
    if (_new.text.length < 6) { setState(() { _pwErr = 'Use at least 6 characters'; _pwOk = null; }); return; }
    if (_new.text != _again.text) { setState(() { _pwErr = 'The two new passwords differ'; _pwOk = null; }); return; }
    setState(() { _busy = true; _pwErr = null; _pwOk = null; });
    try {
      final r = await Api.instance.post('/auth/change-password', {'current_password': _cur.text, 'new_password': _new.text}) as Map<String, dynamic>;
      await Api.instance.adoptToken(r['access_token'] as String);
      _cur.clear(); _new.clear(); _again.clear();
      HapticFeedback.mediumImpact();
      _pwOk = 'Password changed. Other devices were signed out.';
    } on ApiException catch (e) { _pwErr = e.message; }
    if (mounted) setState(() => _busy = false);
  }

  Future<void> _email() async {
    if (!_mail.text.contains('@')) { setState(() { _mailErr = 'Enter a valid email'; _mailOk = null; }); return; }
    setState(() { _busy = true; _mailErr = null; _mailOk = null; });
    try {
      final r = await Api.instance.post('/auth/change-email', {'password': _mailPw.text, 'new_email': _mail.text.trim()}) as Map<String, dynamic>;
      if (r['access_token'] is String) await Api.instance.adoptToken(r['access_token'] as String);
      await widget.onMeChanged();
      _mailPw.clear(); _mail.clear();
      _mailOk = 'Email changed. We also wrote to the old address.';
    } on ApiException catch (e) { _mailErr = e.message; }
    if (mounted) setState(() => _busy = false);
  }

  Future<void> _delete() async {
    final sure = await showDialog<bool>(
      context: context,
      builder: (d) => AlertDialog(
        title: const Text('Delete your account?'),
        content: const Text('This removes your login and, if nobody else shares the register, every entry in it. It cannot be undone.'),
        actions: [TextButton(onPressed: () => Navigator.pop(d, false), child: const Text('Keep it')), FilledButton(style: FilledButton.styleFrom(backgroundColor: Palette.of(context).red), onPressed: () => Navigator.pop(d, true), child: const Text('Delete for good'))],
      ),
    );
    if (sure != true) return;
    setState(() { _busy = true; _delErr = null; });
    try {
      await Api.instance.post('/auth/delete-account', {'confirm_email': _delMail.text.trim(), if (_delPw.text.isNotEmpty) 'password': _delPw.text});
      await Api.instance.signOut();
      widget.onDeleted();
      if (mounted) Navigator.of(context).popUntil((r) => r.isFirst);
      return;
    } on ApiException catch (e) { _delErr = e.message; }
    if (mounted) setState(() => _busy = false);
  }

  @override
  Widget build(BuildContext context) {
    final k = Palette.of(context);
    return Scaffold(
      appBar: AppBar(title: const Text('Account and security')),
      body: ListView(padding: const EdgeInsets.fromLTRB(16, 8, 16, 32), children: [
        const SectionTitle('Change password'),
        const SizedBox(height: 10),
        _field(_cur, 'Current password', secret: true),
        const SizedBox(height: 10),
        _field(_new, 'New password', secret: true, helper: 'At least 6 characters'),
        const SizedBox(height: 10),
        _field(_again, 'New password again', secret: true),
        _msg(k, _pwErr, _pwOk),
        const SizedBox(height: 12),
        FilledButton(onPressed: _busy ? null : _password, child: const Text('Change password')),
        const SectionTitle('Change email'),
        const SizedBox(height: 4),
        Text('Signed in as ${widget.me.email}', style: TextStyle(color: k.muted)),
        const SizedBox(height: 10),
        _field(_mail, 'New email', type: TextInputType.emailAddress),
        const SizedBox(height: 10),
        _field(_mailPw, 'Your password', secret: true),
        _msg(k, _mailErr, _mailOk),
        const SizedBox(height: 12),
        OutlinedButton(onPressed: _busy ? null : _email, child: const Text('Change email')),
        const SectionTitle('Delete account'),
        const SizedBox(height: 6),
        Text('Type your email to confirm. If you sign in with a password, enter it too.', style: TextStyle(color: k.muted)),
        const SizedBox(height: 10),
        _field(_delMail, 'Your email', type: TextInputType.emailAddress),
        const SizedBox(height: 10),
        _field(_delPw, 'Password (leave empty for Google)', secret: true),
        _msg(k, _delErr, null),
        const SizedBox(height: 12),
        OutlinedButton(style: OutlinedButton.styleFrom(foregroundColor: k.red, side: BorderSide(color: k.red)), onPressed: _busy ? null : _delete, child: const Text('Delete my account')),
      ]),
    );
  }
}

// ---------------------------------------------------------------- daily email

class NotificationsScreen extends StatefulWidget {
  const NotificationsScreen({super.key});
  @override
  State<NotificationsScreen> createState() => _NotificationsScreenState();
}

class _NotificationsScreenState extends State<NotificationsScreen> {
  Map<String, dynamic>? _p;
  Object? _error;
  bool _busy = false;

  @override
  void initState() { super.initState(); _load(); }
  Future<void> _load() async {
    try { _p = (await Api.instance.get('/me/notifications')) as Map<String, dynamic>; _error = null; } catch (e) { _error = e; }
    if (mounted) setState(() {});
  }

  Future<void> _set(String key, bool v) async {
    setState(() => _busy = true);
    try {
      final next = {..._p!, key: v};
      _p = (await Api.instance.put('/me/notifications', {'email_digest': next['email_digest'], 'bills': next['bills'], 'budgets': next['budgets'], 'cards': next['cards']})) as Map<String, dynamic>;
      HapticFeedback.selectionClick();
    } catch (e) { if (mounted) showError(context, e); }
    if (mounted) setState(() => _busy = false);
  }

  @override
  Widget build(BuildContext context) {
    final k = Palette.of(context);
    final p = _p;
    return Scaffold(
      appBar: AppBar(title: const Text('Daily email')),
      body: ListView(padding: const EdgeInsets.all(16), children: [
        if (_error != null) ErrorBox(_error!, retry: _load) else if (p == null) const Skeleton(rows: 4) else ...[
          SwitchListTile(
            contentPadding: EdgeInsets.zero, value: p['email_digest'] == true, onChanged: _busy ? null : (v) => _set('email_digest', v),
            title: const Text('Email me when something needs a look', style: TextStyle(fontWeight: FontWeight.w700)),
            subtitle: Text('One short email a day, around 8 in the morning, to ${p['email']}. Nothing is sent on quiet days.'),
          ),
          if (p['email_digest'] == true) ...[
            CheckboxListTile(contentPadding: EdgeInsets.zero, value: p['bills'] == true, onChanged: _busy ? null : (v) => _set('bills', v ?? true), title: const Text('Bills and income due')),
            CheckboxListTile(contentPadding: EdgeInsets.zero, value: p['budgets'] == true, onChanged: _busy ? null : (v) => _set('budgets', v ?? true), title: const Text('Budgets near or over their limit')),
            CheckboxListTile(contentPadding: EdgeInsets.zero, value: p['cards'] == true, onChanged: _busy ? null : (v) => _set('cards', v ?? true), title: const Text('Credit card due dates and limits')),
          ],
          if (p['mail_configured'] != true && p['email_digest'] == true) Padding(padding: const EdgeInsets.only(top: 10), child: Text('This server has no outgoing email set up yet, so nothing will arrive until the owner configures it.', style: TextStyle(color: k.amber))),
        ],
      ]),
    );
  }
}

// ---------------------------------------------------------------- household

class HouseholdScreen extends StatefulWidget {
  final VoidCallback onChanged;
  const HouseholdScreen({super.key, required this.onChanged});
  @override
  State<HouseholdScreen> createState() => _HouseholdScreenState();
}

class _HouseholdScreenState extends State<HouseholdScreen> {
  final _code = TextEditingController();
  int _rev = 0;
  String? _error;
  bool _busy = false;

  @override
  void dispose() { _code.dispose(); super.dispose(); }

  Future<void> _do(Future<void> Function() f, {bool reload = false}) async {
    setState(() { _busy = true; _error = null; });
    try { await f(); if (reload) widget.onChanged(); _rev++; } on ApiException catch (e) { _error = e.message; }
    if (mounted) setState(() => _busy = false);
  }

  @override
  Widget build(BuildContext context) {
    final k = Palette.of(context);
    return Scaffold(
      appBar: AppBar(title: const Text('Share your register')),
      body: ListView(padding: const EdgeInsets.all(16), children: [
        Text('Invite a partner or family member so you both see the same accounts and entries, each with your own login.', style: TextStyle(color: k.muted)),
        Loader<Map<String, dynamic>>(
          key: ValueKey(_rev), rows: 4,
          load: () async => (await Api.instance.get('/me/household/members')) as Map<String, dynamic>,
          builder: (context, h) {
            final members = (h['members'] as List).cast<Map<String, dynamic>>();
            final invites = (h['invites'] as List).cast<Map<String, dynamic>>();
            final iAmOwner = h['you'] == h['owner'];
            return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              const SectionTitle('Members'),
              for (final m in members)
                Container(
                  padding: const EdgeInsets.symmetric(vertical: 10),
                  decoration: BoxDecoration(border: Border(bottom: BorderSide(color: k.rule))),
                  child: Row(children: [
                    Expanded(child: Text(m['email'] as String, overflow: TextOverflow.ellipsis)),
                    if (m['you'] == true) Stamp('You', k.blue),
                    if (m['is_owner'] == true) ...[const SizedBox(width: 6), Stamp('Owner', k.muted)],
                    if (iAmOwner && m['you'] != true) TextButton(onPressed: _busy ? null : () => _do(() async { await Api.instance.delete('/me/household/members/${m['app_user_id']}'); }, reload: true), child: const Text('Remove')),
                  ]),
                ),
              if (invites.isNotEmpty) ...[
                const SectionTitle('Unused invite codes'),
                for (final i in invites)
                  ListTile(
                    contentPadding: EdgeInsets.zero,
                    title: SelectableText(i['code'] as String, style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w800, letterSpacing: 3)),
                    subtitle: const Text('Works once. Give it to them; they enter it in their own app under “Join a household”.'),
                    trailing: IconButton(tooltip: 'Share code', icon: const Icon(Icons.share), onPressed: () => SharePlus.instance.share(ShareParams(text: 'Join my household on PAM with this code: ${i['code']}'))),
                  ),
              ],
              const SizedBox(height: 14),
              Wrap(spacing: 10, runSpacing: 8, children: [
                FilledButton(onPressed: _busy ? null : () => _do(() async { await Api.instance.post('/me/household/invite', {}); }), child: const Text('Create an invite code')),
                if (members.length > 1) OutlinedButton(style: OutlinedButton.styleFrom(foregroundColor: k.red, side: BorderSide(color: k.red)), onPressed: _busy ? null : () async {
                  final ok = await showDialog<bool>(context: context, builder: (d) => AlertDialog(title: const Text('Leave this household?'), content: const Text('You will get an empty register of your own.'), actions: [TextButton(onPressed: () => Navigator.pop(d, false), child: const Text('Stay')), FilledButton(onPressed: () => Navigator.pop(d, true), child: const Text('Leave'))]));
                  if (ok == true) await _do(() async { await Api.instance.post('/me/household/leave', {}); }, reload: true);
                }, child: const Text('Leave household')),
              ]),
              const SectionTitle('Join a household'),
              const SizedBox(height: 10),
              TextField(controller: _code, textCapitalization: TextCapitalization.characters, maxLength: 12, style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w700, letterSpacing: 3), decoration: const InputDecoration(labelText: 'Invite code', helperText: 'Your own register must be empty to join', counterText: '')),
              const SizedBox(height: 10),
              OutlinedButton(onPressed: _busy ? null : () => _do(() async { await Api.instance.post('/me/household/join', {'code': _code.text.trim()}); _code.clear(); }, reload: true), child: const Text('Join')),
              if (_error != null) Padding(padding: const EdgeInsets.only(top: 12), child: Text(_error!, style: TextStyle(color: k.red, fontWeight: FontWeight.w600))),
            ]);
          },
        ),
      ]),
    );
  }
}

// ---------------------------------------------------------------- your data

class DataScreen extends StatefulWidget {
  final VoidCallback onChanged;
  const DataScreen({super.key, required this.onChanged});
  @override
  State<DataScreen> createState() => _DataScreenState();
}

class _DataScreenState extends State<DataScreen> {
  bool _busy = false;
  String? _error, _ok;
  String _from = '', _to = '';

  Future<void> _run(Future<String?> Function() f) async {
    setState(() { _busy = true; _error = null; _ok = null; });
    try { _ok = await f(); } on ApiException catch (e) { _error = e.message; } catch (_) { _error = 'Something went wrong.'; }
    if (mounted) setState(() => _busy = false);
  }

  Future<String?> _share(String path, Map<String, String?> q, String name, String mime) async {
    final text = await Api.instance.getText(path, q);
    await SharePlus.instance.share(ShareParams(files: [XFile.fromData(utf8.encode(text), name: name, mimeType: mime)], fileNameOverrides: [name], subject: name));
    return 'Ready. Choose where to save or send it.';
  }

  Future<String?> _restore() async {
    final f = await FilePicker.pickFile(type: FileType.custom, allowedExtensions: const ['json']);
    if (f == null) return null;
    dynamic backup;
    try { backup = jsonDecode(utf8.decode(await f.readAsBytes())); } catch (_) { throw ApiException(0, 'That file is not a PAM backup.'); }
    final r = await Api.instance.post('/me/restore', {'backup': backup}) as Map<String, dynamic>;
    widget.onChanged();
    return 'Restored ${r['accounts']} accounts and ${r['transactions']} entries.';
  }

  Future<void> _pick(bool from) async {
    final today = DateTime.parse(todayIso());
    final d = await showDatePicker(context: context, initialDate: today, firstDate: DateTime(2020), lastDate: today);
    if (d != null) setState(() { final v = d.toIso8601String().substring(0, 10); if (from) { _from = v; } else { _to = v; } });
  }

  @override
  Widget build(BuildContext context) {
    final k = Palette.of(context);
    return Scaffold(
      appBar: AppBar(title: const Text('Your data')),
      body: ListView(padding: const EdgeInsets.all(16), children: [
        const SectionTitle('Export entries'),
        const SizedBox(height: 6),
        Text('A spreadsheet (CSV) that opens in Excel or Google Sheets.', style: TextStyle(color: k.muted)),
        const SizedBox(height: 10),
        Row(children: [
          Expanded(child: OutlinedButton(onPressed: () => _pick(true), child: Text(_from.isEmpty ? 'From' : dayLabel(_from)))),
          const SizedBox(width: 10),
          Expanded(child: OutlinedButton(onPressed: () => _pick(false), child: Text(_to.isEmpty ? 'To' : dayLabel(_to)))),
          if (_from.isNotEmpty || _to.isNotEmpty) IconButton(tooltip: 'Clear dates', onPressed: () => setState(() { _from = ''; _to = ''; }), icon: const Icon(Icons.clear)),
        ]),
        const SizedBox(height: 10),
        FilledButton.icon(onPressed: _busy ? null : () => _run(() => _share('/me/export.csv', {'date_from': _from, 'date_to': _to}, 'pam-register-${todayIso()}.csv', 'text/csv')), icon: const Icon(Icons.ios_share), label: const Text('Export CSV')),
        const SectionTitle('Backup and restore'),
        const SizedBox(height: 6),
        Text('A complete copy of what you entered: accounts, entries, notes, budgets and goals. Restore it into an empty register, for example after starting over.', style: TextStyle(color: k.muted)),
        const SizedBox(height: 10),
        Wrap(spacing: 10, runSpacing: 8, children: [
          OutlinedButton.icon(onPressed: _busy ? null : () => _run(() => _share('/me/backup.json', const {}, 'pam-backup-${todayIso()}.json', 'application/json')), icon: const Icon(Icons.backup_outlined), label: const Text('Download backup')),
          OutlinedButton.icon(onPressed: _busy ? null : () => _run(_restore), icon: const Icon(Icons.restore), label: const Text('Restore from a backup')),
        ]),
        if (_error != null) Padding(padding: const EdgeInsets.only(top: 14), child: Text(_error!, style: TextStyle(color: k.red, fontWeight: FontWeight.w600))),
        if (_ok != null) Padding(padding: const EdgeInsets.only(top: 14), child: Text(_ok!, style: TextStyle(color: k.green, fontWeight: FontWeight.w600))),
      ]),
    );
  }
}
