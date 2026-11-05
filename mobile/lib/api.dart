import 'dart:convert';

import 'package:flutter/foundation.dart';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:google_sign_in/google_sign_in.dart';
import 'package:http/http.dart' as http;

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
    return Me.fromJson(r['user'] as Map<String, dynamic>);
  }

  Future<Me> me() async => Me.fromJson(await _send('GET', '/auth/me') as Map<String, dynamic>);

  Future<void> signOut() async {
    _token = null;
    try { await FirebaseAuth.instance.signOut(); await GoogleSignIn.instance.signOut(); } catch (_) {}
    try { await _store.delete(key: 'token'); } catch (_) {}
  }

  Future<dynamic> get(String path, [Map<String, String?> q = const {}]) => _send('GET', path, query: q);
  Future<dynamic> post(String path, Map<String, dynamic> body) => _send('POST', path, body: body);
  Future<dynamic> put(String path, Map<String, dynamic> body) => _send('PUT', path, body: body);
  Future<dynamic> delete(String path) => _send('DELETE', path);

  /// Number of requests in flight; the home screen shows a thin progress line while it is above zero.
  final inFlight = ValueNotifier<int>(0);

  Future<dynamic> _send(String method, String path, {Map<String, String?> query = const {}, Map<String, dynamic>? body, bool auth = true}) async {
    inFlight.value++;
    try {
      return await _sendRaw(method, path, query: query, body: body, auth: auth);
    } finally {
      inFlight.value--;
    }
  }

  Future<dynamic> _sendRaw(String method, String path, {Map<String, String?> query = const {}, Map<String, dynamic>? body, bool auth = true}) async {
    final qp = {for (final e in query.entries) if (e.value != null && e.value!.isNotEmpty) e.key: e.value!};
    final uri = Uri.parse('$apiBase$path').replace(queryParameters: qp.isEmpty ? null : qp);
    final headers = {'Accept': 'application/json', 'X-PAM-Client': 'mobile', if (body != null) 'Content-Type': 'application/json', if (auth && _token != null) 'Authorization': 'Bearer $_token'};
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
      if (res.statusCode == 401 && auth && _token != null) { await signOut(); onSignedOut?.call(); }
      var msg = data is Map && data['detail'] is String ? data['detail'] as String : (res.statusCode >= 500 ? 'Something went wrong on the server. Try again.' : 'Request failed');
      if (data is Map && data['errors'] is List && (data['errors'] as List).isNotEmpty) {
        msg = (data['errors'] as List).map((e) => '${e['field']}: ${e['message']}').join('\n');
      }
      throw ApiException(res.statusCode, msg, data is Map ? data['request_id'] as String? : null);
    }
    return data;
  }
}
