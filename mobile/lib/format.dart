import 'package:intl/intl.dart';

// Money arrives as integer paise; format only at the edge.
final _inr = NumberFormat('#,##,##0.00', 'en_IN');
final _inr0 = NumberFormat('#,##,##0', 'en_IN');

String rupees(int paise) => _inr.format(paise.abs() / 100);
String rupeesShort(int paise) => _inr0.format((paise.abs() / 100).round());
String inr(int paise, {bool sign = false}) => '${paise < 0 ? '−' : (sign && paise > 0 ? '+' : '')}₹${rupees(paise)}';

/// "1,250.5" -> 125050; null when it is not a plain amount.
int? toPaise(String input) {
  final s = input.replaceAll(RegExp(r'[,₹\s]'), '');
  if (!RegExp(r'^\d+(\.\d{1,2})?$').hasMatch(s)) return null;
  final parts = s.split('.');
  return int.parse(parts[0]) * 100 + (parts.length > 1 ? int.parse(parts[1].padRight(2, '0')) : 0);
}

const _months = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
String monthName(String m) => '${_months[int.parse(m.substring(5, 7)) - 1]} ${m.substring(0, 4)}';
String shiftMonth(String m, int by) {
  final d = DateTime.utc(int.parse(m.substring(0, 4)), int.parse(m.substring(5, 7)) + by, 1);
  return '${d.year}-${d.month.toString().padLeft(2, '0')}';
}

String _istNow() => DateTime.now().toUtc().add(const Duration(hours: 5, minutes: 30)).toIso8601String();
String todayIso() => _istNow().substring(0, 10);
String currentMonth() => _istNow().substring(0, 7);
String dayLabel(String iso) => '${iso.substring(8, 10)} ${_months[int.parse(iso.substring(5, 7)) - 1].substring(0, 3)}';
String titleCase(String code) => code.toLowerCase().split('_').map((w) => w.isEmpty ? w : w[0].toUpperCase() + w.substring(1)).join(' ');
