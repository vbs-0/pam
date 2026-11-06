import 'dart:convert';

import 'package:flutter/foundation.dart';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:google_sign_in/google_sign_in.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

import 'format.dart' show currentMonth;
import 'offline.dart';
import 'widgets_sync.dart';

/// Server address. Override at build time: flutter build apk --dart-define=API_BASE=https://host/api/v1
const apiBase = String.fromEnvironment('API_BASE', defaultValue: 'https://pam.is-cool.dev/api/v1');

class ApiException implements Exception {
  final int status;
  final String message;
  final String? requestId;
  ApiException(this.status, this.message, [this.requestId]);
  @override
  String toString() => message;
}

class Me {
  final String id, email, role;
  final String? profile;
  Me(this.id, this.email, this.role, this.profile);
  factory Me.fromJson(Map<String, dynamic> j) => Me(j['app_user_id'], j['email'], j['role'], j['profile_user_id']);
}

/// One small client: bearer token in the Keystore-backed secure storage; 401 on a stored token signs the user out.
class Api {
  static final Api instance = Api._();
  Api._();
  final _store = const FlutterSecureStorage();
  final _client = http.Client();
  String? _token;
  void Function()? onSignedOut;

  Future<bool> restore() async {
    try { _token = await _store.read(key: 'token'); } catch (_) { _token = null; }
    return _token != null;
  }

  Future<Me> login(String email, String password) async => _auth('/auth/login', {'email': email, 'password': password});
  Future<Me> register(String email, String password, String name) async =>
      _auth('/auth/register', {'email': email, 'password': password, 'name': name});

  Future<Me> google(String idToken) async => _auth('/auth/firebase', {'id_token': idToken});

  Future<Me> _auth(String path, Map<String, dynamic> body) async {
    final r = await _send('POST', path, body: body, auth: false);
    _token = r['access_token'] as String;
    try { await _store.write(key: 'token', value: _token); } catch (_) {/* keep in memory */}
    final me = Me.fromJson(r['user'] as Map<String, dynamic>);
    await Outbox.instance.adopt(me.id);
    return me;
  }

  Future<Me> me() async => Me.fromJson(await get('/auth/me') as Map<String, dynamic>);

  /// [keepQueue] is for a session that expired by itself: changes made offline stay on the phone for the next sign-in
  /// of the same account. A deliberate sign-out discards them, so nothing of one account ever reaches another.
  Future<void> signOut({bool keepQueue = false}) async {
    _token = null;
    if (!keepQueue) { await Outbox.instance.clear(); await Local.instance.clear(); }
    await clearCache();
    await clearWidgets();
    try { await FirebaseAuth.instance.signOut(); await GoogleSignIn.instance.signOut(); } catch (_) {}
    try { await _store.delete(key: 'token'); } catch (_) {}
  }

  /// True while the last read was answered from the on-device copy because the server could not be reached.
  final offline = ValueNotifier<bool>(false);
  static const _cachePrefix = 'c1:';
  static const _cacheMax = 80;

  String _ckey(String path, Map<String, String?> q) {
    final parts = (q.entries.where((e) => e.value != null && e.value!.isNotEmpty).toList()..sort((a, b) => a.key.compareTo(b.key))).map((e) => '${e.key}=${e.value}');
    return '$_cachePrefix$path?${parts.join('&')}';
  }

  /// Reads go to the server; the answer is kept on the device. With no signal (or changes still waiting to be sent)
  /// the app answers from its copy, with the waiting changes applied, so every screen keeps working.
  Future<dynamic> get(String path, [Map<String, String?> q = const {}]) async {
    final local = Local.instance;
    final isList = path == '/me/transactions';
    final isDetail = path.startsWith('/me/transactions/');
    if (local.hasPending) {
      if (isList) return local.listFor(q);
      if (isDetail) { final d = local.detailFor(path.split('/').last); if (d != null) return d; }
    }
    final key = _ckey(path, q);
    dynamic data;
    // Stale-while-revalidate: if the server is slow but this screen was seen before, show the saved copy now and let the
    // request finish in the background, so the next visit is fresh. Lists and details keep going to the server.
    final saved = (isList || isDetail) ? null : await _recall(key);
    try {
      final req = _send('GET', path, query: q);
      if (saved != null) {
        data = await req.timeout(const Duration(milliseconds: 1500), onTimeout: () {
          req.then((d) { if (offline.value) offline.value = false; _remember(key, d); }).catchError((_) {});
          throw _UseSaved();
        });
      } else {
        data = await req;
      }
      if (offline.value) offline.value = false;
      _remember(key, data);
      if (isList) local.remember(((data as Map)['items'] as List).cast<Map<String, dynamic>>());
      if (isDetail && data is Map) local.remember([data.cast<String, dynamic>()]);
    } on _UseSaved {
      data = saved!.value;
    } on ApiException catch (e) {
      if (e.status != 0) rethrow;
      if (isList && local.mirror.isNotEmpty) { offline.value = true; return local.listFor(q); }
      if (isDetail) { final d = local.detailFor(path.split('/').last); if (d != null) { offline.value = true; return d; } }
      final hit = await _recall(key);
      if (hit == null) rethrow;
      offline.value = true;
      data = hit.value;
    }
    return _overlay(path, q, data);
  }

  dynamic _overlay(String path, Map<String, String?> q, dynamic data) {
    final l = Local.instance;
    final month = q['month'] ?? currentMonth();
    switch (path) {
      case '/me/accounts': return l.accountsView(data as List);
      case '/me/daily': return l.dailyView((data as Map).cast<String, dynamic>(), month);
      case '/me/summary': return l.summaryView((data as Map).cast<String, dynamic>(), month);
      case '/me/spend-by-category': return l.categoriesView((data as Map).cast<String, dynamic>(), month);
      case '/me/budgets': return l.budgetsView((data as Map).cast<String, dynamic>(), month);
      case '/me/goals': return l.goalsView(data as List);
      case '/me/notifications': return l.notificationsView(data);
    }
    return data;
  }

  Future<void> _remember(String key, dynamic data) async {
    try {
      final sp = await SharedPreferences.getInstance();
      await sp.setString(key, jsonEncode(data));
      final order = sp.getStringList('${_cachePrefix}order') ?? <String>[];
      order.remove(key);
      order.add(key);
      while (order.length > _cacheMax) { await sp.remove(order.removeAt(0)); }
      await sp.setStringList('${_cachePrefix}order', order);
    } catch (_) {/* caching is best effort */}
  }

  Future<MapEntry<String, dynamic>?> _recall(String key) async {
    try {
      final sp = await SharedPreferences.getInstance();
      final raw = sp.getString(key);
      return raw == null ? null : MapEntry(key, jsonDecode(raw));
    } catch (_) { return null; }
  }

  Future<void> clearCache() async {
    try {
      final sp = await SharedPreferences.getInstance();
      for (final k in sp.getKeys().where((k) => k.startsWith(_cachePrefix)).toList()) { await sp.remove(k); }
    } catch (_) {/* ignore */}
    offline.value = false;
  }

  /// Raw text download (CSV, JSON backup).
  Future<String> getText(String path, [Map<String, String?> q = const {}]) async {
    final qp = {for (final e in q.entries) if (e.value != null && e.value!.isNotEmpty) e.key: e.value!};
    final uri = Uri.parse('$apiBase$path').replace(queryParameters: qp.isEmpty ? null : qp);
    try {
      final res = await _client.get(uri, headers: {'X-PAM-Client': 'mobile', if (_token != null) 'Authorization': 'Bearer $_token'}).timeout(const Duration(seconds: 60));
      if (res.statusCode >= 400) throw ApiException(res.statusCode, 'Could not download that file.');
      return utf8.decode(res.bodyBytes);
    } on ApiException {
      rethrow;
    } catch (_) {
      throw ApiException(0, "Can't reach the server. Check your connection and try again.");
    }
  }

  Future<dynamic> patch(String path, Map<String, dynamic> body) => _write('PATCH', path, body);

  /// Swap the stored sign-in for a fresh one (after a password or email change).
  Future<void> adoptToken(String token) async {
    _token = token;
    try { await _store.write(key: 'token', value: token); } catch (_) {/* keep in memory */}
  }
  Future<dynamic> post(String path, Map<String, dynamic> body) => _write('POST', path, body);
  Future<dynamic> put(String path, Map<String, dynamic> body) => _write('PUT', path, body);
  Future<dynamic> delete(String path) => _write('DELETE', path, null);

  /// Number of temporary ids a queued change invents for the things it creates.
  int _tempCount(String method, String path, Map<String, dynamic>? body) {
    if (method == 'POST' && (path == '/me/transactions' || path == '/me/accounts' || path == '/me/goals')) return 1;
    if (method == 'POST' && path.endsWith('/duplicate')) return 1;
    if (method == 'POST' && path.endsWith('/split')) return (body?['parts'] as List?)?.length ?? 2;
    if (method == 'POST' && path == '/me/transfers') return 2;
    return 0;
  }

  /// Writes go straight to the server when it can be reached and nothing is waiting; otherwise (or when the connection
  /// drops) they are saved in the outbox on the phone and sent later. The same key is used both ways, so a send that
  /// was cut off after the server acted is recognised and not applied twice.
  Future<dynamic> _write(String method, String path, Map<String, dynamic>? body) async {
    if (onlineOnly(path)) return _send(method, path, body: body);
    final op = Op.create(method, path, body, temps: _tempCount(method, path, body));
    if (Outbox.instance.pending.isEmpty) {
      try {
        return await _send(method, path, body: body, idem: op.id);
      } on ApiException catch (e) {
        if (e.status != 0) rethrow;
      }
    }
    return Outbox.instance.enqueue(op);
  }

  Future<dynamic> sendQueued(String method, String path, Map<String, dynamic>? body, String key) => _send(method, path, body: body, idem: key);

  /// Number of requests in flight; the home screen shows a thin progress line while it is above zero.
  final inFlight = ValueNotifier<int>(0);

  Future<dynamic> _send(String method, String path, {Map<String, String?> query = const {}, Map<String, dynamic>? body, bool auth = true, String? idem}) async {
    inFlight.value++;
    try {
      return await _sendRaw(method, path, query: query, body: body, auth: auth, idem: idem);
    } finally {
      inFlight.value--;
    }
  }

  Future<dynamic> _sendRaw(String method, String path, {Map<String, String?> query = const {}, Map<String, dynamic>? body, bool auth = true, String? idem}) async {
    final qp = {for (final e in query.entries) if (e.value != null && e.value!.isNotEmpty) e.key: e.value!};
    final uri = Uri.parse('$apiBase$path').replace(queryParameters: qp.isEmpty ? null : qp);
    final headers = {'Accept': 'application/json', 'X-PAM-Client': 'mobile', if (idem != null) 'Idempotency-Key': idem, if (body != null) 'Content-Type': 'application/json', if (auth && _token != null) 'Authorization': 'Bearer $_token'};
    http.Response res;
    try {
      final req = http.Request(method, uri)..headers.addAll(headers);
      if (body != null) req.body = jsonEncode(body);
      res = await http.Response.fromStream(await _client.send(req).timeout(const Duration(seconds: 25)));
    } catch (_) {
      throw ApiException(0, "Can't reach the server. Check your connection and try again.");
    }
    if (res.statusCode == 204) return null;
    dynamic data;
    try { data = res.body.isEmpty ? null : jsonDecode(utf8.decode(res.bodyBytes)); } catch (_) {}
    if (res.statusCode >= 400) {
      if (res.statusCode == 401 && auth && _token != null) { await signOut(keepQueue: true); onSignedOut?.call(); }
      var msg = data is Map && data['detail'] is String ? data['detail'] as String : (res.statusCode >= 500 ? 'Something went wrong on the server. Try again.' : 'Request failed');
      if (data is Map && data['errors'] is List && (data['errors'] as List).isNotEmpty) {
        msg = (data['errors'] as List).map((e) => '${e['field']}: ${e['message']}').join('\n');
      }
      throw ApiException(res.statusCode, msg, data is Map ? data['request_id'] as String? : null);
    }
    return data;
  }
}

class _UseSaved implements Exception {}
