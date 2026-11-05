import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:flutter/foundation.dart';
import 'package:path_provider/path_provider.dart';

import 'api.dart';
import 'format.dart';

/// Crash-safe JSON files. A write goes to a temporary file first, the previous good copy is kept as `.bak`, and only
/// then does the temporary file replace the real one, so cutting the app (or the phone) at any moment leaves either
/// the old or the new content intact, never half of each.
class Store {
  static Directory? _dir;
  static Future<File> _file(String name, [String ext = '']) async {
    _dir ??= await getApplicationSupportDirectory();
    return File('${_dir!.path}/$name.json$ext');
  }

  static Future<dynamic> read(String name) async {
    for (final ext in const ['', '.bak']) {
      try {
        final f = await _file(name, ext);
        if (await f.exists()) return jsonDecode(await f.readAsString());
      } catch (_) {/* corrupt: try the backup */}
    }
    return null;
  }

  static Future<void> write(String name, Object data) async {
    final main = await _file(name), tmp = await _file(name, '.tmp'), bak = await _file(name, '.bak');
    await tmp.writeAsString(jsonEncode(data), flush: true);
    try { if (await main.exists()) await main.copy(bak.path); } catch (_) {/* backup is best effort */}
    await tmp.rename(main.path);
  }

  static Future<void> delete(String name) async {
    for (final ext in const ['', '.bak', '.tmp']) {
      try { final f = await _file(name, ext); if (await f.exists()) await f.delete(); } catch (_) {/* ignore */}
    }
  }
}

String _rid([int n = 16]) {
  final r = Random.secure();
  return List.generate(n, (_) => r.nextInt(16).toRadixString(16)).join();
}

/// One change made by the user, waiting to be sent.
class Op {
  final String id, method, path;
  final Map<String, dynamic>? body;
  final int at;
  final List<String> temps; // ids invented on the phone for things this change creates, in the order the server returns them
  String? error;
  int attempts;
  Op(this.id, this.method, this.path, this.body, this.at, this.temps, {this.error, this.attempts = 0});
  factory Op.create(String method, String path, Map<String, dynamic>? body, {int temps = 0}) {
    final id = _rid(24);
    return Op(id, method, path, body, DateTime.now().millisecondsSinceEpoch, [for (var i = 0; i < temps; i++) 'L-${id.substring(0, 8)}-$i']);
  }
  Map<String, dynamic> toJson() => {'id': id, 'method': method, 'path': path, 'body': body, 'at': at, 'temps': temps, 'error': error, 'attempts': attempts};
  factory Op.fromJson(Map<String, dynamic> j) => Op(j['id'] as String, j['method'] as String, j['path'] as String, (j['body'] as Map?)?.cast<String, dynamic>(), j['at'] as int, (j['temps'] as List).cast<String>(), error: j['error'] as String?, attempts: (j['attempts'] as int?) ?? 0);
}

/// Paths that cannot work without the server (they check passwords, parse uploads or change who may sign in).
bool onlineOnly(String path) =>
    path.startsWith('/auth/') || path.startsWith('/me/import') || path.startsWith('/me/restore') || path.startsWith('/me/household/') || path.startsWith('/me/export') || path.startsWith('/me/backup');

/// Changes made with no signal. They are written to disk before the app says "saved", sent in order when the server
/// is reachable, and each carries a key so the server applies it once even if a send is cut off half way.
class Outbox {
  static final Outbox instance = Outbox._();
  Outbox._();

  final pending = <Op>[];
  final failed = <Op>[];
  final _idmap = <String, String>{};
  String? owner;
  final changes = ValueNotifier<int>(0); // any change to the queue
  final synced = ValueNotifier<int>(0); // bumps when something was really sent: screens reload
  final syncing = ValueNotifier<bool>(false);
  Timer? _timer;
  Future<void> _lock = Future.value();

  Future<T> _locked<T>(Future<T> Function() f) {
    final c = Completer<T>();
    _lock = _lock.then((_) async { try { c.complete(await f()); } catch (e, s) { c.completeError(e, s); } });
    return c.future;
  }

  Future<void> load() async {
    final j = await Store.read('outbox');
    if (j is Map) {
      pending..clear()..addAll((j['pending'] as List? ?? const []).map((e) => Op.fromJson((e as Map).cast<String, dynamic>())));
      failed..clear()..addAll((j['failed'] as List? ?? const []).map((e) => Op.fromJson((e as Map).cast<String, dynamic>())));
      _idmap..clear()..addAll(((j['idmap'] as Map?) ?? const {}).cast<String, String>());
      owner = j['owner'] as String?;
    }
    changes.value++;
    _timer ??= Timer.periodic(const Duration(seconds: 20), (_) => flush());
  }

  Future<void> _save() => Store.write('outbox', {'owner': owner, 'pending': pending.map((o) => o.toJson()).toList(), 'failed': failed.map((o) => o.toJson()).toList(), 'idmap': _idmap});

  /// Called after sign-in: a queue that belongs to another account is dropped, never sent as the new one.
  Future<void> adopt(String userId) async {
    if (owner != null && owner != userId) { pending.clear(); failed.clear(); _idmap.clear(); await Local.instance.clear(); }
    owner = userId;
    await _save();
    changes.value++;
  }

  Future<void> clear() async {
    pending.clear(); failed.clear(); _idmap.clear(); owner = null;
    await Store.delete('outbox');
    changes.value++;
  }

  /// Save the change on the phone first; the send happens when the network allows.
  Future<dynamic> enqueue(Op op) async {
    await _locked(() async { pending.add(op); await _save(); });
    changes.value++;
    unawaited(flush());
    return _synthetic(op);
  }

  dynamic _synthetic(Op op) {
    final t = op.temps;
    if (op.path == '/me/transactions') return {'txn_id': t[0], 'processed': false, 'possible_duplicate_of': null, 'transaction': null, 'queued': true};
    if (op.path == '/me/accounts') return {'account_id': t[0], 'queued': true};
    if (op.path == '/me/goals') return Local.instance.goalFor(op);
    if (op.method == 'DELETE') return null;
    return {'queued': true};
  }

  String _remap(String s) {
    var out = s;
    _idmap.forEach((k, v) { out = out.replaceAll(k, v); });
    return out;
  }

  bool _usesTemp(Op o, Set<String> dead) {
    if (dead.isEmpty) return false;
    final s = '${o.path}${jsonEncode(o.body)}';
    return dead.any(s.contains);
  }

  Future<void> flush() async {
    if (syncing.value || pending.isEmpty) return;
    syncing.value = true;
    var sent = 0;
    final dead = <String>{for (final o in failed) ...o.temps};
    try {
      while (pending.isNotEmpty) {
        final op = pending.first;
        if (_usesTemp(op, dead)) {
          await _fail(op, 'It depended on a change that could not be saved.', dead);
          continue;
        }
        try {
          final body = op.body == null ? null : (jsonDecode(_remap(jsonEncode(op.body))) as Map<String, dynamic>);
          final r = await Api.instance.sendQueued(op.method, _remap(op.path), body, op.id);
          _learn(op, r);
          await _locked(() async { pending.remove(op); await _save(); });
          sent++;
          changes.value++;
        } on ApiException catch (e) {
          if (e.status == 0 || e.status == 401 || e.status >= 500 || e.status == 408 || e.status == 429) {
            op.attempts++;
            await _locked(_save);
            break; // try again later, keep order
          }
          if (op.method == 'DELETE' && e.status == 404) {
            await _locked(() async { pending.remove(op); await _save(); }); // already gone: the goal is met
            sent++;
            continue;
          }
          await _fail(op, e.message, dead);
        }
      }
    } finally {
      syncing.value = false;
    }
    if (sent > 0) {
      synced.value++;
      unawaited(Local.instance.prefetch(force: true));
    }
  }

  Future<void> _fail(Op op, String msg, Set<String> dead) async {
    op.error = msg;
    dead.addAll(op.temps);
    await _locked(() async { pending.remove(op); failed.add(op); await _save(); });
    changes.value++;
  }

  void _learn(Op op, dynamic r) {
    if (op.temps.isEmpty || r is! Map) return;
    final real = <String>[];
    if (r['txn_id'] != null) real.add(r['txn_id'] as String);
    if (r['account_id'] != null) real.add(r['account_id'] as String);
    if (r['goal_id'] != null) real.add(r['goal_id'] as String);
    if (r['txn_ids'] is List) real.addAll((r['txn_ids'] as List).cast<String>());
    if (r['debit_txn_id'] != null) { real..add(r['debit_txn_id'] as String)..add(r['credit_txn_id'] as String); }
    for (var i = 0; i < op.temps.length && i < real.length; i++) { _idmap[op.temps[i]] = real[i]; }
  }

  Future<void> retryFailed(Op op) async {
    await _locked(() async { failed.remove(op); op.error = null; pending.add(op); await _save(); });
    changes.value++;
    unawaited(flush());
  }

  Future<void> discard(Op op) async {
    await _locked(() async { failed.remove(op); await _save(); });
    changes.value++;
    synced.value++;
  }
}

/// A copy of the household's data on the phone plus the rules for showing it with the queued changes applied, so the
/// app behaves the same with or without a network.
class Local {
  static final Local instance = Local._();
  Local._();

  final mirror = <String, Map<String, dynamic>>{}; // transactions as the server last reported them
  Map<String, String> catNames = {};
  DateTime? _lastPrefetch;
  bool _loaded = false;
  Timer? _saveTimer;

  Future<void> load() async {
    final j = await Store.read('mirror');
    if (j is Map) {
      mirror..clear()..addAll((j['txns'] as Map).map((k, v) => MapEntry(k as String, (v as Map).cast<String, dynamic>())));
    }
    _loaded = true;
  }

  Future<void> clear() async { mirror.clear(); await Store.delete('mirror'); _lastPrefetch = null; }

  void remember(Iterable<Map<String, dynamic>> items) {
    for (final t in items) { mirror[t['txn_id'] as String] = t; }
    if (mirror.length > 8000) {
      final sorted = mirror.values.toList()..sort((a, b) => (a['local_date'] as String).compareTo(b['local_date'] as String));
      for (final t in sorted.take(mirror.length - 7000)) { mirror.remove(t['txn_id']); }
    }
    _saveTimer?.cancel();
    _saveTimer = Timer(const Duration(seconds: 2), () { if (_loaded) Store.write('mirror', {'txns': mirror}); });
  }

  // ------------------------------------------------------------ applying queued changes

  List<Op> get _ops => Outbox.instance.pending;
  bool get hasPending => _ops.isNotEmpty;

  /// Transactions as they look once every queued change is applied (or as the server has them when nothing is queued).
  List<Map<String, dynamic>> view() => _apply(mirror.values.map((e) => {...e}).toList(), _ops);

  List<Map<String, dynamic>> baseList() => mirror.values.toList();

  String _idOf(String path) => path.split('/').where((s) => s.isNotEmpty).toList().elementAtOrNull(2) ?? '';

  List<Map<String, dynamic>> _apply(List<Map<String, dynamic>> list, List<Op> ops) {
    int signed(Map<String, dynamic> b) => (b['direction'] == 'DR' ? -1 : 1) * (b['amount_paise'] as int);
    Map<String, dynamic> make(String id, Map<String, dynamic> b, int amount, {String? kind, String? cat, String? desc}) {
      final date = b['date'] as String;
      final cat0 = cat ?? b['category_code'] as String?;
      return {
        'txn_id': id, 'local_date': date, 'posted_at': '${date}T${(b['time'] as String?) ?? '12:00:00'}+05:30', 'account_id': b['account_id'], 'amount_paise': amount,
        'channel': b['channel'] ?? 'UPI', 'descriptor': desc ?? b['description'], 'counterparty_vpa': b['counterparty_vpa'], 'merchant_id': null, 'merchant_name': null,
        'category_code': cat0 ?? 'UNKNOWN', 'kind': kind ?? (cat0 == null ? 'UNKNOWN' : (amount < 0 ? 'EXPENSE' : 'INCOME')), 'confidence': null, 'decision': 'PENDING',
        'overridden': cat0 != null, 'note': '', 'tags': <String>[], 'pending': true,
      };
    }

    int at(String id) => list.indexWhere((t) => t['txn_id'] == id);
    for (final op in ops) {
      final p = op.path, b = op.body ?? const <String, dynamic>{};
      if (op.method == 'POST' && p == '/me/transactions') {
        list.add(make(op.temps[0], b, signed(b)));
      } else if (p.startsWith('/me/transactions/')) {
        final id = _idOf(p), i = at(id);
        if (op.method == 'DELETE') {
          if (i >= 0) list.removeAt(i);
        } else if (i < 0) {
          continue;
        } else if (op.method == 'PATCH') {
          final t = list[i];
          if (b['date'] != null) { t['local_date'] = b['date']; t['posted_at'] = '${b['date']}T12:00:00+05:30'; }
          if (b['description'] != null) t['descriptor'] = b['description'];
          if (b['amount_paise'] != null || b['direction'] != null) {
            final dir = (b['direction'] as String?) ?? ((t['amount_paise'] as int) < 0 ? 'DR' : 'CR');
            final amt = (b['amount_paise'] as int?) ?? (t['amount_paise'] as int).abs();
            t['amount_paise'] = dir == 'DR' ? -amt : amt;
          }
        } else if (p.endsWith('/category')) {
          final t = list[i];
          t['category_code'] = b['category_code']; t['overridden'] = true;
          if (t['kind'] == 'UNKNOWN') t['kind'] = (t['amount_paise'] as int) < 0 ? 'EXPENSE' : 'INCOME';
        } else if (p.endsWith('/note')) {
          list[i]['note'] = b['note'] ?? ''; list[i]['tags'] = b['tags'] ?? <String>[];
        } else if (p.endsWith('/duplicate')) {
          list.add({...list[i], 'txn_id': op.temps[0], 'local_date': b['date'] ?? list[i]['local_date'], 'posted_at': '${b['date'] ?? list[i]['local_date']}T12:00:00+05:30', 'pending': true, 'overridden': false});
        } else if (p.endsWith('/split')) {
          final src = list.removeAt(i);
          final parts = (b['parts'] as List).cast<Map<String, dynamic>>();
          for (var n = 0; n < parts.length && n < op.temps.length; n++) {
            final cat = parts[n]['category_code'] as String?;
            list.add({...src, 'txn_id': op.temps[n], 'amount_paise': (src['amount_paise'] as int) < 0 ? -(parts[n]['amount_paise'] as int) : parts[n]['amount_paise'], 'category_code': cat ?? src['category_code'], 'pending': true, 'overridden': cat != null});
          }
        }
      } else if (op.method == 'POST' && p == '/me/transfers') {
        final amt = b['amount_paise'] as int;
        list.add(make(op.temps[0], {...b, 'account_id': b['from_account_id'], 'description': 'Transfer out'}, -amt, kind: 'TRANSFER', cat: 'TRANSFER'));
        list.add(make(op.temps[1], {...b, 'account_id': b['to_account_id'], 'description': 'Transfer in'}, amt, kind: 'TRANSFER', cat: 'TRANSFER'));
      }
    }
    return list;
  }

  // ------------------------------------------------------------ answering reads locally

  bool _match(Map<String, dynamic> t, Map<String, String?> q) {
    String? v(String k) => (q[k] ?? '').isEmpty ? null : q[k];
    final date = t['local_date'] as String, amt = (t['amount_paise'] as int).abs();
    if (v('month') != null && v('month') != 'all' && !date.startsWith(v('month')!)) return false;
    if (v('category') != null && t['category_code'] != v('category')) return false;
    if (v('account_id') != null && t['account_id'] != v('account_id')) return false;
    if (v('kind') != null && t['kind'] != v('kind')) return false;
    if (v('date_from') != null && date.compareTo(v('date_from')!) < 0) return false;
    if (v('date_to') != null && date.compareTo(v('date_to')!) > 0) return false;
    if (v('min_paise') != null && amt < int.parse(v('min_paise')!)) return false;
    if (v('max_paise') != null && amt > int.parse(v('max_paise')!)) return false;
    if (v('merchant') != null && (t['merchant_name'] ?? t['descriptor']) != v('merchant')) return false;
    if (v('tag') != null && !((t['tags'] as List?) ?? const []).contains(v('tag'))) return false;
    if (v('q') != null) {
      final s = v('q')!.toLowerCase();
      final hay = '${t['descriptor']} ${t['merchant_name'] ?? ''} ${t['note'] ?? ''}'.toLowerCase();
      final n = double.tryParse(s.replaceAll(',', ''));
      if (!hay.contains(s) && !(n != null && (n * 100).round() == amt) && !date.startsWith(s)) return false;
    }
    return true;
  }

  Map<String, dynamic>? listFor(Map<String, String?> q) {
    final rows = view().where((t) => _match(t, q)).toList()
      ..sort((a, b) {
        final d = (b['local_date'] as String).compareTo(a['local_date'] as String);
        return d != 0 ? d : (b['txn_id'] as String).compareTo(a['txn_id'] as String);
      });
    final limit = int.tryParse(q['limit'] ?? '') ?? 50;
    final off = (q['cursor'] ?? '').startsWith('o') ? int.parse(q['cursor']!.substring(1)) : 0;
    final page = rows.skip(off).take(limit).toList();
    return {'items': page, 'next_cursor': off + limit < rows.length ? 'o${off + limit}' : null};
  }

  Map<String, dynamic>? detailFor(String id) {
    final v = view().where((t) => t['txn_id'] == id);
    return v.isEmpty ? null : v.first;
  }

  /// Account list with queued edits and the balance effect of queued entries.
  List<dynamic> accountsView(List<dynamic> base) {
    if (!hasPending) return base;
    final list = base.map((e) => {...(e as Map<String, dynamic>)}).toList();
    final delta = <String, int>{};
    for (final t in view()) { delta[t['account_id'] as String] = (delta[t['account_id']] ?? 0) + (t['amount_paise'] as int); }
    for (final t in baseList()) { delta[t['account_id'] as String] = (delta[t['account_id']] ?? 0) - (t['amount_paise'] as int); }
    for (final op in _ops) {
      final b = op.body ?? const <String, dynamic>{};
      if (op.method == 'POST' && op.path == '/me/accounts') {
        final type = b['account_type'] as String;
        final bank = b['bank_code'] as String? ?? 'OTHR';
        list.add({'account_id': op.temps[0], 'account_type': type, 'bank_code': bank, 'masked_number': b['last4'] == null ? '0000' : '••${b['last4']}', 'vpa': b['vpa'], 'label': b['label'], 'status': 'ACTIVE', 'opened_on': b['opened_on'] ?? todayIso(), 'display_name': b['label'] ?? (type == 'UPI' ? '$bank UPI' : '$bank ${titleCase(type).toLowerCase()}'), 'balance_paise': b['opening_balance_paise'] ?? 0, 'credit_limit_paise': b['credit_limit_paise'], 'holder_role': 'OWNER', 'shared_from_other_household': false, 'pending': true});
      } else if (op.path.startsWith('/me/accounts/')) {
        final id = _idOf(op.path), i = list.indexWhere((a) => a['account_id'] == id);
        if (i < 0) continue;
        if (op.path.endsWith('/close')) { list[i]['status'] = 'CLOSED'; } else if (op.method == 'PATCH') {
          if (b['label'] != null) { list[i]['label'] = (b['label'] as String).isEmpty ? null : b['label']; if ((b['label'] as String).isNotEmpty) list[i]['display_name'] = b['label']; }
          if (b['credit_limit_paise'] != null) list[i]['credit_limit_paise'] = b['credit_limit_paise'];
          if (b['vpa'] != null) list[i]['vpa'] = b['vpa'];
          if (b['balance_paise'] != null) { list[i]['balance_paise'] = b['balance_paise']; delta.remove(id); }
        }
      }
    }
    for (final a in list) {
      final d = delta[a['account_id']];
      if (d != null && d != 0) a['balance_paise'] = (a['balance_paise'] as int) + d;
    }
    return list;
  }

  // ----- aggregates: server numbers plus the difference queued changes make

  ({int spend, int income}) _contrib(Map<String, dynamic> t) {
    final a = t['amount_paise'] as int, k = t['kind'] as String;
    if (k == 'EXPENSE' && a < 0) return (spend: -a, income: 0);
    if (k == 'UNKNOWN') return a < 0 ? (spend: -a, income: 0) : (spend: 0, income: a);
    if (k == 'INCOME') return (spend: 0, income: a);
    if (k == 'REFUND') return (spend: -a, income: 0);
    return (spend: 0, income: 0);
  }

  /// Per-key difference (view minus server copy) for transactions that fall in [month].
  Map<String, ({int spend, int income, int count})> _delta(String month, String Function(Map<String, dynamic>) key) {
    final out = <String, ({int spend, int income, int count})>{};
    void add(Map<String, dynamic> t, int sign) {
      if (!(t['local_date'] as String).startsWith(month)) return;
      final c = _contrib(t), k = key(t), o = out[k] ?? (spend: 0, income: 0, count: 0);
      out[k] = (spend: o.spend + sign * c.spend, income: o.income + sign * c.income, count: o.count + sign);
    }
    for (final t in view()) { add(t, 1); }
    for (final t in baseList()) { add(t, -1); }
    return out;
  }

  Map<String, dynamic> dailyView(Map<String, dynamic> base, String month) {
    if (!hasPending) return base;
    final d = _delta(month, (t) => t['local_date'] as String);
    final days = (base['days'] as List).map((e) => {...(e as Map<String, dynamic>)}).toList();
    var total = 0;
    for (final day in days) {
      final x = d[day['date']];
      if (x != null) { day['spend_paise'] = max(0, (day['spend_paise'] as int) + x.spend); day['income_paise'] = max(0, (day['income_paise'] as int) + x.income); day['count'] = max(0, (day['count'] as int) + x.count); }
      total += day['spend_paise'] as int;
    }
    final elapsed = max(1, (base['days_elapsed'] as int?) ?? 1);
    String? busiest; var best = 0;
    for (final day in days) { if ((day['spend_paise'] as int) > best) { best = day['spend_paise'] as int; busiest = day['date'] as String; } }
    return {...base, 'days': days, 'total_spend_paise': total, 'daily_average_paise': (total / elapsed).round(), 'busiest': busiest};
  }

  Map<String, dynamic> summaryView(Map<String, dynamic> base, String month) {
    if (!hasPending) return base;
    final d = _delta(month, (_) => 'all')['all'];
    if (d == null) return base;
    final spend = max(0, (base['spend_paise'] as int) + d.spend), income = max(0, (base['income_paise'] as int) + d.income);
    return {...base, 'spend_paise': spend, 'naive_spend_paise': max(0, (base['naive_spend_paise'] as int) + d.spend), 'income_paise': income, 'savings_rate': income > 0 ? double.parse(((income - spend) / income).toStringAsFixed(4)) : null};
  }

  Map<String, dynamic> categoriesView(Map<String, dynamic> base, String month) {
    if (!hasPending) return base;
    final d = _delta(month, (t) => t['category_code'] as String);
    final cats = (base['categories'] as List).map((e) => {...(e as Map<String, dynamic>)}).toList();
    for (final e in d.entries) {
      if (e.value.spend == 0) continue;
      final i = cats.indexWhere((c) => c['code'] == e.key);
      if (i >= 0) { cats[i]['spend_paise'] = max(0, (cats[i]['spend_paise'] as int) + e.value.spend); } else {
        cats.add({'code': e.key, 'name': catNames[e.key] ?? titleCase(e.key), 'spend_paise': max(0, e.value.spend), 'previous_paise': 0, 'change_paise': 0, 'share': 0});
      }
    }
    final total = cats.fold<int>(0, (s, c) => s + (c['spend_paise'] as int));
    for (final c in cats) {
      c['change_paise'] = (c['spend_paise'] as int) - (c['previous_paise'] as int);
      c['share'] = total == 0 ? 0 : (c['spend_paise'] as int) / total;
    }
    cats.sort((a, b) => (b['spend_paise'] as int).compareTo(a['spend_paise'] as int));
    return {...base, 'categories': cats, 'total_paise': total, 'change_paise': total - (base['previous_total_paise'] as int)};
  }

  Map<String, dynamic> budgetsView(Map<String, dynamic> base, String month) {
    if (!hasPending) return base;
    final d = _delta(month, (t) => t['category_code'] as String);
    final lines = (base['lines'] as List).map((e) => {...(e as Map<String, dynamic>)}).toList();
    final carry = ((base['carry_enabled'] as List?) ?? const []).cast<String>().toList();
    Map<String, dynamic> line(String code) {
      var i = lines.indexWhere((l) => l['category_code'] == code);
      if (i < 0) { lines.add({'category_code': code, 'category_name': catNames[code] ?? titleCase(code), 'budget_paise': null, 'actual_paise': 0, 'ratio': null, 'status': 'NO_BUDGET', 'budget_ids': <String>[]}); i = lines.length - 1; }
      return lines[i];
    }
    for (final e in d.entries) { if (e.value.spend != 0) { final l = line(e.key); l['actual_paise'] = max(0, (l['actual_paise'] as int) + e.value.spend); } }
    for (final op in _ops) {
      final b = op.body ?? const <String, dynamic>{};
      if (op.method == 'PUT' && op.path == '/me/budgets' && b['month'] == month) { line(b['category_code'] as String)['budget_paise'] = b['amount_paise']; }
      if (op.method == 'DELETE' && op.path.startsWith('/me/budgets/$month/')) { line(op.path.split('/').last)['budget_paise'] = null; }
      if (op.method == 'PUT' && op.path == '/me/budgets/carry') { final c = b['category_code'] as String; carry.remove(c); if (b['enabled'] == true) carry.add(c); }
    }
    var tb = 0, ta = 0;
    for (final l in lines) {
      final bud = l['budget_paise'] as int?, act = l['actual_paise'] as int;
      l['ratio'] = bud == null ? null : (bud == 0 ? (act > 0 ? 2.0 : 0.0) : act / bud);
      l['status'] = bud == null ? 'NO_BUDGET' : (bud == 0 ? (act > 0 ? 'OVER' : 'UNDER') : (act / bud > 1 ? 'OVER' : act / bud >= .8 ? 'NEAR' : 'UNDER'));
      tb += bud ?? 0; ta += act;
    }
    lines.sort((a, b) => ((b['ratio'] as num?) ?? -1).compareTo((a['ratio'] as num?) ?? -1));
    return {...base, 'lines': lines, 'carry_enabled': carry, 'total_budget_paise': tb, 'total_actual_paise': ta};
  }

  // ----- goals

  Map<String, dynamic> _goalOut(String id, String name, int target, int saved, String? deadline) {
    final left = max(target - saved, 0);
    int? days;
    if (deadline != null) days = DateTime.parse(deadline).difference(DateTime.parse(todayIso())).inDays;
    final months = days != null && days > 0 ? max((days / 30).ceil(), 1) : null;
    return {'goal_id': id, 'name': name, 'target_paise': target, 'saved_paise': saved, 'remaining_paise': left, 'progress': min(saved / target, 1.0), 'deadline': deadline, 'days_left': days, 'monthly_needed_paise': months != null && left > 0 ? (left / months).ceil() : null, 'completed': saved >= target, 'completed_at': null, 'pending': true};
  }

  Map<String, dynamic> goalFor(Op op) {
    final b = op.body!;
    return _goalOut(op.temps[0], b['name'] as String, b['target_paise'] as int, (b['saved_paise'] as int?) ?? 0, b['deadline'] as String?);
  }

  List<dynamic> goalsView(List<dynamic> base) {
    if (!_ops.any((o) => o.path.startsWith('/me/goals'))) return base;
    final list = base.map((e) => {...(e as Map<String, dynamic>)}).toList();
    for (final op in _ops) {
      final b = op.body ?? const <String, dynamic>{};
      if (op.method == 'POST' && op.path == '/me/goals') { list.add(goalFor(op)); continue; }
      if (!op.path.startsWith('/me/goals/')) continue;
      final id = _idOf(op.path), i = list.indexWhere((g) => g['goal_id'] == id);
      if (i < 0) continue;
      if (op.method == 'DELETE') { list.removeAt(i); continue; }
      final g = list[i];
      var name = g['name'] as String, target = g['target_paise'] as int, saved = g['saved_paise'] as int;
      var deadline = g['deadline'] as String?;
      if (op.path.endsWith('/contribute')) { saved = max(0, saved + (b['amount_paise'] as int)); } else {
        if (b['name'] != null) name = b['name'] as String;
        if (b['target_paise'] != null) target = b['target_paise'] as int;
        if (b.containsKey('deadline')) deadline = b['deadline'] as String?;
      }
      list[i] = _goalOut(id, name, target, saved, deadline);
    }
    return list;
  }

  dynamic notificationsView(dynamic base) {
    final ops = _ops.where((o) => o.method == 'PUT' && o.path == '/me/notifications');
    if (ops.isEmpty || base is! Map) return base;
    return {...base, ...ops.last.body!};
  }

  // ------------------------------------------------------------ keeping the copy fresh

  /// Quietly pull what the app needs to work with no signal: six months of entries and every screen's data.
  Future<void> prefetch({bool force = false}) async {
    final now = DateTime.now();
    if (!force && _lastPrefetch != null && now.difference(_lastPrefetch!).inMinutes < 10) return;
    if (Outbox.instance.pending.isNotEmpty || Api.instance.offline.value) return;
    _lastPrefetch = now;
    final api = Api.instance;
    Future<void> tryGet(String p, [Map<String, String?> q = const {}]) async { try { await api.get(p, q); } catch (_) {/* best effort */} }
    try {
      final cats = await api.get('/categories');
      catNames = {for (final c in (cats as List).cast<Map<String, dynamic>>()) c['code'] as String: c['name'] as String};
    } catch (_) {/* keep old */}
    final month = currentMonth();
    for (final p in ['/me/profile', '/me/accounts', '/me/goals', '/me/alerts', '/me/networth', '/me/recurring', '/me/notifications', '/me/merchants', '/me/weekday', '/me/trend', '/me/upcoming']) {
      final q = p == '/me/merchants' ? {'months': '6', 'limit': '10'} : p == '/me/weekday' ? {'months': '6'} : p == '/me/trend' ? {'months': '12'} : p == '/me/upcoming' ? {'days': '30'} : const <String, String?>{};
      await tryGet(p, q);
    }
    for (var back = 0; back < 6; back++) {
      final m = shiftMonth(month, -back);
      if (back < 2) {
        for (final p in ['/me/summary', '/me/budgets', '/me/daily', '/me/spend-by-category', '/me/insights']) { await tryGet(p, {'month': m}); }
      }
      String? cursor;
      for (var page = 0; page < 12; page++) {
        try {
          final r = await api.get('/me/transactions', {'month': m, 'limit': '100', 'cursor': cursor}) as Map<String, dynamic>;
          cursor = r['next_cursor'] as String?;
          if (cursor == null) break;
        } catch (_) { break; }
      }
    }
  }
}
