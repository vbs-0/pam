import 'package:flutter_test/flutter_test.dart';
import 'package:pam_mobile/offline.dart';

Map<String, dynamic> txn(String id, int amt, String date, {String kind = 'EXPENSE', String cat = 'FOOD', String acct = 'A1'}) => {
      'txn_id': id, 'local_date': date, 'posted_at': '${date}T12:00:00+05:30', 'account_id': acct, 'amount_paise': amt, 'channel': 'UPI',
      'descriptor': 'Swiggy $id', 'merchant_name': null, 'category_code': cat, 'kind': kind, 'note': '', 'tags': <String>[],
    };

void main() {
  final l = Local.instance, ob = Outbox.instance;
  setUp(() {
    ob.pending.clear();
    l.mirror..clear()..addAll({'T1': txn('T1', -10000, '2026-11-02'), 'T2': txn('T2', -5000, '2026-11-03', cat: 'FUEL')});
  });

  test('a queued new entry shows up in lists, accounts and totals, and is counted once', () {
    ob.pending.add(Op.create('POST', '/me/transactions', {'account_id': 'A1', 'date': '2026-11-04', 'amount_paise': 2500, 'direction': 'DR', 'description': 'Chai', 'category_code': 'FOOD'}, temps: 1));
    final list = l.listFor({'month': '2026-11'})!['items'] as List;
    expect(list.length, 3);
    expect((list.first as Map)['descriptor'], 'Chai');
    final acc = l.accountsView([{'account_id': 'A1', 'balance_paise': 100000, 'status': 'ACTIVE'}]);
    expect((acc.first as Map)['balance_paise'], 97500);
    final s = l.summaryView({'spend_paise': 15000, 'naive_spend_paise': 15000, 'income_paise': 0, 'savings_rate': null}, '2026-11');
    expect(s['spend_paise'], 17500);
  });

  test('delete and edit are applied on top of the server copy', () {
    ob.pending.add(Op.create('DELETE', '/me/transactions/T1', null));
    ob.pending.add(Op.create('PATCH', '/me/transactions/T2', {'amount_paise': 8000}));
    final list = (l.listFor({})!['items'] as List).cast<Map<String, dynamic>>();
    expect(list.map((t) => t['txn_id']), ['T2']);
    expect(list.first['amount_paise'], -8000);
    final d = l.dailyView({
      'days': [
        {'date': '2026-11-03', 'spend_paise': 5000, 'income_paise': 0, 'count': 1},
        {'date': '2026-11-02', 'spend_paise': 10000, 'income_paise': 0, 'count': 1},
      ],
      'days_elapsed': 5,
      'total_spend_paise': 15000,
    }, '2026-11');
    expect(d['total_spend_paise'], 8000);
  });

  test('a split replaces the original with its parts and the total is unchanged', () {
    ob.pending.add(Op.create('POST', '/me/transactions/T1/split', {'parts': [{'amount_paise': 6000, 'category_code': 'FOOD'}, {'amount_paise': 4000, 'category_code': 'FUEL'}]}, temps: 2));
    final list = (l.listFor({'month': '2026-11'})!['items'] as List).cast<Map<String, dynamic>>();
    expect(list.where((t) => t['txn_id'] == 'T1'), isEmpty);
    expect(list.where((t) => (t['txn_id'] as String).startsWith('L-')).fold<int>(0, (s, t) => s + (t['amount_paise'] as int)), -10000);
  });

  test('filters work locally: category, amount range and search', () {
    expect((l.listFor({'category': 'FOOD', 'min_paise': '6000'})!['items'] as List).length, 1);
    expect((l.listFor({'q': '50'})!['items'] as List).length, 1); // amount 50.00
    expect((l.listFor({'q': 'nothing'})!['items'] as List).length, 0);
  });

  test('goal changes queue on top of the server list', () {
    ob.pending.add(Op.create('POST', '/me/goals/G1/contribute', {'amount_paise': 2000}));
    final g = l.goalsView([{'goal_id': 'G1', 'name': 'Trip', 'target_paise': 10000, 'saved_paise': 1000, 'deadline': null}]);
    expect((g.first as Map)['saved_paise'], 3000);
  });
}
