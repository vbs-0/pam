import 'package:firebase_core/firebase_core.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'api.dart';
import 'screens/calendar.dart';
import 'screens/more.dart';
import 'screens/spend.dart';
import 'screens/entries.dart';
import 'screens/folio.dart';
import 'screens/login.dart';
import 'prefs.dart';
import 'screens/onboarding.dart';
import 'theme.dart';
import 'widgets_sync.dart';
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

  Future<void> _refreshMe() async {
    try { final m = await Api.instance.me(); if (mounted) setState(() => _me = m); } catch (_) {/* keep the old one */}
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
                    : Home(me: _me!, onMeChanged: _refreshMe, onSignOut: () async { await Api.instance.signOut(); setState(() => _me = null); }),
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
  final Future<void> Function() onMeChanged;
  const Home({super.key, required this.me, required this.onSignOut, required this.onMeChanged});
  @override
  State<Home> createState() => _HomeState();
}

class _HomeState extends State<Home> {
  int _i = 0;
  int _rev = 0; // bump to make tabs reload after an entry is written
  bool _walk = false;
  String _entriesFilter = '';
  int _entriesKey = 0;

  @override
  void initState() {
    super.initState();
    _maybeWalk();
    refreshWidgets();
  }

  Future<void> _maybeWalk() async {
    if (await Prefs.seenWalkthrough(widget.me.id)) return;
    var hasData = true; // on any error assume an existing user: never nag
    try {
      final r = await Future.wait([Api.instance.get('/me/accounts'), Api.instance.get('/me/transactions', {'limit': '1'})]);
      hasData = (r[0] as List).isNotEmpty || ((r[1] as Map)['items'] as List).isNotEmpty;
    } catch (_) {/* keep hasData = true */}
    if (hasData) { await Prefs.markWalkthrough(widget.me.id); return; }
    if (mounted) setState(() => _walk = true);
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
    void changed() { setState(() => _rev++); refreshWidgets(); }
    final pages = [
      Folio(key: ValueKey('f$_rev'), onGo: (t) => setState(() => _i = t == 3 ? 4 : t)),
      Entries(key: ValueKey('e$_rev-$_entriesKey'), initial: _entriesFilter, onChanged: changed),
      CalendarScreen(key: ValueKey('c$_rev'), onChanged: changed),
      SpendScreen(key: ValueKey('s$_rev'), onOpenEntries: (f) => setState(() { _entriesFilter = f; _entriesKey++; _i = 1; })),
      More(me: widget.me, onChanged: changed, onSignOut: widget.onSignOut, onReplayWalkthrough: _replayWalk, onMeChanged: widget.onMeChanged),
    ];
    return Scaffold(
      body: SafeArea(
        child: Column(children: [
          ValueListenableBuilder<int>(
            valueListenable: Api.instance.inFlight,
            builder: (_, n, __) => SizedBox(height: 2, child: n > 0 ? const LinearProgressIndicator(minHeight: 2) : null),
          ),
          ValueListenableBuilder<bool>(
            valueListenable: Api.instance.offline,
            builder: (_, off, __) => off
                ? Container(width: double.infinity, color: Palette.of(context).amber, padding: const EdgeInsets.symmetric(vertical: 5, horizontal: 12), child: Text('Offline · showing what was last saved on this phone', textAlign: TextAlign.center, style: TextStyle(color: Palette.of(context).paper, fontWeight: FontWeight.w700, fontSize: 12)))
                : const SizedBox.shrink(),
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
          NavigationDestination(icon: Icon(Icons.calendar_month_outlined), selectedIcon: Icon(Icons.calendar_month), label: 'Calendar'),
          NavigationDestination(icon: Icon(Icons.pie_chart_outline), selectedIcon: Icon(Icons.pie_chart), label: 'Spend'),
          NavigationDestination(icon: Icon(Icons.apps_outlined), selectedIcon: Icon(Icons.apps), label: 'More'),
        ],
      ),
    );
  }
}
