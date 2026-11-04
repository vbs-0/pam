# Evaluation — starter

All acceptance targets met: **yes**

| Metric | Value | Target | Pass |
|---|---|---|---|
| category_accuracy | 0.9810 | >= 0.85 | ✅ |
| transfer_f1 | 1.0000 | >= 0.95 | ✅ |
| refund_link_recall | 0.9358 | >= 0.9 | ✅ |
| tz_boundary_month_accuracy | 1.0000 | == 1.0 | ✅ |
| budget_mismatch_handling | 1.0000 | == 1.0 | ✅ |
| series_recall | 1.0000 | >= 0.85 | ✅ |
| missed_precision | 1.0000 | >= 0.8 | ✅ |
| missed_recall | 1.0000 | >= 0.8 | ✅ |
| decoy_false_alarm_rate | 0.0000 | <= 0.1 | ✅ |

## Labelled anomalies

| Issue | Caught | Total | Recall |
|---|---|---|---|
| BUDGET_CATEGORY_MISMATCH | 10 | 10 | 100.00% |
| RECURRING_NOT_SKIP | 12 | 12 | 100.00% |
| RECURRING_SKIP | 6 | 6 | 100.00% |
| REFUND_AS_EXPENSE | 23 | 25 | 92.00% |
| TRANSFER_DOUBLE_COUNT | 20 | 20 | 100.00% |
| TZ_BOUNDARY | 20 | 20 | 100.00% |

## Categorization

Accuracy 98.10% · macro-F1 0.9898 · coverage 99.32% · kind accuracy 99.32%

| Category | Precision | Recall | F1 | Support |
|---|---|---|---|---|
| CASH_WITHDRAWAL | 1.000 | 1.000 | 1.000 | 730 |
| CC_BILL_PAYMENT | 1.000 | 1.000 | 1.000 | 598 |
| EDUCATION | 1.000 | 1.000 | 1.000 | 320 |
| EMI_LOANS | 1.000 | 1.000 | 1.000 | 184 |
| ENTERTAINMENT | 1.000 | 1.000 | 1.000 | 929 |
| FOOD_DINING | 0.985 | 1.000 | 0.992 | 4306 |
| FUEL | 1.000 | 1.000 | 1.000 | 1164 |
| GROCERIES | 0.995 | 0.964 | 0.979 | 4228 |
| HEALTH | 1.000 | 0.894 | 0.944 | 1211 |
| INSURANCE | 1.000 | 1.000 | 1.000 | 16 |
| INTEREST | 1.000 | 1.000 | 1.000 | 306 |
| OTHER_INCOME | 1.000 | 1.000 | 1.000 | 200 |
| PERSONAL_CARE | 0.882 | 1.000 | 0.938 | 623 |
| RENT | 1.000 | 1.000 | 1.000 | 347 |
| SALARY | 1.000 | 1.000 | 1.000 | 540 |
| SELF_TRANSFER | 1.000 | 1.000 | 1.000 | 1298 |
| SHOPPING | 0.944 | 0.922 | 0.933 | 2475 |
| SUBSCRIPTIONS | 1.000 | 1.000 | 1.000 | 974 |
| TRANSPORT | 1.000 | 1.000 | 1.000 | 2148 |
| TRAVEL | 1.000 | 1.000 | 1.000 | 680 |
| UTILITIES | 1.000 | 1.000 | 1.000 | 1723 |

## Links

| Link | Precision | Recall | F1 |
|---|---|---|---|
| Transfer pairs | 1.0000 | 1.0000 | 1.0000 |
| Refund → purchase | 0.9333 | 0.9358 | 0.9346 |
| Reversal pairs | 1.0000 | 1.0000 | 1.0000 |

## Recurring payments

Series precision 0.9975, recall 1.0000; member F1 0.9996. MISSED events: precision 1.0000, recall 1.0000 (6 labelled skips), decoy false-alarm rate 0.0000 (12 decoys).

| Type | Truth series | Matched |
|---|---|---|
| EMI | 17 | 17 |
| INTEREST | 76 | 76 |
| RENT | 29 | 29 |
| SALARY | 45 | 45 |
| SUBSCRIPTION | 90 | 90 |
| UTILITY | 139 | 139 |

## Time zone and budgets

IST month accuracy 100.00% vs naive UTC 99.79%; TZ-boundary cases 20 at 100.00%. Spend MAE per user-month-category ₹155.45 over 6908 cells.

## Naive ledger baseline

| Ledger | Total spend |
|---|---|
| Ground truth | ₹4,00,67,179.86 |
| PAM | ₹4,00,67,179.86 (+0.00%) |
| Naive (all debits + non-salary credits, UTC months) | ₹9,18,72,481.28 (+129.30%) |
