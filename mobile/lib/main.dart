import 'package:firebase_core/firebase_core.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'api.dart';
import 'screens/books.dart';
import 'screens/entries.dart';
import 'screens/folio.dart';
import 'screens/login.dart';
import 'screens/recurring.dart';
import 'prefs.dart';
import 'screens/onboarding.dart';
import 'screens/settings.dart';
import 'theme.dart';
import 'ui/widgets.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  try { await Firebase.initializeApp(); } catch (_) {/* no config in this build: email sign-in only */}
  await Prefs.load();
  runApp(const PamApp());
}

class PamApp extends StatefulWidget {
  const PamApp({super.key});
  @override
  State<PamApp> createState() => _PamAppState();
}

class _PamAppState extends State<PamApp> {
  Me? _me;
  bool _loading = true;
  bool _expired = false;

  @override
  void initState() {
    super.initState();
    Api.instance.onSignedOut = () => setState(() { _me = null; _expired = true; });
    _boot();
  }

  Future<void> _boot() async {
    if (await Api.instance.restore()) {
      try { _me = await Api.instance.me(); } catch (_) { await Api.instance.signOut(); }
    }
    if (mounted) setState(() => _loading = false);
  }

  @override
  Widget build(BuildContext context) => ValueListenableBuilder<ThemeMode>(
      valueListenable: Prefs.themeMode,
      builder: (_, mode, __) => MaterialApp(
        title: 'PAM',
        debugShowCheckedModeBanner: false,
        theme: buildTheme(Brightness.light),
        darkTheme: buildTheme(Brightness.dark),
        themeMode: mode,
        home: _loading
            ? const BootSplash()
            : _me == null
                ? LoginScreen(expired: _expired, onSignedIn: (m) => setState(() { _me = m; _expired = false; }))
                : _me!.role != 'CUSTOMER'
                    ? StaffNotice(me: _me!, onSignOut: () async { await Api.instance.signOut(); setState(() => _me = null); })
                    : Home(me: _me!, onSignOut: () async { await Api.instance.signOut(); setState(() => _me = null); }),
      ));
}

class StaffNotice extends StatelessWidget {
  final Me me;
  final VoidCallback onSignOut;
  const StaffNotice({super.key, required this.me, required this.onSignOut});
  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: Row(children: [Image.asset(Theme.of(context).brightness == Brightness.dark ? 'assets/logo-dark.png' : 'assets/logo-light.png', width: 30, height: 30), const SizedBox(width: 10), const Text('PAM')])),
        body: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text('Signed in as ${me.email}', style: const TextStyle(fontWeight: FontWeight.w700)),
            const SizedBox(height: 8),
            Text('${me.role.toLowerCase()} tools live in the web console at pam.is-cool.dev. The app is for households.'),
            const SizedBox(height: 20),
            OutlinedButton(onPressed: onSignOut, child: const Text('Sign out')),
          ]),
        ),
      );
}

class Home extends StatefulWidget {
  final Me me;
  final VoidCallback onSignOut;
  const Home({super.key, required this.me, required this.onSignOut});
  @override
  State<Home> createState() => _HomeState();
}

class _HomeState extends State<Home> {
  int _i = 0;
  int _rev = 0; // bump to make tabs reload after an entry is written
  bool _walk = false;

  @override
  void initState() {
    super.initState();
    Prefs.seenWalkthrough(widget.me.id).then((seen) { if (!seen && mounted) setState(() => _walk = true); });
  }

  Future<void> _finishWalk() async {
    await Prefs.markWalkthrough(widget.me.id);
    if (mounted) setState(() { _walk = false; _i = 0; _rev++; });
  }

  Future<void> _replayWalk() async {
    await Prefs.markWalkthrough(widget.me.id, seen: false);
    if (mounted) setState(() => _walk = true);
  }

  @override
  Widget build(BuildContext context) {
    if (_walk) return Walkthrough(onDone: _finishWalk);
    final pages = [
      Folio(key: ValueKey('f$_rev'), onGo: (t) => setState(() => _i = t)),
      Entries(key: ValueKey('e$_rev'), onChanged: () => setState(() => _rev++)),
      Recurring(key: ValueKey('r$_rev')),
      Books(key: ValueKey('b$_rev'), me: widget.me, onChanged: () => setState(() => _rev++)),
      Settings(me: widget.me, onSignOut: widget.onSignOut, onReplayWalkthrough: _replayWalk),
    ];
    return Scaffold(
      body: SafeArea(
        child: Column(children: [
          ValueListenableBuilder<int>(
            valueListenable: Api.instance.inFlight,
            builder: (_, n, __) => SizedBox(height: 2, child: n > 0 ? const LinearProgressIndicator(minHeight: 2) : null),
          ),
          Expanded(child: IndexedStack(index: _i, children: pages)),
        ]),
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _i,
        onDestinationSelected: (v) { HapticFeedback.selectionClick(); setState(() => _i = v); },
        destinations: const [
          NavigationDestination(icon: Icon(Icons.menu_book_outlined), selectedIcon: Icon(Icons.menu_book), label: 'Folio'),
          NavigationDestination(icon: Icon(Icons.receipt_long_outlined), selectedIcon: Icon(Icons.receipt_long), label: 'Entries'),
          NavigationDestination(icon: Icon(Icons.repeat), label: 'Recurring'),
          NavigationDestination(icon: Icon(Icons.account_balance_wallet_outlined), selectedIcon: Icon(Icons.account_balance_wallet), label: 'Books'),
          NavigationDestination(icon: Icon(Icons.settings_outlined), selectedIcon: Icon(Icons.settings), label: 'Settings'),
        ],
      ),
    );
  }
}
