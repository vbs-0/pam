import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/material.dart';

import '../api.dart';
import '../theme.dart';

class LoginScreen extends StatefulWidget {
  final bool expired;
  final ValueChanged<Me> onSignedIn;
  const LoginScreen({super.key, required this.onSignedIn, this.expired = false});
  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _email = TextEditingController(), _password = TextEditingController(), _name = TextEditingController();
  bool _signUp = false, _busy = false, _show = false;
  String? _error;

  @override
  void dispose() { _email.dispose(); _password.dispose(); _name.dispose(); super.dispose(); }

  Future<void> _google() async {
    setState(() { _busy = true; _error = null; });
    try {
      final cred = await FirebaseAuth.instance.signInWithProvider(GoogleAuthProvider());
      final token = await cred.user?.getIdToken();
      if (token == null) throw ApiException(0, 'Google did not return a sign-in token.');
      widget.onSignedIn(await Api.instance.google(token));
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    } on FirebaseAuthException catch (e) {
      if (e.code != 'web-context-canceled' && e.code != 'canceled') setState(() => _error = 'Google sign-in did not complete (${e.code}).');
    } catch (_) {
      setState(() => _error = 'Google sign-in is not available in this build.');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _submit() async {
    setState(() { _busy = true; _error = null; });
    try {
      final email = _email.text.trim();
      final me = _signUp ? await Api.instance.register(email, _password.text, _name.text.trim()) : await Api.instance.login(email, _password.text);
      widget.onSignedIn(me);
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final k = Palette.of(context);
    return Scaffold(
      body: SafeArea(
        child: Stack(children: [
          Positioned(left: 30, top: 0, bottom: 0, child: Container(width: 1, color: k.red.withValues(alpha: .55))),
          Center(
            child: SingleChildScrollView(
              padding: const EdgeInsets.fromLTRB(46, 24, 24, 24),
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 420),
                child: AutofillGroup(
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Text('PAM', style: TextStyle(color: k.blue, fontWeight: FontWeight.w800, fontSize: 15, letterSpacing: 2)),
                    const SizedBox(height: 14),
                    Text(_signUp ? 'Start your register' : 'Open your register', style: const TextStyle(fontSize: 30, fontWeight: FontWeight.w700, letterSpacing: -.5, height: 1.1)),
                    const SizedBox(height: 8),
                    Text(_signUp ? 'You get a household of your own, empty and ready for your entries.' : 'Where did the month go? Sign in to see.', style: TextStyle(color: k.muted)),
                    if (widget.expired) Padding(padding: const EdgeInsets.only(top: 12), child: Text('Your session ended. Please sign in again.', style: TextStyle(color: k.amber))),
                    const SizedBox(height: 22),
                    if (_signUp) ...[
                      TextField(controller: _name, textCapitalization: TextCapitalization.words, autofillHints: const [AutofillHints.name], decoration: const InputDecoration(labelText: 'Your name (optional)')),
                      const SizedBox(height: 14),
                    ],
                    TextField(controller: _email, keyboardType: TextInputType.emailAddress, autofillHints: const [AutofillHints.username, AutofillHints.email], decoration: const InputDecoration(labelText: 'Email')),
                    const SizedBox(height: 14),
                    TextField(
                      controller: _password, obscureText: !_show, autofillHints: [_signUp ? AutofillHints.newPassword : AutofillHints.password],
                      onSubmitted: (_) => _submit(),
                      decoration: InputDecoration(labelText: 'Password', helperText: _signUp ? 'At least 10 characters' : null,
                          suffixIcon: IconButton(tooltip: _show ? 'Hide password' : 'Show password', icon: Icon(_show ? Icons.visibility_off : Icons.visibility), onPressed: () => setState(() => _show = !_show))),
                    ),
                    if (_error != null) Padding(
                      padding: const EdgeInsets.only(top: 14),
                      child: Container(width: double.infinity, padding: const EdgeInsets.all(12), decoration: BoxDecoration(color: k.redSoft, border: Border.all(color: k.red)),
                          child: Text(_error!, style: TextStyle(color: k.red, fontWeight: FontWeight.w600))),
                    ),
                    const SizedBox(height: 20),
                    SizedBox(width: double.infinity, child: FilledButton(onPressed: _busy ? null : _submit, child: Text(_busy ? 'One moment…' : _signUp ? 'Create account' : 'Sign in'))),
                    const SizedBox(height: 10),
                    SizedBox(width: double.infinity, child: OutlinedButton.icon(onPressed: _busy ? null : _google, icon: const Icon(Icons.g_mobiledata, size: 28), label: const Text('Continue with Google'))),
                    const SizedBox(height: 6),
                    Center(child: TextButton(onPressed: () => setState(() { _signUp = !_signUp; _error = null; }), child: Text(_signUp ? 'Already have an account? Sign in' : 'New here? Create an account'))),
                    if (!_signUp) Center(child: Text('Forgot your password? Reset it at pam.is-cool.dev/forgot', style: TextStyle(color: k.muted, fontSize: 13), textAlign: TextAlign.center)),
                    const Divider(height: 32),
                    Text('Looking around? Sample households sign in as usr-000001@pam.is-cool.dev with password password123. They are read-only synthetic data.', style: TextStyle(color: k.muted, fontSize: 13)),
                  ]),
                ),
              ),
            ),
          ),
        ]),
      ),
    );
  }
}
