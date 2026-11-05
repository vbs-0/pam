import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../api.dart';
import '../theme.dart';
import 'account.dart';
import 'books.dart';
import 'plan.dart';
import 'recurring.dart';
import 'settings.dart';

/// Everything that is not one of the four everyday tabs: planning, accounts, sharing, data and settings.
class More extends StatelessWidget {
  final Me me;
  final VoidCallback onChanged, onSignOut, onReplayWalkthrough;
  final Future<void> Function() onMeChanged;
  const More({super.key, required this.me, required this.onChanged, required this.onSignOut, required this.onReplayWalkthrough, required this.onMeChanged});

  void _go(BuildContext c, Widget w) {
    HapticFeedback.selectionClick();
    Navigator.of(c).push(MaterialPageRoute<void>(builder: (_) => w));
  }

  void _root(BuildContext c, VoidCallback f) {
    Navigator.of(c).popUntil((r) => r.isFirst);
    f();
  }

  @override
  Widget build(BuildContext context) {
    final k = Palette.of(context);
    Widget group(String title, List<Widget> rows) => Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Padding(padding: const EdgeInsets.only(top: 22, bottom: 2), child: Text(title.toUpperCase(), style: TextStyle(color: k.muted, fontWeight: FontWeight.w800, fontSize: 12, letterSpacing: 1))),
          ...rows,
        ]);
    Widget row(IconData i, String t, String sub, Widget Function() page) => InkWell(
          onTap: () => _go(context, page()),
          child: Container(
            padding: const EdgeInsets.symmetric(vertical: 13),
            decoration: BoxDecoration(border: Border(bottom: BorderSide(color: k.rule))),
            child: Row(children: [
              Icon(i, color: k.blue),
              const SizedBox(width: 14),
              Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [Text(t, style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 16)), Text(sub, style: TextStyle(color: k.muted, fontSize: 13))])),
              Icon(Icons.chevron_right, color: k.muted),
            ]),
          ),
        );
    return ListView(padding: const EdgeInsets.fromLTRB(16, 16, 16, 24), children: [
      const Text('More', style: TextStyle(fontSize: 26, fontWeight: FontWeight.w700, letterSpacing: -.4)),
      group('Plan', [
        row(Icons.flag_outlined, 'Budgets', 'Limits per category, with rollover', () => BudgetsScreen(onChanged: onChanged)),
        row(Icons.notifications_none, 'Bills & alerts', 'Due soon, card limits, net worth', () => const BillsScreen()),
        row(Icons.savings_outlined, 'Savings goals', 'Targets and how much to set aside', () => const GoalsScreen()),
        row(Icons.repeat, 'Recurring', 'Subscriptions, rent, salary', () => Scaffold(appBar: AppBar(title: const Text('Recurring')), body: const Recurring())),
      ]),
      group('Accounts', [
        row(Icons.account_balance_wallet_outlined, 'Books', 'Accounts, balances and cards', () => Scaffold(appBar: AppBar(title: const Text('Books')), body: Books(me: me, onChanged: onChanged))),
        row(Icons.group_outlined, 'Share your register', 'Invite a partner or family member', () => HouseholdScreen(onChanged: onChanged)),
      ]),
      group('Data', [
        row(Icons.ios_share, 'Export and backup', 'CSV, full backup, restore', () => DataScreen(onChanged: onChanged)),
        row(Icons.mail_outline, 'Daily email', 'A short note when something needs a look', () => const NotificationsScreen()),
      ]),
      group('App', [
        row(Icons.lock_outline, 'Account and security', 'Password, email, delete account', () => SecurityScreen(me: me, onMeChanged: onMeChanged, onDeleted: () => _root(context, onSignOut))),
        row(Icons.settings_outlined, 'Settings', 'Theme, walkthrough, about, sign out', () => Scaffold(appBar: AppBar(title: const Text('Settings')), body: Settings(me: me, onSignOut: () => _root(context, onSignOut), onReplayWalkthrough: () => _root(context, onReplayWalkthrough)))),
      ]),
    ]);
  }
}
