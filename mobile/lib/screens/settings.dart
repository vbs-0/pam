import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../api.dart';
import '../prefs.dart';
import '../theme.dart';
import '../ui/widgets.dart';

class Settings extends StatelessWidget {
  final Me me;
  final VoidCallback onSignOut, onReplayWalkthrough;
  const Settings({super.key, required this.me, required this.onSignOut, required this.onReplayWalkthrough});

  Future<void> _confirmSignOut(BuildContext context) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (c) => AlertDialog(
        title: const Text('Sign out?'),
        content: const Text('You will need your email and password (or Google) to open your register again.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(c, false), child: const Text('Stay')),
          FilledButton(onPressed: () => Navigator.pop(c, true), child: const Text('Sign out')),
        ],
      ),
    );
    if (ok == true) { HapticFeedback.mediumImpact(); onSignOut(); }
  }

  @override
  Widget build(BuildContext context) {
    final k = Palette.of(context);
    final initial = me.email.isEmpty ? '?' : me.email[0].toUpperCase();
    return ListView(padding: const EdgeInsets.fromLTRB(16, 16, 16, 24), children: [
      const Text('Settings', style: TextStyle(fontSize: 26, fontWeight: FontWeight.w700, letterSpacing: -.4)),
      const SizedBox(height: 16),
      Container(
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(color: k.sheet, border: Border.all(color: k.ruleStrong)),
        child: Row(children: [
          CircleAvatar(radius: 24, backgroundColor: k.blueSoft, child: Text(initial, style: TextStyle(color: k.blue, fontWeight: FontWeight.w800, fontSize: 20))),
          const SizedBox(width: 14),
          Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(me.email, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16), overflow: TextOverflow.ellipsis),
            const SizedBox(height: 4),
            Wrap(spacing: 8, children: [Stamp(me.role, k.blue), if (me.profile != null) Text(me.profile!, style: TextStyle(color: k.muted, fontSize: 12))]),
          ])),
        ]),
      ),
      const SectionTitle('Appearance'),
      const SizedBox(height: 10),
      ValueListenableBuilder<ThemeMode>(
        valueListenable: Prefs.themeMode,
        builder: (_, mode, __) => SizedBox(
          width: double.infinity,
          child: SegmentedButton<ThemeMode>(
            showSelectedIcon: false,
            segments: const [
              ButtonSegment(value: ThemeMode.system, icon: Icon(Icons.brightness_auto, size: 18), label: Text('System')),
              ButtonSegment(value: ThemeMode.light, icon: Icon(Icons.light_mode_outlined, size: 18), label: Text('Light')),
              ButtonSegment(value: ThemeMode.dark, icon: Icon(Icons.dark_mode_outlined, size: 18), label: Text('Dark')),
            ],
            selected: {mode},
            onSelectionChanged: (s) { HapticFeedback.selectionClick(); Prefs.setTheme(s.first); },
          ),
        ),
      ),
      const SectionTitle('Help'),
      _Row(Icons.slideshow_outlined, 'Replay the walkthrough', 'A 30-second tour of what PAM does', onReplayWalkthrough),
      _Row(Icons.language, 'Open the web console', Uri.parse(apiBase).host, () => _openAbout(context, web: true)),
      const SectionTitle('About'),
      _Row(Icons.info_outline, 'About PAM', 'Version $appVersion', () => _openAbout(context)),
      _Row(Icons.description_outlined, 'Open-source licences', 'Libraries this app is built with', () => showLicensePage(context: context, applicationName: 'PAM', applicationVersion: appVersion)),
      const SectionTitle('Account'),
      const SizedBox(height: 10),
      OutlinedButton.icon(onPressed: () => _confirmSignOut(context), icon: const Icon(Icons.logout), label: const Text('Sign out')),
      const SizedBox(height: 16),
      Center(child: Text('PAM $appVersion · ${Uri.parse(apiBase).host}', style: TextStyle(color: k.muted, fontSize: 12))),
    ]);
  }

  void _openAbout(BuildContext context, {bool web = false}) {
    final k = Palette.of(context);
    showModalBottomSheet<void>(
      context: context, isScrollControlled: true, useSafeArea: true,
      builder: (c) => Padding(
        padding: const EdgeInsets.fromLTRB(20, 20, 20, 28),
        child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            Image.asset(Theme.of(c).brightness == Brightness.dark ? 'assets/logo-dark.png' : 'assets/logo-light.png', width: 56, height: 56),
            const SizedBox(width: 14),
            Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(web ? 'Web console' : 'PAM', style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w700)),
              Text(web ? 'Analysts, reviewers and admins' : 'Payment Account Manager · v$appVersion', style: TextStyle(color: k.muted)),
            ]),
          ]),
          const SizedBox(height: 16),
          if (web) ...[
            const Text('Staff roles (analyst, reviewer, admin) work in the web console. Open this address in a browser:'),
            const SizedBox(height: 10),
            SelectableText('https://${Uri.parse(apiBase).host}', style: TextStyle(color: k.blue, fontWeight: FontWeight.w700, fontSize: 16)),
            const SizedBox(height: 10),
            OutlinedButton.icon(
              onPressed: () { Clipboard.setData(ClipboardData(text: 'https://${Uri.parse(apiBase).host}')); HapticFeedback.selectionClick(); Navigator.pop(c); ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Address copied'))); },
              icon: const Icon(Icons.copy, size: 18), label: const Text('Copy address'),
            ),
          ] else ...[
            const Text('PAM turns a household\'s bank and UPI transactions into answers to three questions: what did we really spend, what repeats, and are we inside budget?'),
            const SizedBox(height: 12),
            Text('Amounts are kept in paise, dates follow Indian Standard Time, and everything PAM decides can be traced to a rule and a version.', style: TextStyle(color: k.muted)),
            const SizedBox(height: 12),
            Text('The sample households (USR-000001 onwards) are synthetic. No real person, account or transaction data is used.', style: TextStyle(color: k.muted)),
            const SizedBox(height: 12),
            Text('Source: github.com/vbs-0/pam', style: TextStyle(color: k.blue, fontWeight: FontWeight.w600)),
          ],
        ]),
      ),
    );
  }
}

class _Row extends StatelessWidget {
  final IconData icon;
  final String title, sub;
  final VoidCallback onTap;
  const _Row(this.icon, this.title, this.sub, this.onTap);
  @override
  Widget build(BuildContext context) {
    final k = Palette.of(context);
    return InkWell(
      onTap: () { HapticFeedback.selectionClick(); onTap(); },
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 14),
        decoration: BoxDecoration(border: Border(bottom: BorderSide(color: k.rule))),
        child: Row(children: [
          Icon(icon, color: k.blue),
          const SizedBox(width: 14),
          Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(title, style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 16)),
            Text(sub, style: TextStyle(color: k.muted, fontSize: 13)),
          ])),
          Icon(Icons.chevron_right, color: k.muted),
        ]),
      ),
    );
  }
}
