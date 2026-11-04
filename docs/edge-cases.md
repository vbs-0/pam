# Edge-Case Catalogue

Living document. Every case is handled in code **and** covered by a test before it is marked done.
Status: `planned` → `done` (with the test that proves it). Labelled anomaly types from the brief are marked ★;
`injected` means the labelled case is generated and its shape is tested, while the engine side is still to come.

## Data generation and ledger integrity (D)

| ID | Scenario | Expected handling | Where | Test | Status |
|---|---|---|---|---|---|
| D01 | Account id must embed its owner (`ACC-USR-000001-01`) but a joint holder is a different user | Owner = id prefix; joint holder only in `account_holder` (N:M bridge) | datagen/people.py | test_people::test_master_rows_integrity | done |
| D02 | Account opened during 2026 | No transaction before `opened_on`; opening balance 0 for cards | datagen/spending.py, ledger.py, schedules.py | test_generator::test_fk_and_owner_consistency, test_card_bills_follow_statements | done |
| D03 | Account closed mid-year | Balance swept to primary on `closed_on` (IMPS self pair), closing balance exactly 0, CLOSED event, no later txns | datagen/ledger.py | test_generator::test_balances_reconcile_and_savings_never_negative, test_fk_and_owner_consistency | done |
| D04 | Spending would overdraw a savings account | Opening balance raised (derived) so the running balance never goes below 0 | datagen/ledger.py | test_generator::test_balances_reconcile_and_savings_never_negative | done |
| D05 | Credit-card statement is zero or negative (only refunds) | No bill payment generated for that month | datagen/ledger.py | test_validate::test_clean_dataset_passes (cc_payments: no payment when statement ≤ 0) | done |
| D06 | December card statement | Unpaid inside the data window (paid Jan 2027); card closing balance = −Dec statement | datagen/ledger.py | test_validate::test_clean_dataset_passes (cc_payments: payments only for Jan–Nov statements) | done |
| D07 | Card opened before 2026 has a December 2025 statement | Opening outstanding is paid in January | datagen/ledger.py | test_validate::test_clean_dataset_passes (cc_payments: January payment = opening outstanding) | done |
| D08 | Savings interest rounds to < ₹1 or account closed mid-quarter | Minimum ₹1 credit; no interest for the quarter in which the account closed | datagen/ledger.py | test_validate::test_clean_dataset_passes (interest_derivation recomputes every quarter) | done |
| D09 | Exact volume required (500,000) | Count adjusted only via standalone savings UPI debits; total is exact | datagen/generator.py | test_generator::test_exact_counts_and_chronological_ids | done |
| D10 | Reference numbers | Unique per event, shared by the two legs of a transfer and by a reversal | datagen/descriptors.py | test_generator::test_references_unique_except_transfer_legs_and_reversals | done |
| D11 | 00:10 IST on 1 Jan 2026 is 2025 in UTC | Txn id year uses the IST year (`TXN-2026-…`) | datagen/generator.py | test_generator::test_exact_counts_and_chronological_ids (first row is 2025 in UTC, id says 2026) | done |
| D12 | Salary day falls on Sunday / 2nd or 4th Saturday / national holiday | Paid on the previous working day (RBI rules) | datagen/calendar.py | test_people::test_calendar_rules | done |
| D13 | Pension on the 1st is a holiday | Paid next working day | datagen/calendar.py | test_people::test_calendar_rules | done |
| D14 | Subscription billed on the 29th–31st | Clamped to month end in short months (natural decoy for skip detection) | datagen/schedules.py | test_recurring::test_shift_and_month_end_clamp_are_not_skips | done |
| D15 | 28-day mobile recharge | 13 charges in a calendar year, still one monthly series | datagen/schedules.py | test_recurring::test_same_merchant_two_series (28-day pack = 13 charges, one monthly series) | done |
| D16 | Refund date after 31 Dec 2026 | Refund dropped (outside window) | datagen/spending.py | test_generator::test_exact_counts_and_chronological_ids (no IST date outside 2026) | done |
| D17 | Multiple partial refunds of one order | Sum of refunds ≤ original | datagen/spending.py | test_generator::test_refunds_never_exceed_their_purchase | done |
| D18 | Refund whose purchase was in Dec 2025 | Orphan refund, truth link empty | datagen/spending.py | test_generator::test_coverage_of_required_phenomena | done |
| D19 | Local merchant not in the merchant master | `true_merchant_id` null; keyword fallback or UNCATEGORIZED | datagen/spending.py | test_generator::test_coverage_of_required_phenomena | done |
| D20 | "ENTERPRISES"/"TRADERS" shops sell anything | True category varies; rules cannot know → exception queue | datagen/catalog.py | test_evaluation::test_starter_meets_acceptance_thresholds (per-class F1 in reports/<scale>/evaluation.md; ambiguous shops land in the UNCATEGORIZED queue) | done |
| D21 | Two identical purchases same merchant, same day, same amount | Not duplicates (different RRN) | datagen, validate::duplicates | test_validate::test_clean_dataset_passes (duplicates on account+RRN+amount+time), test_detects_duplicate_pk_bad_fk_bad_enum | done |
| D22 | Household with no budgets (5%) | Budget page shows NO_BUDGET lines; no insights crash | datagen/budgets.py, engine | api test_summary_recurring_insights_shapes | planned |
| D23 | Budget revised mid-month | Version 2 effective; v1 kept as history | datagen/budgets.py | test_budgets_insights::test_latest_version_wins | done |
| D24 | Self-employed irregular income | No salary series; NEFT credits → OTHER_INCOME | datagen/schedules.py | test_evaluation::test_every_salary_and_pension_series_found | done |
| D25 | Retired household | Pension series (SALARY type), more health/grocery spend | datagen | test_evaluation::test_every_salary_and_pension_series_found | done |
| D26 | Joint account | Spend counts toward the owner's budget; joint holder can view it | datagen/people.py, api/me.py | api test_transactions_keyset_pagination_and_isolation | planned |
| D27 | Ground truth leaking into inputs | No `true_*` column in any input table or file | schema.py, validate | test_generator::test_ground_truth_not_in_inputs, validate::truth_isolation | done |
| D28 | Windows checkout rewrites CSV line endings | `.gitattributes` marks CSV/SQL/JSON `-text` so checksums hold | .gitattributes | repro check on a fresh clone | done |
| D29 | Same seed, different Python version / OS | RNG uses only `random.random()`; manifest has no timestamps | datagen/rand.py, writer.py | test_writer::test_repro_identical_across_interpreters (two fresh interpreters, PYTHONHASHSEED 1 and 2) | done |
| D30 | Same merchant runs two independent series on one account (Airtel broadband via BBPS ₹799 + Airtel prepaid via UPI ₹349 every 28 days) | Series key = counterparty + channel + amount band, never merchant alone | datagen/schedules.py, engine/recurring.py | test_recurring::test_same_merchant_two_series | done |
| D31 | Interest on an account closed in Q2 has only 1–2 postings | A truth series needs ≥ 3 occurrences; fewer are labelled INTEREST without a series | datagen/generator.py | test_generator::test_labels_complete_linked_and_truth_month_is_ist | done |
| D32 | Refund or reversal would land after the account closed | Dropped (the credit cannot post to a closed account) | datagen/spending.py | test_generator::test_fk_and_owner_consistency | done |
| D33 | Self transfer close to midnight before a closure day | Transfers only 08:00–21:59 and only while both accounts are open, so no leg lands on the closure day after the sweep | datagen/ledger.py | test_generator::test_balances_reconcile_and_savings_never_negative | done |
| D34 | Card purchase at 00:30 IST on the 1st | Belongs to the new month's statement (statements use the IST month, not UTC) | datagen/ledger.py | test_validate::test_clean_dataset_passes (cc_payments groups by IST month) | done |
| D35 | Requested volume too small for the households' fixed bills | Generator refuses with a clear error instead of silently producing fewer rows | datagen/generator.py | test_generator::test_too_few_transactions_rejected | done |
| D36 | Subscription on a credit card opened during 2026 | Card subscriptions only use cards opened before 2026, so no charge predates the card | datagen/schedules.py | test_generator::test_fk_and_owner_consistency | done |
| D37 | Partial refunds of the same order | Linked to the same purchase; second refund 1–5 days after the first; total ≤ original | datagen/spending.py | test_generator::test_refunds_never_exceed_their_purchase | done |
| D38 | Reference numbers must look like real RRNs and stay unique at 500k rows | Bijective key→RRN map (multiplier coprime with 10¹¹), 12 digits | datagen/descriptors.py | test_generator::test_references_unique_except_transfer_legs_and_reversals | done |
| D39 | CLI run in a Windows console (cp1252 has no ₹) | stdout/stderr reconfigured to UTF-8 at start-up | cli.py | manual: `python -m app.cli evaluate` in Windows 11 Terminal | done |

## Labelled anomalies from the brief (★)

| ID | Scenario | Expected handling | Where | Test | Status |
|---|---|---|---|---|---|
| ★A1 | Transfer counted as spending twice (UPI to own VPA with note "Payment"; credit leg 1–3 days later, maybe next month; card bill via CRED) | Own-VPA rule + pairing → both legs TRANSFER, excluded from spend | engine/pipeline.py, transfers.py | test_anomalies::test_transfer_double_count_shape, test_transfers_refunds::test_pairs_delayed_cross_month_transfer_and_not_other_users, test_evaluation::test_starter_meets_acceptance_thresholds (400/400 caught at full scale) | done |
| ★A2 | Refund treated as new expense (credit with no refund keyword) | Merchant credit → REFUND linked to original, nets the original category | engine/refunds.py | test_anomalies::test_refund_as_expense_has_no_keyword, test_transfers_refunds::test_refund_category_follows_original_and_reversal_by_rrn, test_evaluation::test_starter_meets_acceptance_thresholds (465/500 at full scale; misses are partial refunds with sibling orders, see E36) | done |
| ★A3 | Recurring series skips incorrectly (one occurrence missing) | MISSED event at the expected date ±7 days, then RESUMED | engine/recurring.py | test_anomalies::test_skip_really_missing_and_decoy_present, test_recurring::test_true_skip_emits_missed_and_resumed, test_evaluation::test_starter_meets_acceptance_thresholds (120/120) | done |
| ★A3b | Decoys: retry 2–4 days late, holiday shift, month-end clamp, cancellation | No MISSED event (cancellation → ENDED) | engine/recurring.py | test_recurring::test_shift_and_month_end_clamp_are_not_skips, test_cancelled_series_ends, test_evaluation::test_starter_meets_acceptance_thresholds (0 false alarms on 240 decoys) | done |
| ★A4 | Transaction date crosses timezone boundary (00:00–05:29 IST on the 1st) | Business month = IST month | engine/pipeline.py, timeutil.py | test_anomalies::test_tz_boundary_utc_month_differs, test_evaluation::test_starter_meets_acceptance_thresholds (400/400) | done |
| ★A5 | Budget categories do not match taxonomy (retired, lowercase, synonym, unknown) | Remap retired/case/synonym; unknown → UNMAPPED exception + insight | engine/budgets.py | test_anomalies::test_budget_mismatch_only_where_labelled, test_validate::test_detects_unlabelled_taxonomy_violation, test_budgets_insights::test_resolution_paths, test_evaluation::test_starter_meets_acceptance_thresholds (200/200) | done |

## Decision engine (E)

| ID | Scenario | Expected handling | Where | Test | Status |
|---|---|---|---|---|---|
| E01 | "amazon fresh" vs "amazon" | Longest alias wins; refinement rule → GROCERIES | engine/categorize.py | test_categorize::test_priority_and_refinement | done |
| E02 | VPA known but descriptor text misleading | VPA match beats alias | categorize.py | test_categorize::test_vpa_beats_alias_and_conditions | done |
| E03 | Same descriptor with different RRN | Cache hit (normalized text strips RRN) | normalize.py, categorize.py | test_categorize::test_cache_used | done |
| E04 | Rule direction/channel/account conditions | All non-null conditions must match | categorize.py | test_categorize::test_vpa_beats_alias_and_conditions | done |
| E05 | Equal amount moved to a different user | Never paired (pairing is per user) | transfers.py | test_transfers_refunds::test_pairs_delayed_cross_month_transfer_and_not_other_users | done |
| E06 | Debit and credit on the same account | Never a transfer | transfers.py | test_transfers_refunds::test_card_payment_and_window_and_same_account | done |
| E07 | Two identical transfers on one day | One-to-one greedy pairing by smallest gap | transfers.py | test_transfers_refunds::test_two_identical_transfers_pair_one_to_one | done |
| E08 | Credit leg posted before the debit (bank posting lag) | Window −1 day … +3 days | transfers.py | test_transfers_refunds::test_credit_before_debit_within_a_day | done |
| E09 | Transfer-categorized txn with no counterpart | Stays TRANSFER, exception UNMATCHED_TRANSFER | pipeline.py | test_pipeline | planned |
| E10 | UPI debit failed and auto-reversed (same RRN) | Both legs REVERSAL, excluded from spend | refunds.py | test_transfers_refunds::test_refund_category_follows_original_and_reversal_by_rrn | done |
| E11 | Over-refund (more than remaining) | Orphan refund + exception | refunds.py | test_transfers_refunds::test_partial_refunds_link_and_net | done |
| E12 | Orphan refund from a non-expense category | Category UNCATEGORIZED, still reduces spend bucket | refunds.py | test_transfers_refunds::test_orphan_refund_non_expense_becomes_uncategorized | done |
| E13 | Refund in a later month | Reduces spend in the refund's month (cash basis, documented) | budgets.py | test_budgets_insights::test_spend_partition_refund_nets_transfer_excluded | done |
| E14 | User/analyst override | Locked: pairing, refunds, rent inference never change it; survives reruns | pipeline.py | test_pipeline::test_override_locks_decision, test_transfers_refunds::test_locked_items_untouched, jobs::test_override_survives_rerun | done |
| E15 | Two consecutive skips | Two MISSED events | recurring.py | test_recurring::test_double_skip_two_missed | done |
| E16 | One-step price change (salary hike, rent increase, plan upgrade) | Series kept; AMOUNT_CHANGED event; typical = recent median | recurring.py | test_recurring::test_price_change_allowed_and_logged | done |
| E17 | Variable bills (electricity, interest) | Wider amount tolerance; no AMOUNT_CHANGED noise | recurring.py | test_recurring::test_quarterly_interest_with_varying_amounts | done |
| E18 | Frequent merchant (Swiggy every few days) | Not a series (median gap outside cadence) | recurring.py | test_recurring::test_discretionary_noise_rejected | done |
| E19 | Rent paid by UPI to a person with no note | Monthly uncategorized P2P ≥ ₹5,000 inferred RENT (conf 0.7) | recurring.py | test_recurring::test_uncategorized_p2p_monthly_becomes_rent, test_small_p2p_is_not_rent | done |
| E20 | Series last seen 1.6–2.5 cycles ago | Status MISSED (not yet ENDED) | recurring.py | test_recurring::test_tail_gap_is_missed_not_ended | done |
| E21 | Fewer than 3 occurrences | Not a series | recurring.py | test_recurring::test_two_occurrences_not_series | done |
| E22 | Budget submitted for an INCOME category | UNMAPPED | budgets.py | test_budgets_insights::test_resolution_paths | done |
| E23 | Two budgets resolve to the same category | Amounts summed, both ids kept as evidence | budgets.py | test_budgets_insights::test_status_thresholds_and_lines | done |
| E24 | Budget amount 0 | OVER if any spend, else UNDER | budgets.py | test_budgets_insights::test_status_thresholds_and_lines | done |
| E25 | Uncategorized debits | Counted in spend under UNCATEGORIZED (never silently dropped) | budgets.py | test_budgets_insights::test_spend_partition_refund_nets_transfer_excluded | done |
| E26 | Ledger partition | Σ amounts = income − spend + transfers + reversals, per user | pipeline.py, outputs_validate.py | test_pipeline::test_pipeline_end_to_end_partition_and_exceptions | done |
| E27 | Rerun the pipeline | Same REC-/EXC- ids; resolved exceptions stay resolved; history kept per run | jobs/pipeline_job.py | test_outputs_validate_and_rerun_keeps_ids | done |
| E28 | Spend spike with < 3 prior months | No SPEND_SPIKE insight | insights.py | test_budgets_insights::test_spike_needs_three_prior_months | done |
| E29 | Month with zero income | LOW_SAVINGS skipped (no divide by zero) | insights.py | test_budgets_insights::test_low_savings_zero_income | done |
| E30 | Pipeline fails halfway | Run marked FAILED, outputs rolled back, readers keep using last SUCCEEDED run | jobs/pipeline_job.py | test_failed_run_is_invisible | done |
| E31 | Series on an account that closed mid-year (interest stops after the last quarter before closure) | Status ENDED because the account is CLOSED, even if the gap is still short | recurring.py | test_recurring::test_series_on_closed_account_ends | done |
| E32 | One merchant, two series (see D30) | Kept as two series; neither reports AMOUNT_CHANGED because of the other | recurring.py | test_recurring::test_same_merchant_two_series | done |
| E33 | Budget code typed with spaces, hyphens or lower case (`food-dining`, ` food dining `) | Canonicalised (upper, `_` separators) then REMAPPED_CASE, or REMAPPED_RETIRED if the canonical code is retired | budgets.py | test_budgets_insights::test_resolution_paths | done |
| E34 | Retired code used for a month before its retirement date | VALID for that month; remapping only applies after `effective_to`; a successor must itself be an active expense category | budgets.py | test_budgets_insights::test_retired_code_still_valid_before_retirement | done |
| E35 | Interest jumps 2–4× between quarters as balances grow | No amount-stability check for interest (fixed narration + quarterly cadence identify it) | recurring.py | test_recurring::test_quarterly_interest_with_varying_amounts | done |
| E36 | Partial refund while several orders at that merchant are open | Prefer the order whose unrefunded remainder equals the credit on the same account, else the closest order with enough remainder; genuinely ambiguous (~6–9% link to a sibling order, category usually identical) — documented limitation | refunds.py | test_transfers_refunds::test_refund_prefers_exact_amount_over_latest_purchase | done |
| E37 | Same merchant credit is a refund for one user and income for another | Refund only when the merchant's category is an expense or the narration says refund; salary/interest/other income never become refunds | refunds.py | test_pipeline::test_pipeline_end_to_end_partition_and_exceptions | done |

## API and security (A)

| ID | Scenario | Expected handling | Where | Test | Status |
|---|---|---|---|---|---|
| A01 | Customer requests another household's txn, account list or override | 404, same as a missing id (no existence leak) | api/me.py | test_me::test_cannot_read_other_users_txn | done |
| A02 | Expired, forged, `alg: none`, garbage tokens | 401 | api/deps.py | test_security::test_algorithm_confusion_rejected, test_local_token_roundtrip_and_failures; API: test_expired_and_forged_tokens_rejected | planned |
| A03 | Token says ADMIN but DB says CUSTOMER; demotion while a token is live | DB read on every request wins; unknown login id → 401 | api/deps.py | test_auth::test_login_me_and_role_from_db, test_disabled_and_deleted_logins | done |
| A04 | Disabled user with a valid token, or logging in | 403 (signed in, but not allowed) | api/deps.py, api/auth.py | test_auth::test_disabled_and_deleted_logins | done |
| A05 | Firebase token with wrong aud / iss / unknown kid | 401 | security.py | test_security::test_firebase_bad_claims_rejected, test_firebase_unknown_kid_and_other_signer | done |
| A06 | Two first-time Google logins race | Transaction-scoped advisory lock around find-or-create → one app_user | api/auth.py | test_auth::test_google_signup_link_and_conflicts (idempotent re-login) | done |
| A07 | Override with retired / UNKNOWN / non-existent category | 422; a retired code names its replacement | api/me.py | test_me::test_invalid_category_rejected | done |
| A08 | Invalid month (`2026-13`, `26-1`, `2026-3`) | 422 | api/common.py | test_me::test_summary_recurring_insights_shapes | done |
| A09 | Tampered or malformed cursor | 400 with "start again" message | api/common.py | test_me::test_bad_cursor_limit_and_search | done |
| A10 | `limit` 0 or 10,000 | 422 (bounds 1..100) | api/common.py | test_me::test_bad_cursor_limit_and_search | done |
| A11 | Search containing `%` or `_` | Escaped, matched literally | api/common.py | test_me::test_bad_cursor_limit_and_search | done |
| A12 | No successful pipeline run yet | 409 telling an admin to run the pipeline | api/common.py | test_me::test_no_run_409 | done |
| A13 | Invalid / concurrent exception transition | 409 | api/analyst.py | test_exception_lifecycle_and_invalid_transition | planned |
| A14 | Rule with invalid regex, > 200 chars, or no condition | 422 | api/analyst.py | test_rule_versioning_and_tester | planned |
| A15 | Second dataset job while one runs | 409; a dead worker's job becomes FAILED | jobs/runner.py | test_admin_job_lifecycle | planned |
| A16 | Export path traversal (`..%2F`) | 400/404 | api/admin.py | test_export_path_traversal_blocked | planned |
| A17 | Admin demotes/disables themself | 409 | api/admin.py | test_admin_cannot_demote_self | planned |
| A18 | Dataset reload | App users survive (soft profile reference, no FK cascade) | jobs/load.py | test_reload_keeps_app_users | done |
| A19 | Algorithm confusion: HS256 token signed with Google's public certificate, or `alg: none` | Algorithm pinned per token kind (HS256 local, RS256 Firebase); anything else rejected | security.py | test_security::test_algorithm_confusion_rejected | done |
| A20 | Login probing for which emails exist | Unknown email still runs an argon2 verify against a dummy hash; same 401 message | security.py, api/auth.py | test_security::test_passwords | done |
| A21 | Phone or server clock skew; Firebase `auth_time` in the future | 30 s leeway on exp/iat; future `auth_time` rejected | security.py | test_security::test_firebase_bad_claims_rejected | done |
| A22 | Google certificate endpoint unreachable | Cached keys reused until refreshed (cache honours `max-age`); with no keys at all → 503, not 401 | security.py | test_security::test_cert_cache_max_age | done |
| A23 | First Google sign-in by someone with no invite | Admin emails (config) → ADMIN; others → CUSTOMER linked to the first unclaimed household so the demo has data (synthetic data only; a real deployment would invite instead) | api/auth.py | test_auth::test_google_signup_link_and_conflicts | done |
| A24 | Google email already used by a demo/invited login | Linked to that login (no duplicate); a different Google uid for the same email → 409 | api/auth.py | test_auth::test_google_signup_link_and_conflicts | done |
| A25 | Google account with an unverified email | 403, never matched to an existing login by email | api/auth.py | test_auth::test_google_signup_link_and_conflicts | done |
| A26 | Password guessing | 5 failures per email in 15 min → 429 with minutes to wait (per process) | api/auth.py | test_auth::test_lockout_after_repeated_failures | done |
| A27 | Unhandled server error | problem+json 500 with request id; no exception text leaks | api/errors.py | test_auth::test_unhandled_error_is_generic_500 | done |
| A28 | Joint account (second holder) | Its transactions are visible to both holders; totals and budgets count them for the owner's household only, like the engine (no double counting) | api/me.py | test_me::test_transactions_keyset_pagination_and_isolation | done |
| A29 | Override made after the latest run | Shown at once in lists, detail, budgets and summary (latest override applied on read); the next run bakes it in | api/common.py EFFECTIVE | test_me::test_override_changes_budget_actual_immediately | done |
| A30 | Customer fixes an uncategorized txn | Open UNCATEGORIZED exception closes with an event naming the override | api/me.py | test_me::test_override_resolves_uncategorized_exception | done |
| A31 | Staff opens a customer page | ANALYST/REVIEWER 403; ADMIN must name `?user_id=` (support view), unknown id 404 | api/common.py | test_me::test_roles_and_admin_support_view | done |
| A32 | Login not linked to a household | 409 asking an admin to link it | api/common.py | (covered by household()) | done |

## Web console (U)

| ID | Scenario | Expected handling | Where | Test | Status |
|---|---|---|---|---|---|
| U01 | Loading / empty / error states | Skeleton matching layout, empty guidance, error + Retry on every query | QueryState.tsx | a11y.test.tsx + manual | planned |
| U02 | Very long descriptors | Truncate with tooltip, full text in drawer | DataTable.tsx | manual + screenshot | planned |
| U03 | Crore-scale amounts | `₹1,00,00,000.00` grouping, tabular numerals | money.ts | money.test.ts | planned |
| U04 | Debit vs credit shown by color only | Sign and screen-reader text in addition to color | Amount component | a11y.test.tsx | planned |
| U05 | Session expires mid-use | 401 → logout → login page with "Session expired" | api.ts, auth.tsx | manual | planned |
| U06 | Firebase not configured | Google button hidden, demo login only | firebase.ts | manual | planned |
| U07 | Rapid filter typing | 300 ms debounce; stale responses ignored by query keys | Transactions.tsx | manual | planned |
| U08 | Double-click on submit | Button disabled while pending | dialogs | manual | planned |
| U09 | Someone else changed the exception first | 409 → toast + refetch | Exceptions.tsx | manual | planned |
| U10 | Reduced motion / dark mode / keyboard only | Respected / themed / fully operable | tokens.css, AppShell | a11y.test.tsx, Lighthouse | planned |
| U11 | localStorage blocked (private mode) | Theme falls back to system, no crash | theme code | manual | planned |

## Android app (M)

| ID | Scenario | Expected handling | Where | Test | Status |
|---|---|---|---|---|---|
| M01 | No `google-services.json` | Firebase disabled, demo login only | auth_controller.dart | manual | planned |
| M02 | Non-customer signs in | Message + sign-out | auth_controller.dart | manual | planned |
| M03 | Offline / timeout | Error view with Retry; cached month data still shown | async_view.dart | manual | planned |
| M04 | Token expired | Back to login | client.dart | manual | planned |
| M05 | 130% text scale, dark mode | No overflow, readable | screens | home_golden_test.dart | planned |
| M06 | Category changed by mistake | Undo in snackbar restores previous category | txn_detail_sheet.dart | manual | planned |
