PAM - COMPLETE FEATURE LIST

Generated 2026-11-05 from the code of github.com/vbs-0/pam at commit 577cd28, not from its docs.

Every item was read out of source files; file:line evidence is given in parentheses where non-obvious.

Surfaces: backend (FastAPI + Postgres), web console (React), Android app (Flutter), data/QA/infra.



# BACKEND - FastAPI API, engine, data generator, validation, security, jobs

## API — auth & accounts
1. `POST /api/v1/auth/login` exchanges email+password for a PAM JWT, clearing the failure window on success (`app/api/auth.py:101`).
2. Login throttling: 5 failed attempts per email per 900 s → HTTP 429 with minutes-remaining text (`app/api/auth.py:31`, `:68`).
3. Uniform "email or password is wrong" response and constant-ish argon2 cost for unknown users via a dummy hash (`app/api/auth.py:107`, `app/security.py:40`).
4. Disabled logins get 403 at login and on every request (`app/api/auth.py:110`, `app/api/deps.py:30`).
5. `POST /auth/register` creates a new empty household + CUSTOMER login, rate-limited to 5 sign-ups/hour per client IP (`app/api/auth.py:120`).
6. Registration is gated by `ALLOW_SIGNUP` config (403 when closed) and takes a `pg_advisory_xact_lock('app_user')` to prevent duplicate-email races (`app/api/auth.py:124`, `:134`).
7. `POST /auth/forgot` always returns the same 202 body (no account enumeration) and emails a 30-minute single-use reset link (`app/api/auth.py:150`, `app/security.py:68`).
8. Forgot-password has two separate rate limits: 3 per hour per email and 10 per hour per IP (`app/api/auth.py:158`).
9. `POST /auth/reset` verifies the token's password-hash fingerprint, locks the row `FOR UPDATE`, re-hashes, audits `PASSWORD_RESET`, and mails a security notice (`app/api/auth.py:174`).
10. `POST /auth/firebase` verifies a Firebase RS256 ID token and exchanges it for a PAM token; requires verified email (`app/api/auth.py:193`).
11. Firebase first sign-in auto-links an existing invited/demo login by email, and drops the password of a self-registered (unverified) household so the verified Google owner takes over (`app/api/auth.py:205`).
12. New Google users in `ADMIN_EMAILS` become ADMIN; everyone else gets their own empty household (`app/api/auth.py:221`).
13. `GET /auth/me` returns the caller's live identity (app_user_id, email, role, profile_user_id) (`app/api/auth.py:233`).
14. `POST /auth/change-password` requires the current password (400, not 401, on wrong), forbids reusing it (422), and issues a fresh token for this device (`app/api/auth.py:265`).
15. `POST /auth/change-email` re-verifies the password, blocks collisions, and notifies the old address (`app/api/auth.py:285`).
16. `POST /auth/delete-account` requires exact email confirmation plus password, deletes the household only when no other login shares it, and refuses demo/sample/staff logins (`app/api/auth.py:307`).
17. Mobile clients (`X-PAM-Client: mobile`) get a 30-day token TTL; web console gets 7 days (`app/config.py:13`, `app/api/auth.py:91`).
18. `GET /healthz` liveness probe; `GET /readyz` executes `SELECT 1` against Postgres (`app/main.py:50`, `:54`).

## API — customer reads
19. `GET /categories` lists the whole taxonomy with group, kind, active flag and successor code (`app/api/me.py:46`).
20. `GET /me/accounts` returns held accounts (joint included) with computed balance = opening + Σ txns, holder role, shared-from-other-household flag and a human `display_name` (`app/api/me.py:54`, `:70`).
21. `GET /me/transactions` is cursor-paginated (`next_cursor` = base64 of `(local_date, txn_id)`, one extra row fetched) rather than offset (`app/api/me.py:80`, `app/api/common.py:47`).
22. Its filters: `month` (regex-validated `YYYY-MM`), `category`, `account_id`, `kind`, `q` (ILIKE on descriptor/merchant with `\ % _` escaping), `date_from`, `date_to`, `min_paise`/`max_paise` on absolute amount, `merchant`, `tag`, `limit` 1–100 default 50 (`app/api/me.py:81`, `app/api/common.py:13`, `:68`).
23. Each list row carries note and tags attached in one batched query (`app/api/me.py:127`).
24. Visibility rule: transactions on every account the household *holds*, but totals/budgets count only rows owned by the household (`app/api/me.py:1`, `docs A28`).
25. `GET /me/transactions/{id}` adds reference_no, link_txn_id, series_id, rule_id, rule_version and the full override history; another household's id looks exactly like a 404 (`app/api/me.py:144`, `:136`).
26. All reads are served from the latest `SUCCEEDED` run; if none exists the API returns 409 with an admin hint (`app/api/common.py:16`).
27. `EFFECTIVE` SQL view applies the latest human override on top of the run's decision, re-deriving kind, so a post-run override shows immediately (`app/api/common.py:74`).
28. `GET /me/budgets` returns per-category budget/actual/ratio/status, carried amounts, source budget ids, `remapped` and `unmapped` lists, plus totals and the carry-enabled category set (`app/api/me.py:251`).
29. `GET /me/summary` returns income, spend, `naive_spend_paise`, `transfers_out_paise`, savings rate (None with zero income), top-5 categories, over/near-budget counts (`app/api/me.py:273`).
30. `GET /me/trend?months=1..36` returns oldest-first monthly spend/income under the same kind rules (`app/api/me.py:291`).
31. `GET /me/recurring` returns per-run series state with merchant name, counterparty key, direction and the last 12 lifecycle events (`app/api/me.py:305`).
32. `GET /me/insights` filters by month and sorts ALERT→WARN→INFO (`app/api/me.py:328`).

## API — customer writes
33. `POST /me/transactions/{id}/category` records an override with optional reason and validates the code against the date (`app/api/me.py:199`).
34. `remember: true` also creates a household "remember my choice" rule and retro-sorts other unsorted entries in the same call (`app/api/me.py:208`).
35. Override validation rejects UNKNOWN categories and codes not active on the transaction's date, suggesting `replaced_by` (`app/api/me.py:167`).
36. Every override auto-resolves open UNCATEGORIZED exception cases, appends an `exception_event` and audits `CATEGORY_OVERRIDE` (`app/api/me.py:179`).
37. Sample (synthetic) households are read-only for all writes via `own()` → 403 (`app/api/entry.py:26`).
38. `GET/PATCH /me/profile` with validation (state `^[A-Z]{2}$`, persona enum, household_size 1–20, income cap) and automatic `income_band` derivation (LOW/MID/HIGH/AFFLUENT at ₹25k/₹75k/₹2L) (`app/api/entry.py:46`, `:55`).
39. `POST /me/accounts` enforces: UPI-app vs bank-type cross rules, custom UPI app needs a label, no future open date, credit limit only on cards, unique VPA, max 99 accounts, deterministic id `ACC-<user>-NN`, masked number format (`app/api/entry.py:105`).
40. Account creation writes an `OPENED` account_event using a reserved `AEV-9xxxxx` range so dataset reloads never collide (`app/api/entry.py:142`).
41. `POST /me/accounts/{id}/close` validates the closing date against open date, last posting and today, then refreshes the household (`app/api/entry.py:155`).
42. `PATCH /me/accounts/{id}` edits label, credit limit, VPA, due/statement day, and a "real balance today" that rewrites the opening balance (`app/api/me_plus.py:49`, `:99`).
43. `POST /me/transactions` accepts date + optional IST wall-clock time (noon default), positive amount plus explicit DR/CR direction, and returns the engine's decision inline (`app/api/entry.py:183`, `:241`).
44. Duplicate detection: same account + amount + case-insensitive description + same IST day is reported as `possible_duplicate_of` but still saved (`app/api/entry.py:248`, `:261`).
45. `PATCH /me/transactions/{id}` edits fields, refuses cross-year moves, and audits before/after (`app/api/entry.py:278`).
46. `DELETE /me/transactions/{id}` purges enrichment, overrides, notes, exception events/cases, nulls inbound links, and re-decides the pair/refund (`app/api/entry.py:303`, `:317`).
47. `PUT /me/budgets` allows zero ("plan to spend nothing"), only active EXPENSE categories, and creates a new immutable `version` each time (`app/api/entry.py:335`).
48. `DELETE /me/budgets/{month}/{code}` removes resolutions, exception cases and events, rolling back when the budget is absent (`app/api/entry.py:354`).
49. `PUT /me/transactions/{id}/note` stores note + up to 8 normalized tags (lowercased, `#` stripped, regex-checked, de-duplicated) and deletes the row when both are empty (`app/api/entries_plus.py:54`, `:76`).
50. `GET /me/tags` returns every tag used with counts, most-used first (`app/api/entries_plus.py:93`).
51. `POST /me/transactions/{id}/split` replaces one entry with 2–10 parts that must sum exactly to the original, keeping sign, account, channel and VPA, and labeling each `(split i/n)` (`app/api/entries_plus.py:136`).
52. `POST /me/transactions/{id}/duplicate` copies an entry to another date (today default) carrying its latest category (`app/api/entries_plus.py:182`).
53. `POST /me/transfers` writes the two bank-shaped legs with a shared random `TRF########` reference so the engine pairs them as a transfer (`app/api/entries_plus.py:233`).
54. `POST /me/import/preview` returns detected headers, an auto-suggested column mapping, row count and a 5-row sample (`app/api/entries_plus.py:365`).
55. CSV import auto-detects delimiter (`,;\t|`), strips BOM, skips bank title lines by finding the first row naming a date column, and suggests mappings from 6 field hints (`app/api/entries_plus.py:300`, `:290`).
56. Import understands 10 date formats, ₹/Rs./INR/千 separators, parenthesized and `DR`-suffixed negatives, debit/credit columns or amount + `type` column, and an explicit `date_format` override (`app/api/entries_plus.py:278`, `:337`, `:351`, `:427`).
57. Import caps at 5000 rows and 2,000,000 characters, supports `dry_run`, and returns rows_total / to_import / skipped_duplicates / error_count / errors (max 50, with row numbers) (`app/api/entries_plus.py:49`, `:386`).
58. Import is idempotent per file: rows matching existing (date, amount, narration) are counted as skipped duplicates, with multiplicity (`app/api/entries_plus.py:410`, `:446`).
59. Import inserts in one batched `COPY`-style executemany and re-runs the household plus user sorting rules afterwards (`app/api/entries_plus.py:482`, `:493`).
60. `GET /me/export.csv` downloads the register as UTF-8-with-BOM CSV (12 columns, debit/credit split) with `date_from`/`date_to`/`account_id` filters (`app/api/entries_plus.py:507`).
61. Export guards against CSV formula injection by prefixing cells starting with `= + - @ tab CR` (unless numeric) (`app/api/entries_plus.py:502`).
62. `GET /me/backup.json` downloads a `pam-backup/1` document: profile, accounts (incl. card due/statement days), transactions with latest category/note/tags, latest budget versions, goals, carry list (`app/api/entries_plus.py:580`).
63. `POST /me/restore` loads a backup only into an empty register, re-issues all ids, restores account meta/closed status, notes, goals, budgets (through the normal validated setter) and carry flags (`app/api/entries_plus.py:627`).
64. Restore tolerates categories retired since the backup by letting PAM re-categorize the row (`app/api/entries_plus.py:690`).
65. `POST /me/goals`, `GET /me/goals`, `PATCH`, `POST /contribute` (positive or negative, clamped at 0), `DELETE` with progress, days-left and `monthly_needed_paise` computed server-side (`app/api/me_plus.py:165`–`:249`).
66. Goal limits: max 30 goals, future deadline required, auto-`completed_at` when saved ≥ target (`app/api/me_plus.py:186`, `:236`).
67. `PUT /me/budgets/carry` toggles per-category rollover on/off, EXPENSE categories only (`app/api/me_plus.py:258`).
68. `GET/PUT /me/notifications` stores per-login digest opt-in plus bills/budgets/cards category switches (`app/api/me_plus.py:283`).
69. Household sharing: `GET /me/household/members` lists members, identifies the owner (first created) and shows live unused invite codes (`app/api/me_plus.py:323`).
70. `POST /me/household/invite` issues an 8-char one-time code from a 0/O/1/I-free alphabet, valid 3 days, max 5 unused and max 6 logins per household (`app/api/me_plus.py:359`, `:314`).
71. `POST /me/household/join` accepts a code (case/space/dash insensitive), locks it, and only lets a login in while its own register is empty (`app/api/me_plus.py:393`).
72. `POST /me/household/leave` and `DELETE /me/household/members/{id}` move a login into a fresh empty household; only the owner may remove someone (`app/api/me_plus.py:431`, `:442`).
73. `GET /me/sorting-rules` and `DELETE /me/sorting-rules/{id}` — deleting a rule leaves already-sorted entries alone (`app/api/sorting.py:74`, `:83`).
74. `GET /me/ai` reports AI availability, per-household enablement, provider, and a plain-language disclosure of exactly what text is sent (`app/api/sorting.py:102`).
75. `PUT /me/ai` toggles AI sorting for the household (`app/api/sorting.py:111`).
76. `POST /me/sort`-style `POST /me/ai/sort` asks Gemini about up to 40 unsorted entries per call, de-duplicates by masked text+direction+channel, and applies only confident answers as overrides actor `AI:gemini` (`app/api/sorting.py:119`).
77. AI call budget: 6 per household per hour, enforced from the audit log (429) (`app/api/sorting.py:127`).
78. AI suggestions are accepted only at confidence ≥ 0.6 and only when the category's kind matches the direction (DR→EXPENSE, CR→INCOME) (`app/api/sorting.py:165`).

## API — analytics
79. `GET /me/daily?month=` returns a full calendar month (empty days included) plus total, busiest day, daily average over elapsed days, and days left (`app/api/analytics.py:30`).
80. `GET /me/spend-by-category` adds month-on-month change and share, including categories spent last month but not this one (`app/api/analytics.py:80`, `:117`).
81. `GET /me/merchants?months=1..36&limit=1..50` ranks payees by spend with count and last payment date (`app/api/analytics.py:139`).
82. `GET /me/weekday` reports Monday-first totals, distinct days seen, entry counts and average per day (`app/api/analytics.py:175`).
83. `GET /me/upcoming?days=1..90` merges expected recurring items (ACTIVE or MISSED) with credit-card due dates, sorted by date, with overdue flags and due-in/due-out totals (`app/api/analytics.py:206`).
84. Card due day is projected forward with clamping for short months (`app/api/analytics.py:265`).
85. `GET /me/networth` splits assets vs liabilities across active accounts and returns per-card limit, used, available, utilisation and days-to-due (`app/api/analytics.py:311`).
86. `GET /me/alerts` produces 7 typed alerts — BILL_OVERDUE, BILL_DUE (≤3 days), BUDGET_OVER, BUDGET_NEAR, CARD_DUE (≤5 days), CARD_LIMIT (≥80% utilisation), GOAL_REACHED (last 7 days) — severity-sorted (`app/api/analytics.py:343`).

## API — analyst / reviewer / admin
87. `GET /analyst/exceptions` filters by `type`, `status`, `user_id`, id cursor and limit, and flags `current` = still raised by the latest run (`app/api/analyst.py:32`, `:57`).
88. `GET /analyst/exceptions/counts` gives a type × status histogram (`app/api/analyst.py:62`).
89. Exception workflow permits exactly: OPEN→IN_REVIEW/RESOLVED/DISMISSED, IN_REVIEW→RESOLVED/DISMISSED/OPEN, RESOLVED→OPEN, DISMISSED→OPEN (`app/api/analyst.py:22`).
90. Transitions use optimistic concurrency (status-guarded UPDATE; 409 "someone else changed this"), write an `exception_event` with next `seq`, and can resolve a TXN exception by setting a category in the same call (`app/api/analyst.py:86`, `:93`).
91. `GET /analyst/rules` returns the latest version per rule in evaluation order, with `include_retired` toggle (`app/api/analyst.py:153`).
92. Rule authoring accepts priority 1–999, category, merchant_id, regex pattern, channel, direction DR/CR/ANY, account_type, confidence 0–1, and a note (`app/api/analyst.py:108`).
93. Rule validation: at least one condition required, category must be an active non-UNKNOWN code, merchant must exist (`app/api/analyst.py:133`).
94. ReDoS guard: patterns are compiled and rejected when a nested quantifier like `(a+)+` or `(a|aa)*` is detected (`app/api/analyst.py:24`, `:128`).
95. `POST /analyst/rules/{id}/versions` never edits in place: it retires the current version and appends version+1 (`app/api/analyst.py:175`).
96. `POST /analyst/rules/{id}/retire` retires all unretired versions (`app/api/analyst.py:194`).
97. `POST /analyst/rules/test` dry-runs the whole active rule set on a single narration and returns normalized descriptor, merchant, rule id+version, category, confidence, without saving (`app/api/analyst.py:213`).
98. `GET /analyst/metrics` returns stored evaluation metrics (latest or by `run_id`) (`app/api/analyst.py:232`).
99. `GET /analyst/runs` lists the last 50 pipeline runs with status, timings, ruleset hash, stats and error (`app/api/analyst.py:243`).
100. `GET /ops/transactions/{id}` full trace: raw txn + account info, current effective decision, every run's enrichment, override history, exception cases with event chains (`app/api/analyst.py:250`).
101. Ground truth (`gt.txn_label`) is appended to the trace only for REVIEWER/ADMIN, never ANALYST or CUSTOMER (`app/api/analyst.py:276`).
102. `GET /review/anomalies` joins labelled anomalies to per-run CAUGHT/MISSED outcomes, filterable by `issue_type`, `outcome`, `run_id` (`app/api/review.py:21`).
103. `GET /review/summary` gives recall per issue type plus threshold results for the evaluated run (`app/api/review.py:35`).
104. `GET /review/audit` pages the audit log by entity type/id/actor/action with an id cursor (`app/api/review.py:49`).
105. `GET /admin/overview` reports last dataset load, latest run, evaluation headline, six population counts (incl. real households by id range) and running jobs (`app/api/admin.py:26`).
106. `POST /admin/jobs` starts GENERATE_LOAD / PIPELINE / EVALUATE / VALIDATE / EXPORT / REPRO with a ≤500-byte JSON params cap; 409 vs 422 depending on rejection reason (`app/api/admin.py:44`).
107. `GET /admin/jobs` (cursor + limit) and `GET /admin/jobs/{id}` expose job state, timings, result and error (`app/api/admin.py:63`, `:73`).
108. `GET /admin/validation?scope=DATASET|OUTPUTS` returns the latest stored validation run (`app/api/admin.py:81`).
109. `GET /admin/reproducibility?scale=` prefers a SUCCEEDED REPRO job and otherwise falls back to the committed CLI evidence file `reports/<scale>/repro-<scale>.json` (`app/api/admin.py:91`).
110. `GET /admin/exports/{scale}` returns the dataset manifest plus a computed download list (manifest files + `seed.sql` + `json/*.json`) (`app/api/admin.py:114`).
111. `GET /admin/exports/{scale}/files/{path}` serves only manifest-listed/allow-listed files, resolves the path and rejects anything escaping the scale directory (`app/api/admin.py:123`).
112. `GET /admin/users` filters by email LIKE (escaped), role and id cursor, and reveals only *whether* a Google/password login exists (`app/api/admin.py:137`).
113. `PATCH /admin/users/{id}` changes role/household/disabled with guards: no self-demotion or self-disable, household must exist, CUSTOMER must have a household, and the last active admin cannot be demoted or disabled (`app/api/admin.py:159`).

## Engine
114. The pipeline is a pure function of its input (categorize → overrides → reversals/refunds → transfers → recurring → budgets → insights → exceptions) and never touches the DB or ground truth (`app/engine/pipeline.py:1`, `app/engine/types.py:1`).
115. Categorization tier order: rules sorted by (priority, rule_id), first rule with all non-null conditions satisfied wins; VPA-registered merchant beats any text, then longest alias (`app/engine/categorize.py:28`, `:38`).
116. Alias matching uses a word-boundary alternation compiled longest-first so "amazon fresh" beats "amazon" (`app/engine/categorize.py:32`).
117. Decision cache keyed on (normalized descriptor, VPA, channel, direction, account type) with a hit counter exposed in run stats (`app/engine/categorize.py:45`).
118. Descriptor normalization strips card masks, IFSC codes, 6+-digit references and punctuation, lower-cases and re-squeezes whitespace (`app/engine/normalize.py:12`).
119. `strip_variable` additionally drops month names and numbers so recurring occurrences group (`app/engine/normalize.py:22`).
120. Payments to the household's own registered VPA are forced to SELF_TRANSFER at 0.99 with decision `OWN_VPA`, before any rule runs (`app/engine/pipeline.py:65`).
121. Human overrides win over rules (decision `OVERRIDE:<id>`, confidence 1.0, `locked=True`) and clear rule attribution (`app/engine/pipeline.py:72`).
122. Kind is derived from category kind + sign: an EXPENSE-category credit becomes a REFUND (`app/engine/types.py:52`).
123. Reversal linkage: same account + same RRN + exactly opposite amount + credit after debit, in first pass, marks both legs REVERSAL with decision `UPI_REVERSAL` (`app/engine/refunds.py:13`).
124. Refund netting: candidate purchases are same user + merchant (or refund-worded narration), within a 90-day window, prefer exact unrefunded remainder, then same account, then latest gap (`app/engine/refunds.py:27`–`:47`).
125. Partial refunds decrement a running `remaining` balance per purchase, so one purchase can absorb several credits (`app/engine/refunds.py:35`, `:50`).
126. Over-refunds / unmatched credits become `REFUND_ORPHAN`; if their category isn't an EXPENSE bucket they are reset to UNCATEGORIZED (`app/engine/refunds.py:53`).
127. Refund words recognized: refund, rfnd, reversal, rvsl, rev (`app/engine/refunds.py:8`).
128. Transfer pairing: same user, different accounts, exactly equal |amount|, credit within [-1, +3] days of the debit, greedy by smallest gap with each leg used once, so duplicate transfers pair one-to-one (`app/engine/transfers.py:10`).
129. Paired legs become CC_BILL_PAYMENT when either side is a credit card, else SELF_TRANSFER, decision `TRANSFER_PAIR`, rule `SYS-PAIR`, confidence floored at 0.95 (`app/engine/transfers.py:42`).
130. Transfer candidates exclude already-locked rows and reversals/refunds (`app/engine/transfers.py:19`).
131. Recurring grouping key = (user, counterparty key, direction), where the counterparty key itself includes account, merchant-or-VPA-or-descriptor, category and channel, so one merchant can hold two independent series (`app/engine/recurring.py:39`, `:54`).
132. Recurring gates: ≥3 members; median gap in 25–35 (MONTHLY) or 80–100 (QUARTERLY) days else rejected; no gap below 0.5× median; ≥70% of gaps within 0.6–1.4× median; ≥80% of consecutive amount pairs within tolerance (`app/engine/recurring.py:65`–`:79`).
133. Amount tolerance by category: UTILITIES 60%, INTEREST unlimited, default 15% (`app/engine/recurring.py:17`).
134. Series events emitted: DETECTED, AMOUNT_CHANGED (single >5% move on non-variable categories), MISSED (one per skipped cycle when a gap ≥1.6× median), RESUMED, ENDED (`app/engine/recurring.py:81`–`:100`).
135. Status rules: ENDED when the account closed (with reason) or nothing seen for >2.5× median; MISSED when >1.6× median; else ACTIVE, with `next_expected` cleared on ENDED (`app/engine/recurring.py:90`).
136. Series type is mapped from the category (SALARY/RENT/SUBSCRIPTION/EMI/UTILITY/INTEREST) with rent inference: uncategorized monthly DR with median ≥ ₹5,000 and no locked rows becomes RENT at confidence 0.7 via `SYS-RECUR-RENT` (`app/engine/recurring.py:15`, `:104`).
137. Typical amount = median of the last three occurrences (`app/engine/recurring.py:118`).
138. Budget category resolution ladder: VALID → REMAPPED_RETIRED (via successor) → REMAPPED_CASE (upper/underscore normalization) → REMAPPED_SYNONYM → UNMAPPED; targets must be active EXPENSE categories, so income/transfer budgets are unmapped (`app/engine/budgets.py:43`).
139. Only the highest version of each budget id is effective; earlier versions remain as history (`app/engine/budgets.py:70`).
140. Cash-basis spend: refunds reduce the bucket in the month they arrive, uncategorized debits count, transfers and reversals never do (`app/engine/budgets.py:85`).
141. Budget status thresholds: OVER >1.0, NEAR ≥0.8, UNDER otherwise, NO_BUDGET when unset; a zero budget is OVER on any spend (`app/engine/budgets.py:103`).
142. Budgets resolving to the same category are summed into one line, keeping all source budget ids (`app/engine/budgets.py:112`).
143. Rollover/carry is applied at read time: last month's unspent limit is added to opted-in categories as synthetic `CARRY-<code>` lines (`app/api/me.py:230`).
144. Insight types: OVER_BUDGET, NEAR_BUDGET, UNMAPPED_BUDGET, SPEND_SPIKE, LOW_SAVINGS, NEW_RECURRING, RECURRING_MISSED, RECURRING_PRICE_CHANGE, each with severity, metric, baseline and evidence ids (`app/engine/insights.py:44`–`:106`, `app/schema.py:49`).
145. Spend spike rule: ≥1.5× the trailing 3-month mean AND at least ₹2,000 above it, requiring three prior full months (`app/engine/insights.py:9`, `:66`).
146. Low-savings rule: savings rate below 10%, with a distinct message for "spent more than came in", and skipped entirely when income is zero (`app/engine/insights.py:76`).
147. Insight prose renders whole-rupee amounts through Indian grouping while data stays in paise (`app/engine/insights.py:26`, `app/money.py:1`).
148. Exception types raised by the engine: UNCATEGORIZED, UNMATCHED_TRANSFER, ORPHAN_REFUND, BUDGET_CATEGORY_UNMAPPED, RECURRING_MISSED; locked (override) rows raise nothing (`app/engine/pipeline.py:93`).
149. Business dates are bucketed in the household's IANA timezone (default Asia/Kolkata) from UTC storage, with a naive-timestamp guard (`app/engine/pipeline.py:63`, `app/timeutil.py:16`).
150. IST conversion helpers: fixed +05:30 offset for bulk work, cached `ZoneInfo`, month start/end, `add_months`, ISO `YYYY-MM` keys, and `Z`-timestamp parse/format (`app/timeutil.py:8`–`:58`).
151. Money is signed integer paise end to end, with a zero-amount check constraint (`app/schema.py:210`).

## Data generation
152. Two scales: `starter` (50 households / 25,000 txns) and `full` (1,000 / 500,000), overridable with explicit `--users`/`--transactions` (`app/datagen/generator.py:23`, `app/cli.py:17`).
153. Default seed 20261022, settable per run; year is pinned to 2026 because holidays and seasonality only cover it (`app/cli.py:204`, `app/datagen/generator.py:89`).
154. Exact volume is guaranteed by removing or adding standalone savings-UPI purchases from an "adjustable" pool, then asserting the count (`app/datagen/generator.py:56`, `:127`).
155. Per-user RNG streams (`<seed>:<USR-xxxxxx>:…`) plus named global streams, so adding households never changes existing rows (`app/datagen/people.py:82`, `app/datagen/anomalies.py:41`).
156. Deterministic RNG built only on `random.random()` (uniform/randint/choice/weighted/normal/lognormal/shuffle/sample) for cross-version checksum stability (`app/datagen/rand.py:5`).
157. Household profiles draw persona, city+tier, income band, income, household size 1–6, renter flag, name from Indian first/last name pools, and a pre-2026 created_on (`app/datagen/people.py:80`).
158. Account mix: primary savings always, secondary at 40%, credit card at 45% (75% for HIGH/AFFLUENT) with limit = 3× income floored at ₹50k; UPI ids `usr######.nn@<bank-handle>` (`app/datagen/people.py:96`–`:110`).
159. Population-level guarantees with a minimum of one: 3% secondary accounts close mid-year, 10% cards open in 2026, 5% of open secondaries get a same-city JOINT holder (`app/datagen/people.py:120`).
160. Bank working-day rules: Sundays, 2nd/4th Saturdays (RBI) and 2026 national holidays are closed; helpers for last/next working day and day clamping (`app/datagen/calendar.py:8`).
161. Recurring plans: salary (last working day, 15% get a 5–15% mid-year hike), pension (1st working day), rent (day 1–7, 40% with no "rent" hint, 15% rent bump), 0–4 subscriptions with price changes and early cancellations, EMI via NACH, electricity with state-specific biller and seasonality, broadband, 28-day mobile packs (13/year), DTH (`app/datagen/schedules.py:71`–`:179`).
162. Truth series only cover plans with ≥3 live occurrences, and are numbered `TRS-######` in sorted plan order (`app/datagen/generator.py:133`).
163. Discretionary spending uses persona × category weights, per-category seasonality, weekday weighting (Sat/Sun ×1.3), hour-of-day curves (food vs shop hours), income-band multipliers, lognormal amounts, and a Zipf-weighted merchant pool per category (`app/datagen/spending.py:199` via catalog, `:54`, `:92`, `:106`).
164. Channel choice per purchase: online merchants on card 45%, else UPI (70% to the round-rupee amount), else POS/cash; secondary savings used 15% of the time (`app/datagen/spending.py:136`).
165. 65 real-brand merchants with ids, canonical names, alias/typo sets, synthetic `-mrch` UPI handles, online flag, mean amount and sigma, extra categories, and regex sub-business refinements (Swiggy Instamart → GROCERIES, Amazon Fresh/Prime) (`app/datagen/catalog.py:83`).
166. 24 categories across 5 groups, 2 retired with successors, 5 synonyms, 3 unknown budget codes and 3 remap variant sets (`app/datagen/catalog.py:24`–`:56`).
167. Long-tail local shops deliberately outside the merchant master: 14 prefixes × 12 suffixes, with ENTERPRISES/TRADERS genuinely ambiguous so no rule can be right every time (`app/datagen/catalog.py:161`).
168. Seed rule set has 8 priority bands (5 system keywords, 6 ATM/NACH, 10 merchant refinements, 50 merchant defaults, 60 rent keyword, 90 shop keywords, 95 income fallbacks) with per-rule confidence and note (`app/datagen/catalog.py:222`).
169. Bank-shaped narrators: UPI (DR/CR/REV), NEFT with IFSC, IMPS P2A/CR, NACH EMI, BBPS, POS with masked card, ECOM with REFUND/RECURRING tags, ATM WDL, INT.PD date ranges, CC BILL PAY, PAYMENT RECEIVED (`app/datagen/descriptors.py:25`–`:80`).
170. RRNs are 12-digit and unique by construction: `key × coprime + seed mod 10^11` is a bijection (`app/datagen/descriptors.py:11`).
171. Six labelled anomaly families injected at per-household rates: TRANSFER_DOUBLE_COUNT 0.4, REFUND_AS_EXPENSE 0.5, RECURRING_SKIP 0.12, RECURRING_NOT_SKIP 0.24, TZ_BOUNDARY 0.4, BUDGET_REMAP 0.15, BUDGET_UNKNOWN 0.05 (`app/datagen/anomalies.py:19`).
172. Transfer anomaly rewrites a self transfer into a UPI "Payment" pair (20% via CRED card bill) with the credit 1–3 days late (`app/datagen/anomalies.py:78`).
173. Refund anomaly strips all refund wording from a linked merchant credit so only linkage arithmetic can find it (`app/datagen/anomalies.py:109`).
174. Timezone anomaly moves a discretionary transaction to 00:00–05:29 IST on the 1st, where the UTC month differs (`app/datagen/anomalies.py:127`).
175. Skip/decoy anomalies alter plan occurrences before materialization: a true skip in the middle band, a decoy delayed 2–4 days (`app/datagen/anomalies.py:45`).
176. Budget anomalies submit retired/case/synonym variants and codes outside the taxonomy, each with the expected decision (`app/datagen/anomalies.py:147`).
177. Self transfers 1–3/month per household in ₹500 steps with IMPS SELF narrations; card statements paid day 3–7 of the next month (December unpaid), 60% IMPS vs 40% UPI-via-CRED (`app/datagen/ledger.py:32`, `:54`).
178. Derived opening balances keep savings accounts solvent (≥₹1,000 floor); quarterly savings interest at 3% p.a. on end-of-day balances, min ₹1, none in the closing quarter; closure sweeps the balance to zero with a paired transfer (`app/datagen/ledger.py:105`–`:159`).
179. Budgets are sized from each household's own true spend (±25%), in ₹500 steps, 6 base + rent + optional categories, ~5% of households keep none, 8% get a mid-month v2 revision (`app/datagen/budgets.py:29`).
180. Extras: self-employed irregular client income (NEFT/IMPS, deliberately not a series), annual insurance premiums, and January orphan refunds for 2025 orders (`app/datagen/spending.py:209`).
181. Same-day duplicate purchases are injected once per household at 5% and are marked non-adjustable (`app/datagen/spending.py:90`, `:159`).
182. Id formats are fixed: USR-######, ACC-USR-######-NN, TXN-YYYY-########, BUD-user-month-code, REC/TRS/ANM/AEV/RUL/MER/OVR/EXC/VAL/DSL/JOB/RUN/INS sequences, validated by a pattern table (`app/ids.py:34`).
183. Monthly balance rows are derived per account per IST month from the ledger (`app/datagen/generator.py:152`).
184. Outputs: per-table CSVs (canonical, LF, header = schema order, NULL = empty field, `Z` timestamps), typed JSON arrays per table, a self-contained `seed.sql` (DDL + indexes + `COPY FROM stdin`), `manifest.json` with per-file rows and sha256 and no timestamps, and `provenance.json` (`app/datagen/writer.py:53`–`:139`).
185. Provenance records: synthetic-only declaration and statement, a combined SHA-256 over all generator + schema + ids sources, git commit and generator-tree cleanliness, Python version and platform, `uv.lock` hash, the exact command line, manifest hash, export checksums, and a "do not edit" note (`app/datagen/writer.py:160`).
186. Reproducibility check regenerates and exports twice in two fresh interpreter subprocesses with `PYTHONHASHSEED` 1 and 2 and compares manifest bytes plus every export checksum (`app/datagen/writer.py:187`).

## Validation
187. 22 dataset checks run over the written files: columns, pk_unique, fk_integrity, enums, id_formats, date_order, balances, cc_payments, interest_derivation, transfer_pairs_zero, lifecycle, duplicates, taxonomy_conformance, truth_isolation, sign_convention, manifest_and_volume, coverage, account_rules, holders, balance_months, effective_dates, artifacts (`app/datagen/validate.py:517`).
188. `fk_integrity` additionally enforces account-id-embeds-owner, txn user = account owner, and that every anomaly's entity/related ids exist (`app/datagen/validate.py:117`–`:128`).
189. Enum and id-format checks are derived from schema metadata, so a new column or FK is checked for free (`app/datagen/validate.py:133`, `:23`).
190. Balance check reconciles opening+credits+debits=closing chains, monthly flows vs the ledger, non-negative savings, closed accounts at zero (`app/datagen/validate.py:197`).
191. `interest_derivation` recomputes 3% p.a. on end-of-day balances per quarter and fails on interest posted after closure (`app/datagen/validate.py:252`).
192. `taxonomy_conformance` proves the only budgets violating the taxonomy are exactly the labelled anomalies (and counts them as `labelled`) (`app/datagen/validate.py:328`).
193. `truth_isolation` fails if any `true_*` column or ground-truth table leaks into `inputs/` (`app/datagen/validate.py:343`).
194. `sign_convention` cross-checks narration prefixes (UPI/DR/, BBPS/, ATM WDL vs UPI/CR/, NEFT CR, INT.PD…) against amount signs and rejects zero amounts (`app/datagen/validate.py:27`, `:352`).
195. `manifest_and_volume` re-hashes every file, compares rows, and requires exactly 12 business months (`app/datagen/validate.py:361`).
196. `artifacts` verifies the file set matches the manifest exactly, that JSON and `seed.sql` COPY blocks carry the same row counts, and that provenance checksums hold (`app/datagen/validate.py:472`).
197. `coverage` is a WARN-level check for presence of all issue types, true kinds and 6 series types (small datasets may legitimately miss one) (`app/datagen/validate.py:508`).
198. Nine output checks over a persisted run: completeness, partition_identity (income+spend+transfer/reversal buckets exhaustive and disjoint), mutual_pairs_balance, refund_links_to_earlier_purchase, series_ids_registered, exception_entities_exist, exception_event_chains (seq gaps, status continuity, last event = current status), series_events_ordered, insights_have_evidence (`app/jobs/outputs_validate.py:12`).
199. Output validation stores a `validation_run` row with pass flag and full per-check JSON (`app/jobs/outputs_validate.py:70`).

## Security & platform
200. Role set CUSTOMER/ANALYST/REVIEWER/ADMIN, enforced per request from the DB so demotions and disables take effect immediately (`app/schema.py:54`, `app/api/deps.py:20`).
201. Two pinned token kinds — HS256 local and RS256 Firebase — with `alg: none` and algorithm-confusion tokens rejected (`app/security.py:162`, `:141`).
202. Firebase keys are fetched from Google's x509 endpoint, cached by the returned max-age, guarded by a lock, and served stale if Google is unreachable (else 503) (`app/security.py:116`).
203. Token claims required per kind (exp/iat/sub/iss; plus aud for Firebase), 30 s leeway, subject length cap and future `auth_time` rejection (`app/security.py:98`, `:148`).
204. Password hashing is argon2id with library defaults; reset tokens embed a password-hash fingerprint making them single-use without a table (`app/security.py:24`, `:75`).
205. Session tokens embed the password fingerprint, so changing or resetting a password signs every other device out (`app/security.py:52`, `:63`).
206. Idempotency middleware replays the stored response (with `X-Idempotent-Replay: 1`) for mutating `/api/v1/me/*` calls carrying a valid 8–80 char `Idempotency-Key`, scoped to the caller and method+path (`app/idempotency.py:19`).
207. Idempotency takes a transaction-scoped advisory lock on the key so simultaneous repeats serialize, stores only 2xx answers, and prunes rows older than 14 days probabilistically (`app/idempotency.py:63`–`:78`).
208. Advisory locks are used throughout for sequence allocation and single-flight work: `app_user`, `category_override`, `category_rule`, `job`, `account_event`, per-household, per-budget-id, and the dataset-wide pipeline lock 72610221 (`app/api/*.py` passim, `app/db.py:9`).
209. `pg_try_advisory_lock` yields a typed `LockBusy` → 409 problem response instead of queuing (`app/db.py:23`, `app/api/errors.py:33`).
210. Household-scoping helper denies cross-household reads with 404 and lets admins pass `?user_id=` for support (`app/api/common.py:31`).
211. Cursor tokens are base64 with strict part-count validation and friendly expiry messages (`app/api/common.py:51`).
212. LIKE inputs are escaped for `\ % _` before every ILIKE/LIKE query (`app/api/common.py:68`, `app/api/admin.py:142`).
213. Amount/length validation: paise typed as int with ₹100 crore cap, positive-only amounts + explicit direction, VPA regex, reference charset, description/note/tag/label regex normalization (`app/api/entry.py:21`, `:36`, `app/api/entries_plus.py:58`).
214. Every human and job mutation writes an `audit_event` with actor, action, entity, request id and JSON detail; ~25 distinct action names (LOGIN, PASSWORD_RESET, CATEGORY_OVERRIDE, TXN_CREATE/EDIT/DELETE/IMPORT/SPLIT, TRANSFER_CREATE, BUDGET_SET/DELETE/CARRY, ACCOUNT_CREATE/CLOSE/EDIT, PROFILE_UPDATE, RULE_CREATE/VERSION/RETIRE, EXCEPTION_TRANSITION, USER_UPDATE, JOB_START, HOUSEHOLD_INVITE/JOIN/LEAVE/REMOVE, BACKUP_RESTORE, AI_SORT, EMAIL_CHANGE, ACCOUNT_DELETE, PASSWORD_CHANGE) (`app/api/me.py:192`, and each module).
215. Config self-check refuses to boot in `prod` with the default or a short JWT secret, and demands a 12+ char DEMO_PASSWORD distinct from the shared household password (`app/config.py:33`).
216. All errors leave as RFC 9457 `application/problem+json` with title mapping, instance path, request id, field-level validation details, `WWW-Authenticate: Bearer` on 401, and no stack traces (500 is logged, not leaked) (`app/api/errors.py:17`).
217. Structured JSON request logging with request-id echo (caller-supplied id accepted only if short and alphanumeric), latency ms, status, and `X-Request-ID` exposed through CORS (`app/logging.py:9`–`:41`, `app/main.py:40`).
218. GZip middleware (≥1024 B) sits outside the idempotency layer so stored replays are the uncompressed body (`app/main.py:38`).
219. SQLAlchemy engine pooling (10+10, pre-ping) with a swappable module-level engine so tests can redirect the connection factory (`app/db.py:8`, `:16`).

## Jobs & workers
220. In-process background job runner: one thread per job, a process-wide lock so jobs serialize, QUEUED→RUNNING→SUCCEEDED/FAILED transitions, error captured truncated to 2000 chars (`app/jobs/runner.py:64`–`:94`).
221. Job parameter validation and sizing: scale whitelist, `MAX_JOB_TRANSACTIONS` (100k) guard with an explicit "generate full offline" hint, VALIDATE scope check, EXPORT requires an existing manifest, REPRO scale guard (`app/jobs/runner.py:41`).
222. Single-flight rule rejecting a new dataset-mutating job (GENERATE_LOAD/PIPELINE) while one is queued or running (`app/jobs/runner.py:23`, `:67`).
223. Orphan recovery at startup marks jobs left QUEUED/RUNNING by the previous shutdown as FAILED (`app/jobs/runner.py:97`, `app/main.py:20`).
224. `GENERATE_LOAD` chains generate → load → seed logins → pipeline in one job (`app/jobs/runner.py:104`).
225. Pipeline runs are numbered `RUN-######`, insert a RUNNING row, then SUCCEEDED with stats+ruleset hash, or FAILED with the error while readers keep the last SUCCEEDED run (`app/jobs/pipeline_job.py:42`).
226. Two populations are processed separately: synthetic households judged "as of" the dataset's last month, real households as of today (`app/jobs/pipeline_job.py:97`).
227. `refresh_household` re-runs the engine for one household inside the latest run with a 3 s `lock_timeout`, deleting and rewriting its enrichment, series state/events, resolutions and insights; a busy lock queues the edit for the next run (`app/jobs/pipeline_job.py:66`).
228. Stable ids across runs: recurring series keep their `REC-` id for the same natural key, and exception cases keep their `EXC-` id and status (only `last_run_id` moves) (`app/jobs/pipeline_job.py:120`, `:153`).
229. Insights get per-household ids so refreshing one household never collides; exception cases get an initial `OPEN` event; evidence natural keys are swapped for `REC-` ids (`app/jobs/pipeline_job.py:146`, `:173`, `:184`).
230. `ruleset_hash` is a SHA-256 over the sorted active rule tuples, recorded per run for reproducibility (`app/jobs/pipeline_job.py:36`).
231. Bulk persistence uses binary-safe `COPY FROM STDIN` on the run's transaction (dicts/lists auto-serialized to JSON), and reads use schema-column-order SELECTs (`app/jobs/sql.py:8`, `:19`).
232. `next_number` derives the next sequence from `max(id)` of fixed-width ids, avoiding counters (`app/jobs/sql.py:27`).
233. Dataset load is an explicit reset: TRUNCATE inputs+truth+outputs `RESTART IDENTITY`, real households copied to `ON COMMIT DROP` temp tables and re-inserted, streaming 1 MiB `COPY` chunks, `synchronous_commit = off`, `ANALYZE` after load, and a `dataset_load` row with seed, manifest sha256 and row counts (`app/jobs/load.py:25`).
234. Demo logins: one per role at `@pam.test` when `DEMO_PASSWORD` is set, never overwriting existing accounts; sample household logins `usr-000001@pam.is-cool.dev` share one argon2 hash computed once for speed (`app/jobs/load.py:57`, `:81`).
235. Household deletion is cascaded across 23 statements while the audit log is deliberately retained, and refuses synthetic households (`app/households.py:36`).
236. Real households are separated by id range (from USR-500001, transactions TXN-YYYY-9xxxxxxx) so evaluation excludes them and reloads keep them (`app/households.py:9`, `app/jobs/evaluate_job.py:21`).
237. Daily digest worker: an asyncio loop in the API process checks every 15 minutes, sends only after 08:00 IST when mail is configured, records the day in `digest_run` so restarts never double-send, honors per-person bills/budgets/cards switches and `last_sent_on`, skips sample households, and sends nothing when there is nothing to report (`app/digest.py:80`–`:113`, `:41`).
238. Evaluation job persists `evaluation_run.metrics` plus per-anomaly `anomaly_outcome` rows for a run, replacing prior results (`app/jobs/evaluate_job.py:13`).

## Evaluation & metrics
239. Nine acceptance thresholds with operators: category_accuracy ≥0.85, transfer_f1 ≥0.95, refund_link_recall ≥0.90, tz_boundary_month_accuracy =1.0, budget_mismatch_handling =1.0, series_recall ≥0.85, missed_precision ≥0.80, missed_recall ≥0.80, decoy_false_alarm_rate ≤0.10, plus an `all_pass` flag (`app/evaluation.py:10`).
240. Metrics: accuracy, macro-F1, per-class precision/recall/F1/support and a full confusion dict, for both category and kind, plus coverage of categorized rows (`app/evaluation.py:54`, `:126`).
241. Link scoring computes set precision/recall/F1 for transfer pairs (unordered), refund→purchase links (ordered) and reversal pairs (`app/evaluation.py:130`–`:140`).
242. Series matching awards a truth series to the predicted series covering ≥50% of its members (best overlap wins), with series-level and member-level scores and a per-series-type breakdown (`app/evaluation.py:69`, `:156`).
243. MISSED-event evaluation scores precision/recall against labelled skips within ±7 days and computes the decoy false-alarm rate against labelled late-but-present occurrences (`app/evaluation.py:82`).
244. Timezone metrics compare IST month accuracy, naive UTC-month accuracy, and the TZ-boundary subset accuracy with its case count (`app/evaluation.py:164`).
245. Budget metric is MAE in paise over the union of user-month-category cells plus total spend comparisons (`app/evaluation.py:171`).
246. Naive baseline: every debit and every non-salary credit counted as spend, bucketed by UTC month (`salary|pension|int.pd` regex), reported as overstatement vs truth alongside PAM's own error (`app/evaluation.py:16`, `:102`).
247. Per-anomaly outcome judgments with the observed behaviour string, covering all six issue types (transfer both-legs-excluded, refund netting, skip/decoy, TZ month, budget remap-or-exception) (`app/evaluation.py:210`).
248. Markdown evaluation report renderer: threshold table, anomaly recall table, categorization per-class table, link table, recurring section, timezone/budget section and the naive-ledger comparison (`app/evaluation.py:259`).
249. Dataset validation report renderer with overall worst status, pass ratio and per-check examples (`app/datagen/validate.py:533`).

## CLI, exports & developer tooling
250. Eleven CLI subcommands: generate, export, repro, validate-dataset, evaluate, load, seed-users, pipeline, validate-outputs, all, docs (`app/cli.py:188`).
251. Common CLI flags on every subcommand: `--scale` (choices from SCALES), `--users`, `--transactions`, `--seed`, `--out`, `--reports`; plus `--report` for repro and `--db` for evaluate (`app/cli.py:201`).
252. `--out` defaults to `../data/<scale>`, or `../data/tmp-custom` when custom user/transaction counts are given; `--reports` defaults to `../reports/<scale-name>` (`app/cli.py:22`, `:57`).
253. `all` runs generate → validate-dataset → load → pipeline → evaluate (against the DB) → validate-outputs, timing each stage into `perf.json` (`app/cli.py:159`).
254. CLI exits non-zero on any FAIL (validate), failed check (validate-outputs), `all_pass` false (evaluate), or repro mismatch (`app/cli.py:73`, `:104`, `:54`).
255. `evaluate` without `--db` scores files-only (engine over CSVs, no database), with `--db` scores the latest DB run and commits it (`app/cli.py:77`).
256. `export` regenerates JSON + `seed.sql` + provenance next to existing CSVs and refuses when no dataset is present (`app/cli.py:36`).
257. `docs` regenerates `docs/data-dictionary.md` from schema metadata (never hand-edited): cardinality table, per-column type/required/allowed-values/unit/unique/validation/FK and description, and a full foreign-key list (`app/cli.py:175`, `app/docs_gen.py:42`).
258. Windows-console safety: stdout/stderr reconfigured to UTF-8 so the ₹ symbol prints (`app/cli.py:183`).
259. Alembic migrations with URL and metadata pulled from app settings, offline mode supported, `gt` schema included (`migrations/env.py:15`).
260. Six migrations, including constraint-replacing ENUM widenings (`OTHR`, then UPI providers and `account_type='UPI'` + `account_label`) and forward-safe downgrades that delete affected rows (`migrations/versions/0002_other_bank.py`, `0003_upi_accounts.py`).
261. Tables outside the dataset schema (txn_note, account_meta, goal, budget_carry, notify_pref, digest_run, household_invite, idempotency_key, user_rule, user_ai, ai_cache, account_label) deliberately carry no FKs so dataset reloads leave them alone (`migrations/versions/0004_extras.py:3`).
262. Naming conventions for pk/fk/uq/ck/ix are declared once in the metadata so generated DDL, seed.sql and migrations stay consistent (`app/schema.py:29`).
263. Every schema column carries data-dictionary metadata (description, allowed values, unit, validation rule), which doubles as the source of CHECK constraints, enum validation and docs (`app/schema.py:60`, `:67`).
264. Dev tooling config: pytest with `testpaths`, `.` on the path, `db` and `slow` markers (slow deselected by default), ruff with line-length 120 and E/F/I/B/UP/SIM rules plus documented per-file ignores (`pyproject.toml:25`–`:47`).

## AI integration
265. Optional Gemini integration, off entirely when `GEMINI_API_KEY` is unset (`app/config.py:26`, `app/ai_sort.py:28`).
266. Privacy mask before any AI call: emails, VPA ids and all digits removed, descriptor normalized and variable tokens stripped, lower-cased words only, capped at 80 characters — never amounts, dates, account names or identity (`app/ai_sort.py:32`, `app/api/sorting.py:106`).
267. The prompt explicitly frames narration as untrusted third-party data and forbids following instructions inside it (`app/ai_sort.py:67`).
268. Responses are constrained by a `responseSchema` with a category enum plus `UNSURE`, `temperature: 0`, JSON response MIME, and are re-validated in code (id must be requested, code must be in the enum, confidence 0–1) (`app/ai_sort.py:72`, `:88`).
269. Persistent AI answer cache keyed by SHA-256 of (masked text, direction, channel), stored with model name, consulted before any network call (`app/ai_sort.py:41`, `app/api/sorting.py:146`).
270. AI failures are non-fatal: provider errors leave entries unsorted, and a 502 is only raised if the provider failed *and* nothing was sorted (`app/api/sorting.py:158`, `:176`).
271. Household remembered rules sort unsorted entries by longest-phrase-first substring match on direction and normalized descriptor, applied as ordinary overrides with actor `RULE`, and silently skip categories retired since the rule was written (`app/api/sorting.py:52`).
272. Rule phrases are derived from the descriptor with variable parts stripped and capped at 60 chars, rejecting anything shorter than 3 chars (`app/api/sorting.py:27`, `:35`).

## Households / sharing / misc
273. Household ids and account ids follow the brief's formats for real logins too, with per-household account numbering under an advisory lock (`app/households.py:17`, `app/api/entry.py:122`).
274. New real households default to city "Not set", state NA, tier 2, SALARIED/MID, income 0, size 1, Asia/Kolkata (`app/households.py:22`).
275. Account display naming covers UPI providers, bank names, custom labels, `Other bank` fallback, and last-4 suppression for placeholder numbers (`app/api/me.py:70`).
276. `display_name` and `account_type` naming are reused by transfers and net-worth views for consistent labels (`app/api/entries_plus.py:222`, `app/api/analytics.py:296`).

## Web console — Theming and design tokens
277. CSS custom properties define paper, sheet, rule, ink, muted, blue, red, amber and green colour tokens (`index.css:6`).
278. A dark override swaps every token and sets the CSS color-scheme to dark on the data-theme attribute (`index.css:21`).
279. System dark preference applies automatically unless the theme is manually pinned to light (`index.css:36`).
280. The Tailwind inline theme block maps every token to a color utility class and a 2px radius (`index.css:44`).
281. The theme toggle persists to localStorage and falls back to prefers-color-scheme on first paint (`Shell.tsx:54`).
282. Switching theme also updates the browser theme-color meta tag to match the paper colour (`Shell.tsx:61`).
283. Body type is 15px with a 1.45 line-height for a dense register look (`index.css:63`).
284. Tabular lining figures are enabled globally so money columns align on the decimal point (`index.css:64`).
285. Scrollbars render thin in rule-strong over a transparent track and inputs inherit the body font (`index.css:68`).

## Web console — Register and stamp visual language
286. Status states print as bordered uppercase stamps rather than glowing badges (`ui.tsx:12`).
287. A status-tone map assigns each engine status its stamp colour and a friendly label (`ui.tsx:16`).
288. The left margin rule draws a single red vertical line evoking ruled register paper (`index.css:72`).
289. Register tables use uppercase muted headers with 1px row rules and blue-soft hover (`index.css:99`).
290. The signature strike-draw keyframe crosses out a naive figure with a hand-drawn red stroke (`index.css:112`).
291. The login hero renders a ruled sheet, red margin and worked naive-to-true ledger (`Login.tsx:43`).

## Web console — Animation and reduced motion
292. Skeleton rows shimmer with a 1.4s background sweep while data loads (`index.css:107`).
293. The splash logo breathes and a bar slides beneath it on full-page and route loads (`ui.tsx:205`).
294. Chart bars grow in once via scaleX and scaleY keyframes on mount (`index.css:150`).
295. The month's reinked wrapper fades and lifts the headline whenever the month changes (`Folio.tsx:42`).
296. A prefers-reduced-motion query zeroes every animation and transition duration document-wide (`index.css:121`).
297. Reduced motion also disables chart growth, donut fade and the calendar hover lift (`index.css:156`).

## Web console — Accessibility
298. A skip-to-content link is visually hidden until keyboard focus reveals it (`Shell.tsx:99`).
299. Focus-visible draws a 2px blue outline with offset on every interactive element (`index.css:67`).
300. Nav links and tool buttons meet a 44px mobile and 38px desktop minimum touch target (`Shell.tsx:117`).
301. The drawer traps Tab focus, closes on Escape and restores focus to the trigger on close (`ui.tsx:147`).
302. Every SVG chart carries role="img" with a descriptive aria-label for screen readers (`charts.tsx:21`).
303. Limit bars expose a percent-of-budget label and a no-budget fallback for readers (`ui.tsx:187`).
304. Month changes announce themselves through a polite live region beside the picker (`ui.tsx:105`).
305. Filter presets and upcoming-window toggles report their state with aria-pressed (`Entries.tsx:84`).

## Web console — Responsive behaviour
306. The shell collapses the sticky sidebar into a horizontal scrolling bar on mobile (`Shell.tsx:100`).
307. Grids reflow from multi-column desktop layouts to a single column on narrow screens (`Folio.tsx:42`).
308. Tables wrap in horizontal scroll containers with explicit min-widths to keep columns readable (`Entries.tsx:109`).
309. Content is capped at 1180px and centred with responsive gutters at every breakpoint (`Shell.tsx:145`).

## Web console — Loading, error and empty states
310. QueryState renders a skeleton, an error box, or children from a single query result (`ui.tsx:64`).
311. Skeleton accepts a row count and height so each page sizes its own placeholder (`ui.tsx:40`).
312. ErrorBox shows the server message, the request id and a Try again button (`ui.tsx:47`).
313. Empty pairs a title, optional hint and action between dashed rules (`ui.tsx:57`).
314. An HTML boot splash renders before any JavaScript using the same logo and bar (`index.html:15`).
315. A top progress bar appears whenever any query or mutation is in flight (`ui.tsx:216`).

## Web console — Formatting conventions
316. Money stays integer paise end to end and is formatted only at the display edge (`format.ts:1`).
317. Amounts use en-IN grouping so lakh and crore commas land in the right place (`format.ts:2`).
318. The Money component splits rupees and dimmed paise into two separate runs (`ui.tsx:28`).
319. Signed amounts print a real minus and an explicit leading plus when requested (`format.ts:7`).
320. Typed amounts parse to paise, rejecting three-decimal, empty and leading-negative input (`format.ts:13`).
321. Today and month defaults resolve in the Asia/Kolkata timezone regardless of device locale (`format.ts:21`).
322. Indian grouping, crore totals and signed negatives are covered by vitest unit tests (`format.test.ts:5`).

## Web console — Routing and role guards
323. A Guard component sends unauthenticated users to login and wrong-role users to their home (`App.tsx:33`).
324. Customer routes also admit admins so the support view can reuse the folio pages (`App.tsx:40`).
325. Each analyst, reviewer and admin route declares its own allowed-role list inline (`App.tsx:71`).
326. The root path shows the folio only for customers or admins currently holding a household (`App.tsx:91`).
327. Every page below the shell lazy-loads under Suspense with a splash fallback (`App.tsx:11`).
328. Unmatched routes render a 404 page styled as an entry missing from the register (`App.tsx:98`).

## Web console — Per-role navigation
329. Customers get an eleven-item My-month tree running from Folio through Settings (`Shell.tsx:11`).
330. Analysts see Exceptions, Rules, Metrics and Trace (`Shell.tsx:24`).
331. Reviewers see Anomalies, Audit log and Trace (`Shell.tsx:30`).
332. Admins combine Admin, Analyst and Reviewer groups in one sidebar (`Shell.tsx:46`).
333. Group headings appear only when a role has more than one navigation group (`Shell.tsx:111`).

## Web console — Admin support view
334. Opening a household stores its id in sessionStorage keyed pam.household (`api.ts:13`).
335. Every /me request auto-appends the held household id as the user_id query parameter (`api.ts:85`).
336. A red support-view banner names the household being viewed with a Leave button (`Shell.tsx:141`).
337. Leaving the household clears the id and returns the admin to the households page (`Shell.tsx:142`).
338. The household id never survives sign-out because the leave routine clears it (`auth.tsx:34`).

## Web console — Authentication flows
339. Login and register share one form that flips between sign-in and start-up modes (`Login.tsx:11`).
340. Registration asks for an optional name and enforces a ten-character minimum password (`Login.tsx:59`).
341. The Google popup button hides entirely when the Firebase environment variables are unset (`Login.tsx:63`).
342. Firebase auth is dynamically imported only when the Google button is actually pressed (`firebase.ts:11`).
343. Forgot-password posts the email and shows the server detail for a 30-minute link (`Recover.tsx:34`).
344. Reset reads the token from the URL and refuses to render the form without it (`Recover.tsx:73`).
345. A session-expired flag surfaces a friendly sign-in-again notice on the login screen (`auth.tsx:41`).
346. The bearer token lives in localStorage and the server owns role and the seven-day expiry (`api.ts:1`).

## Web console — Offline caching and PWA
347. The service worker precaches the shell, manifest and two icons at install (`sw.js:9`).
348. Fingerprinted app assets and images are served cache-first so a new build gets new names (`sw.js:46`).
349. Data GETs are network-first with the last good answer saved for offline replay (`sw.js:31`).
350. A clear message from the app wipes the offline data cache on sign-out (`sw.js:19`).
351. The manifest makes PAM installable standalone with its own theme colour and icons (`manifest.webmanifest:7`).
352. The worker registers only in production and the whole site works without it (`main.tsx:20`).

## Web console — Offline write queue
353. Unreachable writes are kept in localStorage and replayed once the server responds again (`api.ts:39`).
354. Each queued change carries an idempotency key so a cut-off send is never applied twice (`api.ts:91`).
355. Login, password, import and export calls are deliberately never queued (`api.ts:50`).
356. While anything is queued, new writes join the back so change order is preserved (`api.ts:92`).
357. The flush loop stops on network errors, 401, 5xx, 408 and 429 to keep ordering safe (`api.ts:68`).
358. A DELETE that comes back 404 is treated as already applied and dropped from the queue (`api.ts:69`).
359. Flush fires on coming online, every twenty seconds, and 1.5 seconds after load (`api.ts:77`).
360. The sync bar goes red on failed changes with Try again and Discard, and blue while sending (`Shell.tsx:84`).

## Web console — Data fetching layer
361. One QueryClient sets a 20-second stale time and turns off refetch-on-window-focus (`main.tsx:9`).
362. Queries retry a dropped connection once but never a request the server answered with 4xx (`main.tsx:14`).
363. The typed fetch client wraps GET, POST, PATCH, PUT and DELETE helpers over fetch (`api.ts:116`).
364. ApiError carries the HTTP status, the request id and field-level validation messages (`api.ts:18`).
365. A 401 response with a live token fires the registered unauthorized handler (`api.ts:109`).
366. Downloads fetch with the bearer header and hand a blob to the browser as a file (`api.ts:122`).

## Web console — Folio page
367. The headline shows true spend beside income and a kept savings-rate card (`Folio.tsx:42`).
368. The naive ledger figure is struck through and the gap to true spend explained in words (`Folio.tsx:46`).
369. A contra stamp and transfers-out figure break out money moved between your own accounts (`Folio.tsx:50`).
370. The against-budget table ranks nine categories by ratio with limit bars and status stamps (`Folio.tsx:79`).
371. Margin notes surface the unsorted count, missed recurring bills and the top insights (`Folio.tsx:96`).
372. The twelve-month chart draws spend columns with income ticks and peak plus current labels (`Folio.tsx:136`).
373. Pace projects month-end spend and a safe daily allowance to stay inside the limits (`FolioExtras.tsx:30`).
374. A sample household shows a read-only stamp and hides the add-entry button (`Folio.tsx:26`).

## Web console — Entries page
375. Transactions load through useInfiniteQuery using a keyset next-cursor, 50 rows at a time (`Entries.tsx:37`).
376. Every filter lives in the URL search params so any view is shareable and reload-stable (`Entries.tsx:16`).
377. Narration search is debounced 300 milliseconds before it touches the query (`Entries.tsx:33`).
378. Filters cover category, account, kind, merchant, tag, amount range and a date window (`Entries.tsx:63`).
379. An all-months checkbox swaps the month bar for a whole-register scan (`Entries.tsx:56`).
380. Rows group under sticky day headers that total each day's spend (`Entries.tsx:119`).
381. Transfers and reversals print struck while unknown rows carry a stamp and notes show tags (`Entries.tsx:114`).
382. Money out and money in sit in separate right-aligned tabular columns (`Entries.tsx:137`).

## Web console — Transaction drawer
383. The drawer loads one transaction by id and prints amount, payee, account and channel (`Entries.tsx:166`).
384. A why-this-category line reports the rule, its version and confidence, or a hand-set note (`Entries.tsx:193`).
385. Reclassification posts a category with an optional reason and a remember-my-choice toggle (`Entries.tsx:171`).
386. Remembering creates a rule; the success note reports how many similar entries it also sorted (`Entries.tsx:210`).
387. An override history list shows who changed the category, when, and why (`Entries.tsx:217`).
388. Note and tags save through a PUT that strips hashes and caps the tags at eight (`EntryTools.tsx:16`).
389. Splitting into two-to-ten parts validates the running sum live before it lets you submit (`EntryTools.tsx:41`).
390. Deletion is a two-step confirm that permanently removes the entry after a keep-or-delete prompt (`Entries.tsx:228`).

## Web console — Add entry
391. Defaults pick the first active account, today's date and the UPI channel (`Entries.tsx:288`).
392. Amount is the autofocus field and a radio pair toggles money out or in (`Entries.tsx:330`).
393. Optional details fold open for time, channel, counterparty VPA and reference number (`Entries.tsx:342`).
394. A server flag warns on likely duplicates and offers to remove the new copy (`Entries.tsx:316`).
395. With no active account the drawer points the user to Books instead of a form (`Entries.tsx:306`).

## Web console — CSV import
396. Files over 2MB are rejected and asked to be split by year (`EntryTools.tsx:130`).
397. Preview returns headers, a suggested column mapping and a sample grid before any write (`EntryTools.tsx:122`).
398. Five mappable fields cover date, narration, single amount, debit and credit columns (`EntryTools.tsx:111`).
399. A dry run reports to-import, skipped duplicates and per-row errors before confirming (`EntryTools.tsx:168`).
400. Re-importing the same statement is safe because rows already in the register are skipped (`EntryTools.tsx:146`).

## Web console — Transfers
401. Move-money writes a paired contra that is never counted as spending (`EntryTools.tsx:88`).
402. It needs two distinct active accounts and blocks selecting the same one twice (`EntryTools.tsx:100`).
403. The success state confirms both sides are written outside the spend total (`EntryTools.tsx:95`).

## Web console — Budgets
404. The budgets table shows spent, limit, a precise bar with a red tick and a status stamp (`Budgets.tsx:37`).
405. Inline editing replaces a limit while keeping the old version in history (`Budgets.tsx:91`).
406. Roll over is a per-category checkbox that carries unspent money into next month's limit (`Budgets.tsx:104`).
407. A limit of zero is documented as a plan to spend nothing in that category (`Budgets.tsx:58`).
408. Remapped budgets explain which renamed category now absorbs each submitted code (`Budgets.tsx:62`).
409. Unmapped budgets flag codes PAM cannot place and note the analyst has been asked (`Budgets.tsx:68`).

## Web console — Books
410. Accounts list provider, UPI id, balance and status with per-row edit and close actions (`Books.tsx:30`).
411. Account types cover savings, credit card and UPI apps, each showing its own fields (`Books.tsx:79`).
412. UPI apps include PhonePe, Google Pay, Paytm, BHIM and Amazon Pay plus a custom entry (`Books.tsx:9`).
413. An other bank or app reveals a required custom-name field for free text (`Books.tsx:81`).
414. Closing an account is a two-step confirm and is hidden for cross-household shared accounts (`Books.tsx:38`).
415. Joint holders print a Joint stamp inside the opened-on line of the table (`Books.tsx:32`).
416. The household profile edits city, state, income, household size and persona, read-only for samples (`Books.tsx:94`).

## Web console — Calendar
417. The month grid shades each day's spend on a colour-mix heat scale (`Calendar.tsx:63`).
418. A small green dot marks days where money also came in (`Calendar.tsx:71`).
419. Summary stats report month spend, daily average, busiest day and days left (`Calendar.tsx:24`).
420. Grid cells use role gridcell with aria-pressed and a full spoken label per day (`Calendar.tsx:66`).
421. Monday-first leading blanks align the first of the month under the right header (`Calendar.tsx:53`).
422. Tapping a day opens a drawer listing its entries and the total spent that day (`Calendar.tsx:79`).

## Web console — Spend analysis
423. A donut of category spend links both legend rows and slices through to filtered entries (`Spend.tsx:26`).
424. The by-category table prints this month, last month and change with arrow deltas (`Spend.tsx:35`).
425. Top payees render as a clickable bar list computed over the last six months (`Spend.tsx:51`).
426. Weekday bars highlight the heaviest spending day in red against the rest (`Spend.tsx:60`).

## Web console — Bills
427. A needs-a-look list prints over, watch and info stamps drawn from the alerts feed (`Bills.tsx:24`).
428. The coming-up section toggles a 7, 30 or 90 day window with aria-pressed (`Bills.tsx:37`).
429. Each upcoming bill counts days away and marks overdue ones in red (`Bills.tsx:47`).
430. Card utilisation bars turn amber at fifty and red at eighty percent of the limit (`Bills.tsx:79`).

## Web console — Goals
431. Goal cards show a progress bar, saved-versus-target figures and the remaining amount (`Goals.tsx:69`).
432. Contribute and take-out both post signed amounts against the chosen goal (`Goals.tsx:55`).
433. A deadline projects the monthly amount needed to arrive on time (`Goals.tsx:76`).
434. Completed goals earn a Reached stamp and hide the monthly projection (`Goals.tsx:63`).

## Web console — Recurring payments
435. Status tabs filter the series list across all, active, missed and ended states (`Recurring.tsx:18`).
436. The table shows payee, cadence, usual amount, last paid, next due and status (`Recurring.tsx:26`).
437. Expanding a series row prints its event timeline and the occurrence count (`Recurring.tsx:39`).
438. Missed series turn their next-due cell red to draw the eye (`Recurring.tsx:36`).

## Web console — Notes and insights
439. The notes page lists monthly insights with severity stamps and their insight types (`Insights.tsx:16`).
440. Each insight names its category and shows the underlying insight type as a label (`Insights.tsx:22`).
441. A month with nothing to flag reads as an empty note rather than an error (`Insights.tsx:15`).

## Web console — Settings
442. A daily-email digest master switch gates the bills, budget and card sub-switches (`Settings.tsx:42`).
443. An unconfigured mail server warns that the digest cannot send yet (`Settings.tsx:51`).
444. Sorting rules list remembered category choices with one-click removal for future entries (`Sorting.tsx:19`).
445. The AI sorter discloses its provider, exactly what is sent, and an opt-in toggle (`Sorting.tsx:45`).
446. A run button sorts unsorted entries and reports how many were left for a human (`Sorting.tsx:58`).
447. Household sharing creates invite codes, lists members, and lets the owner remove them (`Settings.tsx:77`).
448. Data controls export a date-ranged CSV, download a JSON backup, and restore one safely (`Settings.tsx:123`).
449. Security accordions change the password, change the email, and delete the account in place (`Settings.tsx:152`).

## Web console — Analyst pages
450. Exceptions open with type tabs, each showing a live count of matching cases (`Exceptions.tsx:31`).
451. A status dropdown and cursor paging drive the whole exception queue (`Exceptions.tsx:35`).
452. A state-machine NEXT map limits which transitions each current status allows (`Exceptions.tsx:11`).
453. A concurrent move returns 409, invalidates queries and shows the new state behind the message (`Exceptions.tsx:77`).
454. Rules sort by priority with confidence, a retired stamp and a new-version action (`Rules.tsx:31`).
455. A narration tester runs a descriptor through the rules and narrates the decision live (`Rules.tsx:84`).
456. Metrics table each threshold against its target with a pass or fail stamp (`Metrics.tsx:24`).
457. The naive baseline states how much a plain ledger overstates and PAM's own error (`Metrics.tsx:28`).

## Web console — Reviewer pages
458. Anomalies draw per-issue-type recall bars that turn red below ninety percent (`Review.tsx:33`).
459. Issue-type and outcome dropdowns scope the anomaly case table (`Review.tsx:46`).
460. Each anomaly case links its transaction straight through to the trace page (`Review.tsx:54`).
461. The audit log pages newest-first with actor, action and entity-id filters (`Review.tsx:66`).
462. Trace accepts a transaction id from the URL and renders every decision across runs (`Review.tsx:99`).
463. Run-decision rows list category, kind, rule version, decision and paired link (`Review.tsx:120`).
464. Ground truth renders only for reviewers and admins and only on labelled data (`Review.tsx:129`).

## Web console — Admin pages
465. Overview polls the admin feed every ten seconds for counts and pipeline state (`Admin.tsx:17`).
466. Five headline stats show households, real households, transactions, open exceptions and logins (`Admin.tsx:26`).
467. Output validation lists each consistency check with a pass or fail stamp (`Admin.tsx:33`).
468. Reproducibility compares two fresh-interpreter checksums and reports whether they match (`Admin.tsx:37`).
469. The job launcher offers seven job types, each with a one-line description (`Admin.tsx:47`).
470. Jobs history auto-refreshes every two seconds while any job is queued or running (`Admin.tsx:62`).
471. Logins search by email, change roles, and disable accounts with self-protection (`Admin.tsx:117`).
472. Exports list files with row counts and a truncated SHA-256 hash beside each download (`Admin.tsx:146`).
473. Households opens any valid USR id as the admin support-view folio (`Admin.tsx:156`).

## Web console — Developer tooling
474. Vite proxies /api to a live server or to VITE_API_TARGET during development (`vite.config.ts:8`).
475. npm scripts cover dev, a tsc-then-build, vitest test, eslint and vite preview (`package.json:7`).
476. Vitest runs in a node environment for the money and month unit tests (`vite.config.ts:10`).
477. TypeScript strict mode also forbids unused locals and parameters and unchecked side-effect imports (`tsconfig.app.json:19`).
478. Project references split the app and node tsconfigs from a solution-style root (`tsconfig.json:3`).
479. ESLint layers react-hooks and react-refresh rules over the typescript-eslint recommended set (`eslint.config.js:9`).
480. Builds ship no sourcemaps and raise the chunk-size warning limit to 700kB (`vite.config.ts:9`).
481. React nineteen runs under StrictMode with router seven, TanStack Query five and openapi types (`package.json:17`).
482. App.css is a leftover Vite scaffold stylesheet that the application never imports (`App.css:1`).

## Android app — Authentication
483. Email and password sign-in posts to /auth/login while register posts to /auth/register when the mode toggles (api.dart:48).
484. Google sign-in opens the native in-app account picker, not a browser, then trades the ID token for a session (login.dart:33).
485. The native picker needs a web OAuth client id passed as serverClientId to initialise GoogleSignIn (login.dart:32).
486. A Firebase login path /auth/firebase posts the Google ID token to establish the PAM bearer session (api.dart:52).
487. When Firebase configuration is absent the app still boots and falls back to email sign-in only (main.dart:21).
488. Google sign-in shows a degraded "not available in this build" message when initialisation throws (login.dart:47).
489. Login fields carry autofill hints for name, email and password so the keyboard offers stored credentials (login.dart:95).
490. The password field toggles visibility through a suffix eye icon that flips obscureText (login.dart:101).
491. Sign-up mode adds a name field and helper text requiring at least ten characters (login.dart:100).
492. An expired-session banner reads "Your session ended. Please sign in again." above the form (login.dart:89).
493. A sample-household hint tells explorers to sign in as usr-000001@pam.is-cool.dev with password123, read-only (login.dart:116).
494. Password reset is delegated: the screen points to pam.is-cool.dev/forgot instead of resetting in-app (login.dart:114).
495. An inline error box renders server messages in a red soft panel below the fields (login.dart:103).

## Android app — Secure token storage and sessions
496. The bearer token is stored under key "token" in Keystore-backed flutter_secure_storage, never plain preferences (api.dart:38).
497. Startup restores the stored token and calls /auth/me; a failure silently signs out keeping the queue (main.dart:47).
498. Any request returning 401 on a stored token signs out while preserving offline changes (api.dart:240).
499. Mobile sessions last thirty days; expiry flows through the same keepQueue sign-out path (api.dart:65).
500. A deliberate sign-out clears the outbox and mirror so nothing from one account reaches another (api.dart:67).
501. Adopting a fresh token swaps the stored sign-in after a password or email change (api.dart:177).
502. Sign-out also clears the read cache, home widgets and any Google or Firebase session (api.dart:70).
503. On sign-in the outbox owner id is checked; a foreign queue is dropped and never sent (offline.dart:109).

## Android app — API client
504. Base URL defaults to https://pam.is-cool.dev/api/v1 and is overridable with --dart-define=API_BASE (api.dart:16).
505. Every request sends an Accept application/json header and the identifying X-PAM-Client mobile header (api.dart:227).
506. Writes carry an Idempotency-Key so a send cut off mid-flight is never applied twice (api.dart:227).
507. JSON requests time out at twenty-five seconds while raw file downloads allow sixty (api.dart:232).
508. Network failures are normalised to ApiException status zero with a friendly can't-reach message (api.dart:234).
509. Server errors surface detail text, per-field validation messages and a request_id for support (api.dart:241).
510. A 204 No Content response is returned as null rather than attempted to parse (api.dart:236).
511. A thin two-pixel in-flight progress line shows at the top whenever inFlight exceeds zero (main.dart:180).
512. getText fetches raw CSV or JSON text for the system share sheet (api.dart:160).
513. The post, put, patch and delete verbs all route through the idempotent write path (api.dart:174).

## Android app — Navigation shell
514. Five bottom tabs Folio, Entries, Calendar, Spend and More live in an IndexedStack so state survives switching (main.dart:191).
515. A revision counter bumps after every write, forcing each tab to rebuild through its ValueKey (main.dart:169).
516. Spend jumps into Entries by setting a query filter string and raising the entries key (main.dart:174).
517. Deep-link filters arrive as query text such as category=FOOD parsed and applied on init (entries.dart:36).
518. Returning to the foreground triggers a quiet offline flush followed by a background prefetch (main.dart:131).
519. Tab selection plays a selection-click haptic before switching the selected index (main.dart:190).

## Android app — Onboarding
520. Four swipeable slides cover the value, true spend, budgets and repeats, and your own register (onboarding.dart:21).
521. A per-user seen flag is stored securely so returning users are never nagged again (main.dart:146).
522. Any existing accounts or entries auto-mark the walkthrough seen and skip it silently (main.dart:152).
523. Replay resets the flag from Settings and re-shows the four slides (main.dart:161).
524. Page dots animate width, slides fade and rise in, and Skip hides on the final slide (onboarding.dart:92).
525. The finishing button reads "Set up my books" on the last slide (onboarding.dart:98).
526. A getting-started checklist shows two steps that tick themselves off from live account and entry data (onboarding.dart:108).
527. The checklist only appears while both accounts and entries are still missing (onboarding.dart:133).
528. Tapping an open checklist step jumps to Books or Entries while an animated bar tracks progress (onboarding.dart:156).

## Android app — Folio
529. Folio pulls summary, budgets, insights and profile together in a single Future.wait load (folio.dart:21).
530. A month bar navigates months and re-keys the loader on each change (folio.dart:38).
531. The TRUE SPEND hero figure counts up on a large tabular money display (folio.dart:64).
532. A struck plain-ledger comparison shows how much PAM leaves out of naive spend (folio.dart:65).
533. INCOME and KEPT savings-rate figures sit side by side beneath the hero (folio.dart:75).
534. Against-budget rows list up to eight categories with limit bars and status stamps (folio.dart:82).
535. Margin notes show up to five insights colour-coded by ALERT, WARN or info (folio.dart:86).
536. Sample households display a read-only stamp in place of the setup guide (folio.dart:55).

## Android app — Entries
537. The register pages transactions forty per request, following a next cursor until exhausted (entries.dart:67).
538. A Load-more button runs out into an "End of the register" count line (entries.dart:208).
539. Search matches narration, payee or a parsed amount, capped at sixty characters (entries.dart:178).
540. The filter sheet offers category, account, type, from and to dates, min and max amount, tag and payee (entries.dart:513).
541. Quick range chips set Today, Last 7 days, Last 30 days or All months (entries.dart:187).
542. A badge on the filter button counts the currently active filters (entries.dart:184).
543. A ranged or all-months selection swaps the month bar for a range banner with Back-to-months (entries.dart:167).
544. Rows group under day headers that total that day's expenses (entries.dart:203).
545. Each row shows a date chip on a red margin, merchant or description, category, and signed money (entries.dart:219).
546. Status stamps mark Unsorted, Contra, Refund or Reversed and a "By hand" tag shows overrides (entries.dart:246).
547. Transfers and reversals render struck-through and muted across the register (entries.dart:227).
548. Swipe right opens the category sheet; swipe left deletes with a five-second undo snackbar (entries.dart:93).
549. Undo restores the removed row in place without ever reaching the server (entries.dart:118).
550. Sample households stay read-only: one-way swipe, hidden FAB and hidden overflow menu (entries.dart:95).
551. An Add-entry extended FAB opens the add sheet while overflow offers Move money and Import CSV (entries.dart:151).
552. An inline AI banner appears above the list whenever the Unsorted type filter is on (entries.dart:197).

## Android app — Entry detail sheet
553. A bottom sheet loads the transaction by id and renders a full provenance line (entries.dart:289).
554. Provenance states Set by hand, Rule N version X, or No rule matched (entries.dart:348).
555. A reclassify dropdown pairs with a Remember-for-similar-entries checkbox when writable (entries.dart:352).
556. Saving a category shows a snackbar reporting budgets updated and how many more sorted (entries.dart:296).
557. The note and tags section edits a private note and up to eight tags (entries.dart:349).
558. Actions expose Edit, Split and Duplicate; Split only shows for negative expense entries (entries.dart:358).
559. Duplicate copies the entry to today and toasts "Copied to today" (entries.dart:311).
560. Delete is two-step: tap Delete entry then confirm "Yes, delete" or Keep (entries.dart:364).
561. PopScope intercepts close and returns a changed flag so the list reloads (entries.dart:324).
562. Read-only sample entries hide editing actions and show the note as plain text (entries.dart:356).

## Android app — Add entry
563. A segmented Money-out versus Money-in control sets the direction of the new entry (entries.dart:439).
564. The amount field parses lakh-aware text to paise, rejecting empty or zero values (entries.dart:405).
565. A date button bounds selection between 2020 and today in IST (entries.dart:398).
566. The account dropdown defaults to the first active account of the household (entries.dart:435).
567. An empty household prompts "Add an account first" instead of showing the form (entries.dart:434).
568. The category dropdown is optional and defaults to the Let-PAM-decide placeholder (entries.dart:458).
569. After saving it reports "Saved and sorted" or "will be sorted in the next run" (entries.dart:473).
570. A duplicate card warns it looks like an existing entry with a one-tap "Remove the new one" (entries.dart:475).
571. Add another clears the amount and description and returns straight to the form (entries.dart:486).

## Android app — Books and accounts
572. Account rows show the display name, bank or UPI app label, balance and status stamp (books.dart:64).
573. Bank and UPI-app choices come from fixed code-to-name maps covering major Indian banks and wallets (books.dart:9).
574. Choosing Other bank or Other UPI app reveals a free-text name field (books.dart:144).
575. Savings and card accounts accept optional last-four digits; savings and UPI accept a VPA (books.dart:145).
576. Opening-balance labels change per type: amount owed, wallet balance, or balance when you start (books.dart:148).
577. The card edit sheet exposes credit limit, bill due day and statement day fields (books.dart:213).
578. Correcting the balance accepts negatives and rewrites the opening balance leaving entries untouched (books.dart:211).
579. Closed accounts and those shared from another household cannot be tapped to edit (books.dart:65).
580. The Move-money shortcut appears only when two or more accounts exist (books.dart:58).
581. Sample households show a read-only stamp and hide the Add and Move buttons (books.dart:57).

## Android app — Transfers
582. The transfer sheet requires two accounts, otherwise it prompts the user to add another (entry_tools.dart:249).
583. From and To pickers plus amount and date are validated, rejecting the same account twice (entry_tools.dart:226).
584. A move posts to /me/transfers as a matched pair that is never counted as spending (entry_tools.dart:229).

## Android app — CSV statement import
585. The file picker accepts only csv and txt and rejects anything larger than two megabytes (entry_tools.dart:300).
586. The chosen text posts to /me/import/preview so the server detects headers first (entry_tools.dart:307).
587. Column mapping dropdowns cover date, narration, a single amount or separate debit and credit columns (entry_tools.dart:296).
588. A dry run named Check-before-importing shows import, skip and error counts plus sample rows (entry_tools.dart:372).
589. The real import reports how many entries were added and how many duplicates skipped (entry_tools.dart:320).
590. Re-importing is duplicate-safe: rows already in the register are always skipped (entry_tools.dart:350).

## Android app — Calendar
591. A month renders as a Monday-first heat grid with each day shaded by its spend (calendar.dart:75).
592. Cell shading scales that day's spend against the month's peak-day amount (calendar.dart:98).
593. Days with entries but no net spending show a small green dot instead of a shade (calendar.dart:116).
594. Today is outlined with a thicker red border while dark cells switch to paper text (calendar.dart:110).
595. The amount label wraps in a FittedBox scaleDown to avoid cell overflow (calendar.dart:115).
596. A Less-to-More legend renders five increasing alpha steps of the blue (calendar.dart:83).
597. Three top facts report month SPENT, a daily A DAY average, and DAYS LEFT or BUSIEST (calendar.dart:67).
598. Tapping any day opens a sheet listing that day's entries with a spend line (calendar.dart:38).
599. The day sheet opens each entry in the detail sheet and reloads via a PopScope flag (calendar.dart:154).
600. A biggest-day caption names the peak day and its spend below the grid (calendar.dart:90).

## Android app — Spend
601. Spend loads categories, merchants, weekday pattern and the twelve-month trend in parallel (spend.dart:21).
602. The donut animates a sweep on an eight-hundred-millisecond controller around a centre total (charts.dart:30).
603. Donut hit-testing ignores the hole and outer edge, then maps the tap angle to a slice (charts.dart:57).
604. More than eight slices roll the smallest into a single "Other" that is not tappable (charts.dart:34).
605. Legend rows pair a colour swatch, label, share percentage and amount for each slice (charts.dart:83).
606. Tapping a slice or legend row jumps to Entries filtered by that category for the month (spend.dart:58).
607. An against-last-month block shows the total delta then up to six category movers (spend.dart:60).
608. Top payees render as a six-month bar list that opens per-merchant Entries (spend.dart:80).
609. A twelve-month column chart overlays a green income line above each month's spend bar (spend.dart:90).

## Android app — Plan screens
610. Bills and alerts loads notifications, upcoming payments and net worth in one parallel call (plan.dart:25).
611. Alerts are stamped Over, Watch or Info; an empty list reads "All clear" (plan.dart:56).
612. The coming-up window toggles across 7, 30 and 90 days (plan.dart:61).
613. Due rows show a LATE, TODAY or Nd badge with day, name, cadence and money (plan.dart:74).
614. Net worth reports YOU OWN, YOU OWE and NET, with per-card utilisation tiles (plan.dart:87).
615. Card utilisation bars turn amber past fifty percent and red past eighty (plan.dart:127).
616. Goals list shows animated progress, amount remaining and a monthly-to-set-aside projection (plan.dart:228).
617. Add-money and Take-out dialogs post a signed amount to the goal's contribute endpoint (plan.dart:191).
618. The goal sheet edits name, target, already-saved and an optional deadline before the horizon (plan.dart:273).
619. Budgets show total budgeted against spent with a limit bar and status per category (plan.dart:376).
620. A roll-over checkbox adds last month's unspent to this month's limit per category (plan.dart:408).
621. The set-limit sheet notes re-setting a limit keeps the old version in history (plan.dart:467).
622. Sample households hide the new-goal and set-limit floating action buttons (plan.dart:163).

## Android app — Recurring
623. Choice chips filter the series list by ALL, ACTIVE, MISSED or ENDED status (recurring.dart:27).
624. Each series row shows merchant or category, cadence and type, next and last dates, typical amount (recurring.dart:37).
625. A missed series renders its next-expected line in red bold with a Missed stamp (recurring.dart:46).
626. The empty hint explains patterns appear once a payment repeats three times (recurring.dart:35).

## Android app — Sorting
627. Remembered rules list quotes each phrase, its money direction and target category with a remove button (sorting.dart:40).
628. Rules are created when reclassifying an unsorted entry keeps the Remember checkbox ticked (sorting.dart:33).
629. An optional AI switch names the provider and discloses exactly what text is sent (sorting.dart:63).
630. The run action sorts unsorted entries, reporting how many sorted and how many left (sorting.dart:69).
631. A not-configured message tells the owner to add a Gemini API key to enable it (sorting.dart:60).
632. An inline AI banner above the Unsorted list offers one-tap sorting with sure answers applied (sorting.dart:84).

## Android app — Data and settings screens
633. The More hub groups Plan, Accounts, Data and App rows into pushed full-screen routes (more.dart:52).
634. CSV export uses from and to date pickers then shares the file through the system sheet (account.dart:321).
635. A JSON backup downloads a full copy while restore first validates the file is a PAM backup (account.dart:299).
636. The household screen lists members with You and Owner stamps; the owner can remove anyone (account.dart:225).
637. Invite codes are single-use, selectable and shareable through the share sheet (account.dart:239).
638. Users create an invite, leave a shared household, or join one with a code and an empty register (account.dart:248).
639. Daily email uses a master digest switch then bills, budgets and card checkboxes underneath (account.dart:169).
640. A warning appears when digest is on but the server has no outgoing email configured (account.dart:179).
641. Security changes password (auto-adopting the new token), changes email, and deletes the account with confirmation (account.dart:42).
642. Settings shows a profile card with avatar, email and role stamp (settings.dart:37).
643. A theme segmented control of System, Light and Dark persists the choice immediately (settings.dart:56).
644. The web console sheet reveals the host address with a copy-to-clipboard button (settings.dart:98).
645. The About sheet explains paise, IST dates, rule-and-version traceability and synthetic sample data (settings.dart:108).
646. An open-source licences page is reachable and sign-out warns about unsynced offline changes (settings.dart:73).

## Android app — Offline engine
647. The crash-safe JSON store writes a tmp file, keeps the prior copy as .bak, then renames (offline.dart:32).
648. A read falls back to the .bak whenever the main file is corrupt or missing (offline.dart:22).
649. Outbox flushing is serialised behind an async lock so queue saves never interleave (offline.dart:88).
650. Pending changes send strictly in insertion order, preserving that order across retries (offline.dart:157).
651. Statuses zero, 401, 5xx, 408 and 429 retry later while a DELETE 404 counts as done (offline.dart:171).
652. Local temporary ids prefixed L- are remapped to real server ids once each change lands (offline.dart:200).
653. A change depending on a failed one cascades straight into the failed list (offline.dart:159).
654. The failed list offers Try again and Discard for each refused change (widgets.dart:344).
655. An LRU read cache keeps up to eighty keyed responses in SharedPreferences, evicting the oldest (api.dart:131).
656. The transaction mirror holds eight-thousand rows trimming oldest, debounced to a two-second save (offline.dart:248).
657. A local overlay recomputes lists, accounts, daily, summary, categories, budgets and goals from queued ops (api.dart:116).
658. onlineOnly paths such as auth, import, restore, household, ai, export and backup bypass the queue (offline.dart:69).
659. Background prefetch pulls six months of entries and every screen's data after a resume (offline.dart:541).
660. A sync bar shows offline, syncing and failed states, opening a pending-changes sheet on tap (widgets.dart:276).

## Android app — Home-screen widgets
661. Three widgets: Today shows spend today and month, Budget month versus limits, Bills the next three (PamWidgets.kt:28).
662. The app saves keys signed_in, today_spend, month_spend, budget_total, budget_pct, bill_1 to bill_3 and updated (widgets_sync.dart:44).
663. Widgets refresh when the app opens and again after every successful sync (main.dart:116).
664. A thirty-minute fallback update period fires even when the app is closed (pam_today_info.xml:12).
665. Signed-out widgets hide every number and show a "Sign in" call to action (PamWidgets.kt:35).
666. The "Updated HH:MM" caption is blank whenever the user is signed out (PamWidgets.kt:17).
667. The Budget widget hides its progress bar when no category limits are set (PamWidgets.kt:50).
668. The Bills widget hides empty rows and shows a "nothing due" line when clear (PamWidgets.kt:66).
669. Sizes are Today 2x2, Budget 2x2 and Bills 3x2, all horizontally and vertically resizable (pam_bills_info.xml:9).
670. Widget backgrounds and text colours flip for night mode through a values-night color set (colors.xml:3).
671. Tapping any widget opens the app through a stored launch pending intent (PamWidgets.kt:18).

## Android app — Theming
672. A Hisaab Register palette defines paper, sheet, ruled lines, ballpoint blue, margin red, amber and green (theme.dart:12).
673. Material 3 themes seed from the blue with matched light and dark surface colours (theme.dart:33).
674. Tabular and lining font features are applied across money so columns align like a register (theme.dart:26).
675. Count-up widgets tween whole numbers toward new values over seven hundred fifty milliseconds (widgets.dart:257).
676. The boot splash breathes the logo in scale and opacity above a sliding bar (widgets.dart:222).
677. Reduce-motion freezes the donut, skeleton and count-up directly to their final states (charts.dart:46).
678. Haptic feedback fires on tab change, swipe, save and list selection throughout (main.dart:190).
679. Dark-mode logo assets swap by brightness across the app bar, splash and login (main.dart:82).
680. Two-pixel square radii and ruled hairline borders echo the paper ledger everywhere (theme.dart:45).
681. The donut clamps to the smaller of width and 210 on narrow screens via LayoutBuilder (charts.dart:51).
682. Bottom sheets lift by viewInsets.bottom so the keyboard never covers a field (entries.dart:328).
683. Money dims its decimals, strikes transfers, and adds rupees semantics for screen readers (widgets.dart:8).

## Android app — Android specifics
684. The manifest requests only the INTERNET permission and nothing else (AndroidManifest.xml:2).
685. MainActivity is exported, singleTop, and handles orientation, locale and uiMode configuration changes (AndroidManifest.xml:13).
686. Three exported widget receivers declare APPWIDGET_UPDATE filters pointing at their provider metadata (AndroidManifest.xml:30).
687. A queries element permits PROCESS_TEXT lookups that the share and autofill plugins rely on (AndroidManifest.xml:59).
688. The Gradle applicationId pam.garudatechnologies.com differs from the source namespace dev.is_cool.pam_mobile (build.gradle.kts:26).
689. Release signing falls back to the debug config when no key.properties file exists (build.gradle.kts:48).
690. The Google services plugin applies only when a google-services.json file is present (build.gradle.kts:64).
691. Launcher icons ship across five mipmap densities from mdpi through xxxhdpi (AndroidManifest.xml:6).
692. Light and night LaunchTheme and NormalTheme styles set window backgrounds for the splash (styles.xml:4).
693. Java seventeen source and target compatibility with Kotlin JVM_17 is configured (build.gradle.kts:20).
694. No push-notification SDK or Firebase messaging service is wired into the app (build.gradle.kts:64).

## Android app — Offline testing
695. A unit test seeds the mirror then asserts a queued entry appears in lists, accounts and totals (offline_test.dart:16).
696. Delete, edit, split, local filters and goal contributions are each verified against the recomputed overlay (offline_test.dart:27).

## Data & QA — committed starter dataset artifacts
697. Thirteen input CSVs under data/starter/inputs and three ground-truth CSVs (anomaly.csv, recurring_truth.csv, txn_label.csv) are committed.
698. Ground-truth txn_label.csv maps every transaction id to its true merchant, category, kind, link id and IST month.
699. Sixteen JSON exports under data/starter/json mirror the CSVs as top-level arrays with matching row counts.
700. A single 6115088-byte seed.sql holds the whole starter dataset inside one BEGIN/COMMIT atomic transaction.

## Data & QA — seed.sql structure and constraints
701. Sixteen CREATE TABLE statements, a gt schema for ground-truth tables, twenty-three REFERENCES foreign keys and thirty-four CHECK constraints sit in seed.sql.
702. Sixteen COPY ... FROM stdin WITH (FORMAT csv) blocks bulk-load each table in parent-first order.
703. ck_account_balance_monthly_reconciles requires opening plus credits plus debits to equal closing (seed.sql:142).
704. ck_account_status_matches_close ties status CLOSED to a non-null closed_on date to prevent lifecycle drift (seed.sql:106).
705. ck_category_rule_channel_allowed enumerates all ten permitted payment channels as an inline CHECK (seed.sql:85).
706. The gt ground-truth tables are loaded via COPY from stdin after the public-schema tables.

## Data & QA — manifest.json fields
707. manifest.json records currency as INR in paise, timezone Asia/Kolkata, generator pam-datagen/1 and seed 20261022.
708. Its params block stores transactions, users and year values; its files block stores each CSV row count and SHA-256.
709. manifest.json is byte-identical on every regeneration, making it the reproducible volume-and-checksum record.

## Data & QA — provenance.json fields
710. provenance.json stores synthetic_only true plus a statement that no real person or bank data was scraped.
711. It records generator_source_sha256, git_commit and the git_tree_clean_for_generator boolean flag.
712. Python 3.12.13, platform Windows-11-10.0.26200-SP0, dependency_lock_sha256 and manifest_sha256 identify the exact build.
713. Its exports block hashes every JSON file and seed.sql, but provenance itself is excluded from repro comparison.
714. A do_not_edit field instructs anyone to fix the generator and regenerate instead of editing files.

## Data & QA — observed ID formats
715. User ids follow USR-000001 with a six-digit zero-padded counter (backend/app/ids.py).
716. Account ids embed the owner as ACC-USR-000001-02; transaction ids are TXN-2026-00000002 using the IST year.
717. Budget ids look like BUD-USR-000001-2026-01-FOOD_DINING combining owner, month and category code.
718. Truth series ids use TRS-000002 while engine-predicted series ids use the REC-000001 form.
719. Merchants are MER-0001, rules RUL-0001, anomalies ANM-000001 and account events AEV-000001.
720. Merchant VPAs always carry a -mrch handle suffix such as uber-mrch@ybl to avoid real-handle confusion.

## Data & QA — scale parameters and real row counts
721. The starter scale produces 50 households and exactly 25000 transactions; the full scale produces 1000 and 500000 (generator.py:23).
722. Starter account.csv has 103 rows split into 77 savings and 26 credit-card accounts; full account.csv has 1951.
723. Starter txn_label.csv labels 21597 expenses, 1896 transfers, 1046 income, 387 refunds and 74 reversals.
724. Starter recurring_truth.csv holds 396 series: 139 utility, 90 subscription, 76 interest, 45 salary, 29 rent, 17 EMI; full holds 7755.
725. Starter budget.csv carries 4869 rows and full 93894; balance rows are 1223 versus full 23151.

## Data & QA — six labelled anomaly issue types with counts
726. Six labelled issue types are generated: BUDGET_CATEGORY_MISMATCH, RECURRING_NOT_SKIP, RECURRING_SKIP, REFUND_AS_EXPENSE, TRANSFER_DOUBLE_COUNT, TZ_BOUNDARY.
727. Starter counts are 10 budget-mismatch, 12 not-skip, 6 skip, 25 refund-as-expense, 20 transfer-double-count, 20 TZ-boundary (93 total).
728. Full counts scale to 200, 240, 120, 500, 400, 400 respectively (1860 total).
729. Each anomaly row ties an entity type and id to a related-id list plus an expected decision.
730. Anomaly volumes are driven from a per-user RATES table in anomalies.py:19.

## Data & QA — expected_decision vocabulary
731. Budget-mismatch anomalies expect REMAP_TO:CATEGORY for synonym or case corrections and bare EXCEPTION for unknown codes.
732. Recurring-skip anomalies expect MISSED_EVENT while recurring-not-skip decoys expect NO_MISSED_EVENT.
733. Refund-as-expense anomalies expect NET_AGAINST:CATEGORY pointing at the original purchase category.
734. Transfer-double-count anomalies expect EXCLUDE_BOTH_LEGS so neither leg enters the spend total.
735. TZ-boundary anomalies expect a MONTH:2026-MM decision naming the correct IST month.

## Data & QA — merchant catalog composition
736. The merchant master holds 65 Indian-brand rows MER-0001 through MER-0065 with default category, VPA and is_online flag.
737. Real brands include Swiggy, Zomato, BigBasket, Amazon, Flipkart, Myntra, Uber, Airtel, Jio, IRCTC, IndiGo, CRED and Nykaa.
738. UPI handles cycle five PSP suffixes ybl, axl, icici, hdfcbank, paytm assigned by index.
739. Forty merchants are online and 25 offline; the Tata Group row makes bare tata ambiguous via longest-match aliases.

## Data & QA — merchant aliases and long-tail shops
740. merchant_alias.csv maps 148 alias strings back to the 65 canonical merchant ids, including corporate-legal forms like bundl technologies.
741. Fourteen long-tail prefixes such as SRI LAKSHMI, NEW BALAJI and OM SAI form unmastered narrations.
742. Twelve long-tail suffixes decide a true category, e.g. PROVISION STORES and KIRANA mean GROCERIES.
743. Suffixes ENTERPRISES and TRADERS are deliberately ambiguous so no keyword rule can be right every time (catalog.py:166).

## Data & QA — category taxonomy, synonyms and retired categories
744. category.csv defines 24 codes across groups INCOME, ESSENTIALS, LIFESTYLE, OTHER, FINANCIAL with kinds EXPENSE/INCOME/TRANSFER/UNKNOWN.
745. Two retired categories DINING_OUT and MOBILE_RECHARGE carry effective_to dates and replaced_by successors FOOD_DINING and UTILITIES.
746. category_synonym.csv lists five synonyms BILLS, FOOD_AND_DINING, GROCERY, MEDICAL, SUBSCRIPTION mapped to canonical codes.

## Data & QA — seeded rule bands and priorities
747. Ninety version-1 rules span priority bands 5, 6, 10, 50, 60, 90 and 95 all created by system.
748. Priority 5 covers five system keywords like salary, interest and self-transfer, matched before all others.
749. Priority 10 holds merchant refinements such as instamart to GROCERIES; priority 50 holds 65 merchant defaults.
750. Priority 90 covers ten long-tail keyword rules and priority 95 three credit-fallback rules.
751. Rules match on pattern, channel, direction DR/CR/ANY and account_type SAVINGS or CREDIT_CARD.

## Data & QA — channel vocabulary
752. Ten channels form the enum: UPI, IMPS, NEFT, RTGS, NACH, CARD_POS, CARD_ECOM, ATM, BBPS, INTERNAL.
753. In starter transactions UPI dominates with 15461 rows, then CARD_ECOM 3338, IMPS 1522, CARD_POS 1412, BBPS 1084, ATM 730, NEFT 664, INTERNAL 605, NACH 184.
754. Descriptors mimic Indian bank narrations such as UPI/DR/... and ATM WDL, while the bank handle table maps each VPA suffix to a short bank code like ybl to YESB (descriptors.py:4).

## Data & QA — household, persona and income-band structure
755. Fifty starter profiles carry persona, income_band, city_tier and household_size with full scale at 1000 profiles.
756. Personas split 43 SALARIED, 5 SELF_EMPLOYED, 2 RETIRED; income bands LOW 16, MID 20, HIGH 12, AFFLUENT 2.
757. City tiers are T1 21, T2 21, T3 8 and household size ranges 1 to 6 in starter.
758. Joint accounts exist N:M via account_holder with 104 holder rows for 103 accounts.
759. Persona weights drive category mix, e.g. RETIRED spends 30% on GROCERIES versus SALARIED 20%.

## Data & QA — seasonality and holiday-aware scheduling
760. Eight categories carry twelve-month frequency multipliers such as SHOPPING peaking 1.6-1.7 at Diwali and UTILITIES Apr-Jun for AC load.
761. EDUCATION spikes 2.5x April and June for fees; TRAVEL rises in summer and year-end.
762. Five national 2026 bank holidays are hardcoded: 26 Jan, 1 May, 15 Aug, 2 Oct, 25 Dec.
763. Salary on Sunday, 2nd/4th Saturday or holiday is paid the previous working day; holiday-1st pension rolls forward.
764. A subscription billed on the 29th-31st clamps to month end as a skip-detection decoy, and a 28-day pack yields 13 charges in one monthly series.

## Data & QA — refunds, transfers and other ledger phenomena
765. Self transfers post as offsetting IMPS/SELF pairs sharing one reference across both legs.
766. Credit-card statements net refunds and are paid on day 3-7 of the following month; December stays unpaid into Jan 2027.
767. Refunds link to an earlier purchase with partial sums never exceeding the original, while failed payments generate UPI/REV reversal pairs sharing the RRN and same-day buys inject a duplicate.
768. Quarterly savings interest pays one credit per account per quarter at minimum one rupee; account closure sweeps the balance to zero.

## Data & QA — derived-value rules
769. Monthly balances are derived so opening plus credits plus debits reconcile to closing, and savings opening balances are raised so the running balance never goes negative.
770. Budgets are generated from measured spend rather than random, so actuals and budgets share intent.
771. Ground-truth labels are derived from the same rules as the generator, never from random draws.

## Data & QA — determinism technique
772. The RNG is built only on random.random plus a string-seeded random.Random for cross-version stability, reimplementing choice, randint, gauss on top (rand.py).
773. Each RNG stream is named from a f-string of seed plus a purpose tag, e.g. Rand(f"{seed}:global:adjust").
774. Master data precedes dependent records so parent ids exist; exact volume is hit only by standalone savings UPI debits and RRNs are a coprime bijection of the event key.

## Data & QA — reproducibility and tamper mechanisms
775. The repro command regenerates and re-exports in two fresh interpreters with PYTHONHASHSEED 1 and 2, both yielding the identical manifest hash 19ef74d06f9f... recorded in reproducibility.json.
776. The .gitattributes marks *.csv, *.sql, *.json as -text and *.png, *.apk binary under text=auto eol=lf, while CI verifies published hashes from docs/manifest-hashes.sha256 with sha256sum -c.
777. The ruleset_hash is a SHA-256 of active rules stored per pipeline_run; dataset_load records store scale, seed, manifest_sha256 and rows (schema.py:279).

## Data & QA — twenty-two dataset validation checks (all named)
778. The columns check verifies headers equal the schema column order.
779. The pk_unique check enforces primary-key uniqueness across every table.
780. The fk_integrity check validates every declared foreign key reference resolves.
781. The enums check confirms all enumerated columns hold allowed values.
782. The id_formats check validates identifiers against the compiled ID_PATTERNS regexes.
783. The date_order check enforces chronological date consistency.
784. The balances check recomputes the monthly balance reconciliation equation.
785. The cc_payments check requires no bill payment when a statement is zero or negative.
786. The interest_derivation check recomputes every quarterly interest credit.
787. The transfer_pairs_zero check nets each transfer pair to exactly zero.
788. The lifecycle check validates open and close transitions against events.
789. The duplicates check detects unintended duplicate rows.
790. The taxonomy_conformance check validates budget categories, flagging ten labelled mismatches.
791. The truth_isolation check guarantees ground-truth columns never leak into inputs.
792. The sign_convention check enforces debit negative and credit positive amounts.
793. The manifest_and_volume check compares declared counts and hashes to files.
794. The coverage check confirms all issue types, true kinds and series types appear.
795. The account_rules check validates credit limits exist only on cards.
796. The holders check enforces exactly one primary holder per account.
797. The balance_months check confirms contiguous chaining monthly balance rows.
798. The effective_dates check validates ordered rule and category effective dates.
799. The artifacts check verifies the file set, JSON/SQL row counts and provenance checksums.
800. All twenty-two starter checks report PASS with zero violations (reports/starter/validation_dataset.md).

## Data & QA — nine pipeline-output validation checks (all named)
801. The completeness check ensures every input transaction received an output decision.
802. The partition_identity check verifies a run partitions transactions without loss.
803. The mutual_pairs_balance check confirms transfer pairs net to zero.
804. The refund_links_to_earlier_purchase check requires each refund precede from a valid earlier debit.
805. The series_ids_registered check confirms every emitted series id is registered.
806. The exception_entities_exist check verifies each exception references a real entity.
807. The exception_event_chains check validates exception status transitions form a chain.
808. The series_events_ordered check confirms each series' events are chronologically ordered.
809. The insights_have_evidence check requires every insight reference backing numbers.
810. All nine output checks report PASS (reports/starter/validation_outputs.md).

## Data & QA — report files under reports/starter and reports/full
811. reports/starter/evaluation.md tabulates nine acceptance metrics; category_accuracy 0.9810 and transfer_f1 1.0000 both pass.
812. Starter evaluation reports refund_link_recall 0.9358 and tz_boundary month accuracy 1.0000; evaluation.json holds the full per-category and per-link structure.
813. reports/starter/perf.json records stage timings generate 1.2, validate 0.7, load 11.5, pipeline 10.1, evaluate 3.7, validate_outputs 0.9 seconds.
814. Starter reproducibility.json plus validation_dataset and validation_outputs json/md files complete the starter report set.
815. reports/full holds evaluation json/md, manifest, provenance, reproducibility and validation_dataset json/md but no perf or validation_outputs.
816. Full evaluation shows per-issue recall 400/400 transfer and 465/500 refund-as-expense; the committed full manifest hash 1938a37638e5 matches docs/manifest-hashes.sha256.

## Data & QA — commit policy honesty for full scale
817. Only the starter dataset is git-tracked, with thirty-five files under data/starter confirmed by git ls-files.
818. The data/full directory is git-ignored, so its CSV and JSON bytes are not committed to the repository.
819. Full-scale bytes ship as an attached release zip while reports/full carries the derived manifest, provenance and reports.

## Data & QA — documentation set
820. docs/data-dictionary.md is generated from app/schema.py and documents 33 table subsections with 241 column rows plus a sixteen-row cardinality table.
821. docs/dataset-provenance.md explains synthetic-only status and the four tamper-detection checks; docs/dev-setup.md documents the SSH tunnel and pam role.
822. docs/deploy.md covers updating, CD gating, first-time setup, mail relay and sizing; docs/infrastructure.md maps domain, VM, three firewall layers and DNS.
823. docs/brand holds three PNG logos dark, light and transparent; docs/manifest-hashes.sha256 lists two published manifest hashes.

## Data & QA — edge-case register
824. docs/edge-cases.md is a living catalogue with status vocabulary done, partial, open and dropped.
825. Two hundred entries are marked done, 26 manual, 5 partial, 5 open and 6 dropped across thirty-nine rows.
826. Cases are grouped by prefix such as D for data generation, each citing handling location, test name and a star for labelled brief anomalies.

## Data & QA — design spec, plans, AI disclosure, product and license
827. The design spec opens with twenty-seven requirement-traceability rows R1 through R27, each mapping the problem statement to a design section and plan task.
828. Two implementation plans cover the backend and the clients-plus-docs slices.
829. docs/ai/AI-DISCLOSURE.md names Claude Code, Impeccable, optional Gemini and ChatGPT honestly; prompt-history.md lists fifty-three numbered prompts P1 through P53 grouped by phase.
830. PRODUCT.md defines four actors customer, analyst, reviewer and admin plus purpose; LICENSE is MIT (c) 2026 vbs-0 and README.md runs thirteen major sections.

## Data & QA — Makefile targets
831. Makefile defaults SCALE to starter with targets install, test, lint, migrate, data, pipeline, all, api, docs and web declared .PHONY.
832. The data target runs the generate CLI for the chosen SCALE; the all target runs generate, validate, load, engine, evaluate and output validation.

## Data & QA — CI backend job steps
833. The CI backend job runs on ubuntu-latest with a postgres:14 service container setting user pam, password pam, db pam_test on 5432.
834. The service health command runs pg_isready -U pam with interval 5s, timeout 5s and 10 retries.
835. setup-uv installs then uv sync --frozen --python 3.12 pins the locked environment before ruff check app tests and pytest -q.
836. The repro step regenerates the starter via the CLI repro command into /tmp with a report path.
837. The regenerate-and-diff step generate-and-exports into /tmp then diffs inputs, ground_truth, json, manifest.json and seed.sql against committed data.
838. A final step runs sha256sum -c docs/manifest-hashes.sha256 to verify published hashes.

## Data & QA — CI web, mobile and deploy gating
839. The web job pins Node 24 with npm cache then runs npm ci, npm run lint, npm audit --omit=dev --audit-level=high, npm run build and npx vitest run.
840. The mobile job uses subosito/flutter-action stable with cache then runs flutter pub get and flutter analyze --no-fatal-infos.
841. The deploy job needs backend, web and mobile and fires only on push to refs/heads/main under a concurrency group named deploy.
842. SSH setup installs secrets DEPLOY_SSH_KEY, DEPLOY_HOST, DEPLOY_KNOWN_HOSTS with StrictHostKeyChecking yes; the web console build passes only public VITE_FIREBASE identifiers.

## Data & QA — deploy script behaviour
843. deploy.sh runs git archive of HEAD for backend and docs, shipping only committed code.
844. It preserves the server .env by copying it into the new tree before an atomic swap that moves backend to backend.old.
845. It restarts pam-api then polls /readyz up to 20 times at one-second intervals, rolling back to backend.old and re-restarting on failure.
846. Dependency sync and alembic upgrade head run as the unprivileged pam user with uv sync --frozen --no-dev.

## Data & QA — systemd unit hardening
847. pam-api.service runs as unprivileged User pam, Group pam with NoNewPrivileges, ProtectSystem=strict, ProtectHome and PrivateTmp.
848. ReadWritePaths limits writable directories to data, reports and /tmp with MemoryMax 600M and Restart on-failure after 3 seconds.
849. ExecStart binds uvicorn to 127.0.0.1:8100 with one worker and no server header; the unit Requires and After postgresql.service.

## Data & QA — nginx config contents and honest gaps
850. nginx-pam.conf listens 443 ssl with Certbot-managed Let's Encrypt certificates and a port-80 redirect, setting client_max_body_size 2M.
851. Only two security headers are present, X-Content-Type-Options nosniff and Referrer-Policy strict-origin-when-cross-origin; CSP, X-Frame-Options and HSTS are absent.
852. Proxy rules forward api, healthz, readyz, docs, openapi.json and redoc to 127.0.0.1:8100 with four forwarded headers and 120s read timeout.
853. The SPA location falls back to index.html via try_files; the APK path /opt/pam/www/downloads/pam.apk exists only in deploy.md, not as an nginx location.

## Data & QA — Postgres roles, secrets, gitignore and mail policy
854. The pam role owns only pam and pam_test with CONNECT revoked from PUBLIC; Postgres listens on localhost reached via SSH tunnel 15432.
855. .env, backend/.env and .env.example placeholders for JWT_SECRET and DEMO_PASSWORD are git-ignored, as are service accounts, keystores, key.properties and google-services.json.
856. Password-reset mail sends through an authenticated SMTP relay on port 587 since Oracle blocks port 25; Gmail allows about 500 messages a day.
857. Reset sends are limited to 3 per address and 10 per client per hour; leaving SMTP unset disables mail so requests do nothing.

## Data & QA — test inventory and lint gates
858. Twenty-nine backend test files hold 191 test functions excluding conftest, spanning engine, api, datagen, jobs and top-level areas.
859. Engine test_engine_never_touches_ground_truth asserts the pipeline cannot read gt tables; security tests cover Firebase claim, unknown-kid, signer, algorithm-confusion and none rejection plus local-token expiry, argon2id hashing and cert-cache max-age parsing.
860. Seven schema tests assert every column documented with a primary key and truth-free inputs; six evaluation tests check thresholds while two health tests verify healthz and request-id echo.
861. The web suite is one Vitest file format.test.ts with six it cases; five Flutter tests cover offline queue, edit, split, local filters and goal change.
862. Backend pytest defines markers db and slow while addopts deselect via -m 'not slow'; ruff enforces line-length 120 with select E F I B UP SIM.
