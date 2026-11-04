# Evaluation — full

All acceptance targets met: **yes**

| Metric | Value | Target | Pass |
|---|---|---|---|
| category_accuracy | 0.9799 | >= 0.85 | ✅ |
| transfer_f1 | 1.0000 | >= 0.95 | ✅ |
| refund_link_recall | 0.9091 | >= 0.9 | ✅ |
| tz_boundary_month_accuracy | 1.0000 | == 1.0 | ✅ |
| budget_mismatch_handling | 1.0000 | == 1.0 | ✅ |
| series_recall | 0.9995 | >= 0.85 | ✅ |
| missed_precision | 0.9600 | >= 0.8 | ✅ |
| missed_recall | 1.0000 | >= 0.8 | ✅ |
| decoy_false_alarm_rate | 0.0000 | <= 0.1 | ✅ |

## Labelled anomalies

| Issue | Caught | Total | Recall |
|---|---|---|---|
| BUDGET_CATEGORY_MISMATCH | 200 | 200 | 100.00% |
| RECURRING_NOT_SKIP | 240 | 240 | 100.00% |
| RECURRING_SKIP | 120 | 120 | 100.00% |
| REFUND_AS_EXPENSE | 465 | 500 | 93.00% |
| TRANSFER_DOUBLE_COUNT | 400 | 400 | 100.00% |
| TZ_BOUNDARY | 400 | 400 | 100.00% |

## Categorization

Accuracy 97.99% · macro-F1 0.9899 · coverage 99.26% · kind accuracy 99.27%

| Category | Precision | Recall | F1 | Support |
|---|---|---|---|---|
| CASH_WITHDRAWAL | 1.000 | 1.000 | 1.000 | 15675 |
| CC_BILL_PAYMENT | 1.000 | 1.000 | 1.000 | 12514 |
| EDUCATION | 1.000 | 1.000 | 1.000 | 6296 |
| EMI_LOANS | 1.000 | 1.000 | 1.000 | 3119 |
| ENTERTAINMENT | 1.000 | 1.000 | 1.000 | 18188 |
| FOOD_DINING | 0.986 | 1.000 | 0.993 | 87068 |
| FUEL | 1.000 | 1.000 | 1.000 | 24729 |
| GROCERIES | 0.993 | 0.955 | 0.974 | 85324 |
| HEALTH | 1.000 | 0.899 | 0.947 | 25694 |
| INSURANCE | 1.000 | 1.000 | 1.000 | 366 |
| INTEREST | 1.000 | 1.000 | 1.000 | 5603 |
| OTHER_INCOME | 1.000 | 1.000 | 1.000 | 6299 |
| PERSONAL_CARE | 0.888 | 1.000 | 0.941 | 12771 |
| RENT | 1.000 | 1.000 | 1.000 | 7824 |
| SALARY | 1.000 | 1.000 | 1.000 | 10188 |
| SELF_TRANSFER | 1.000 | 1.000 | 1.000 | 19304 |
| SHOPPING | 0.940 | 0.927 | 0.933 | 49255 |
| SUBSCRIPTIONS | 1.000 | 1.000 | 1.000 | 19049 |
| TRANSPORT | 1.000 | 1.000 | 1.000 | 42661 |
| TRAVEL | 1.000 | 1.000 | 1.000 | 13579 |
| UTILITIES | 1.000 | 1.000 | 1.000 | 34494 |

## Links

| Link | Precision | Recall | F1 |
|---|---|---|---|
| Transfer pairs | 1.0000 | 1.0000 | 1.0000 |
| Refund → purchase | 0.9077 | 0.9091 | 0.9084 |
| Reversal pairs | 1.0000 | 1.0000 | 1.0000 |

## Recurring payments

Series precision 0.9967, recall 0.9995; member F1 0.9994. MISSED events: precision 0.9600, recall 1.0000 (120 labelled skips), decoy false-alarm rate 0.0000 (240 decoys).

| Type | Truth series | Matched |
|---|---|---|
| EMI | 298 | 298 |
| INTEREST | 1398 | 1398 |
| RENT | 654 | 654 |
| SALARY | 849 | 849 |
| SUBSCRIPTION | 1768 | 1765 |
| UTILITY | 2788 | 2787 |

## Time zone and budgets

IST month accuracy 100.00% vs naive UTC 99.80%; TZ-boundary cases 400 at 100.00%. Spend MAE per user-month-category ₹164.64 over 138363 cells.

## Naive ledger baseline

| Ledger | Total spend |
|---|---|
| Ground truth | ₹83,26,12,475.37 |
| PAM | ₹83,26,12,475.37 (+0.00%) |
| Naive (all debits + non-salary credits, UTC months) | ₹1,76,28,93,455.09 (+111.73%) |
