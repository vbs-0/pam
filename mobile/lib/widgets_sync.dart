import 'package:home_widget/home_widget.dart';

import 'api.dart';
import 'format.dart';

const _providers = ['dev.is_cool.pam_mobile.TodayWidget', 'dev.is_cool.pam_mobile.BudgetWidget', 'dev.is_cool.pam_mobile.BillsWidget'];

Future<void> _push() async {
  for (final p in _providers) {
    try { await HomeWidget.updateWidget(qualifiedAndroidName: p); } catch (_) {/* widget not on the home screen */}
  }
}

Future<void> _save(Map<String, String> data) async {
  for (final e in data.entries) {
    try { await HomeWidget.saveWidgetData<String>(e.key, e.value); } catch (_) {/* best effort */}
  }
}

String _two(int n) => n.toString().padLeft(2, '0');

/// Save today's figures for the home-screen widgets. Runs when the app opens and after every change; the widgets
/// show the last saved numbers together with the time they were saved, so a stale one is never mistaken for live.
Future<void> refreshWidgets() async {
  try {
    final month = currentMonth();
    final r = await Future.wait([
      Api.instance.get('/me/daily', {'month': month}),
      Api.instance.get('/me/budgets', {'month': month}),
      Api.instance.get('/me/upcoming', {'days': '30'}),
    ]);
    final daily = r[0] as Map<String, dynamic>;
    final today = todayIso();
    final days = (daily['days'] as List).cast<Map<String, dynamic>>();
    final todaySpend = days.where((d) => d['date'] == today).fold<int>(0, (s, d) => s + (d['spend_paise'] as int));
    final monthSpend = daily['total_spend_paise'] as int;
    final budgets = r[1] as Map<String, dynamic>;
    final total = budgets['total_budget_paise'] as int;
    final items = ((r[2] as Map<String, dynamic>)['items'] as List).cast<Map<String, dynamic>>();
    final now = DateTime.now();
    final bills = <String, String>{
      for (var i = 0; i < 3; i++) 'bill_${i + 1}': i < items.length ? '${dayLabel(items[i]['due'] as String)}  ${items[i]['name']}  ${inr(items[i]['amount_paise'] as int)}' : '',
    };
    await _save({
      'signed_in': '1',
      'today_spend': inr(todaySpend),
      'month_spend': inr(monthSpend),
      'month_name': monthName(month).split(' ').first,
      'budget_total': total > 0 ? inr(total) : '',
      'budget_pct': total > 0 ? '${(monthSpend * 100 / total).round()}' : '0',
      'updated': '${_two(now.hour)}:${_two(now.minute)}',
      ...bills,
    });
    await _push();
  } catch (_) {/* offline or signed out: keep what the widgets already show */}
}

/// On sign out the widgets must not keep showing someone's figures.
Future<void> clearWidgets() async {
  await _save({'signed_in': '0', 'today_spend': '', 'month_spend': '', 'budget_total': '', 'bill_1': '', 'bill_2': '', 'bill_3': ''});
  await _push();
}
