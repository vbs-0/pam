export type Role = "CUSTOMER" | "ANALYST" | "REVIEWER" | "ADMIN";
export interface Me { app_user_id: string; email: string; role: Role; profile_user_id: string | null }
export interface LoginOut { access_token: string; user: Me; expires_in: number }

export interface Txn {
  txn_id: string; local_date: string; posted_at: string; account_id: string; amount_paise: number; channel: string;
  descriptor: string; counterparty_vpa: string | null; merchant_id: string | null; merchant_name: string | null;
  category_code: string; kind: string; confidence: number | null; decision: string; overridden: boolean;
  link_txn_id?: string | null; series_id?: string | null; reference_no?: string | null; rule_id?: string | null;
  rule_version?: number | null;
  note?: string; tags?: string[];
  overrides?: { override_id: string; category_code: string; actor: string; reason: string | null; created_at: string }[];
}
export interface TxnPage { items: Txn[]; next_cursor: string | null }
export interface Category { code: string; name: string; group: string; kind: string; active: boolean; replaced_by: string | null }
export interface Account {
  account_id: string; account_type: "SAVINGS" | "CREDIT_CARD" | "UPI"; bank_code: string; masked_number: string; vpa: string | null; label: string | null; display_name: string;
  status: string; opened_on: string; closed_on: string | null; credit_limit_paise: number | null; holder_role: string;
  balance_paise: number; shared_from_other_household: boolean;
}
export interface Profile {
  user_id: string; display_name: string; city: string; state: string; persona: string; income_band: string;
  monthly_income_paise: number; household_size: number; sample: boolean; has_run: boolean;
}
export interface Summary {
  month: string; income_paise: number; spend_paise: number; naive_spend_paise: number; transfers_out_paise: number;
  savings_rate: number | null; top_categories: { code: string; spend_paise: number }[];
  over_budget_count: number; near_budget_count: number;
}
export interface BudgetLine {
  category_code: string; category_name: string | null; budget_paise: number | null; actual_paise: number;
  ratio: number | null; status: "UNDER" | "NEAR" | "OVER" | "NO_BUDGET"; budget_ids: string[]; carried_paise?: number;
}
export interface Budgets {
  month: string; carry_enabled?: string[]; lines: BudgetLine[]; total_budget_paise: number; total_actual_paise: number;
  remapped: { budget_id: string; submitted_code: string; resolved_code: string; resolution: string }[];
  unmapped: { budget_id: string; submitted_code: string; amount_paise: number }[];
}
export interface Series {
  series_id: string; account_id: string; merchant_id: string | null; merchant_name: string | null; category_code: string;
  series_type: string; cadence: string; median_gap_days: number; typical_amount_paise: number; first_seen: string;
  last_seen: string; next_expected: string | null; status: "ACTIVE" | "MISSED" | "ENDED"; occurrences: number;
  direction: string; events: { seq: number; type: string; date: string; detail: Record<string, unknown> | null }[];
}
export interface Insight {
  insight_id: string; month: string; insight_type: string; severity: "INFO" | "WARN" | "ALERT"; category_code: string | null;
  metric_paise: number | null; baseline_paise: number | null; message: string;
}
export interface Trend { month: string; spend_paise: number; income_paise: number }

export interface ExceptionRow {
  exception_id: string; exception_type: string; entity_type: string; entity_id: string; user_id: string | null; status: string;
  detail: Record<string, unknown> | null; created_at: string; updated_at: string; current: boolean; descriptor?: string | null;
  amount_paise?: number | null; posted_at?: string | null; budget_code?: string | null; budget_month?: string | null;
}
export interface Rule {
  rule_id: string; version: number; priority: number; category_code: string; merchant_id: string | null; pattern: string | null;
  channel: string | null; direction: string; account_type: string | null; confidence: number; effective_from: string;
  retired_at: string | null; created_by: string; note: string | null;
}
export interface Job {
  job_id: string; job_type: string; params: Record<string, unknown>; status: "QUEUED" | "RUNNING" | "SUCCEEDED" | "FAILED";
  created_by: string; created_at: string; started_at: string | null; finished_at: string | null;
  result: Record<string, unknown> | null; error: string | null;
}
export interface Page<T> { items: T[]; next_cursor: string | null }

export interface ValidationOut { passed: boolean; created_at: string; results: { checks: { name: string; status: string }[] } }
export interface ReproOut { match: boolean; source?: string; runs: string[]; python_hash_seeds?: number[]; files?: Record<string, string> }
export interface TraceOut {
  txn: { amount_paise: number; descriptor: string; posted_at: string; channel: string; account_id: string; account_type: string; account_status: string };
  current: { category_code: string; kind: string } | null;
  runs: { run_id: string; category_code: string; kind: string; rule_id: string | null; rule_version: number | null; decision: string; link_txn_id: string | null }[];
  overrides: { override_id: string; category_code: string; actor: string; created_at: string; reason: string | null }[];
  truth?: Record<string, unknown> | null;     // reviewers and admins only
  exceptions: { exception_id: string; exception_type: string; status: string; events: { seq: number; from_status: string | null; to_status: string; actor: string; at: string; note: string | null }[] }[];
}

// ---- calendar, analytics, planning ----
export interface DailyDay { date: string; spend_paise: number; income_paise: number; count: number }
export interface Daily { month: string; days: DailyDay[]; total_spend_paise: number; busiest: string | null; daily_average_paise: number; days_elapsed: number; days_left: number }
export interface CatSpend { code: string; name: string; spend_paise: number; previous_paise: number; change_paise: number; share: number }
export interface SpendByCategory { month: string; previous_month: string; total_paise: number; previous_total_paise: number; change_paise: number; categories: CatSpend[] }
export interface MerchantSpend { name: string; spend_paise: number; count: number; last_date: string; category_code: string }
export interface WeekdaySpend { weekday: number; name: string; spend_paise: number; days: number; count: number; average_paise: number }
export interface UpcomingItem { kind: "RECURRING" | "CARD"; id: string; name: string; direction: "DR" | "CR"; amount_paise: number; due: string; days_away: number; overdue: boolean; series_type: string; cadence: string; category_code: string | null }
export interface Upcoming { days: number; items: UpcomingItem[]; due_out_paise: number; due_in_paise: number }
export interface CardInfo { account_id: string; display_name: string; balance_paise: number; limit_paise: number | null; used_paise: number; available_paise: number | null; utilisation: number | null; due_day: number | null; statement_day: number | null; due_date: string | null; days_to_due: number | null }
export interface NetWorth { net_worth_paise: number; assets_paise: number; liabilities_paise: number; accounts: { account_id: string; display_name: string; account_type: string; balance_paise: number }[]; cards: CardInfo[] }
export interface AlertItem { type: string; severity: "ALERT" | "WARN" | "INFO"; title: string; detail: string; amount_paise: number }
export interface Goal { goal_id: string; name: string; target_paise: number; saved_paise: number; remaining_paise: number; progress: number; deadline: string | null; days_left: number | null; monthly_needed_paise: number | null; completed: boolean; completed_at: string | null }
export interface NotifyPrefs { email_digest: boolean; bills: boolean; budgets: boolean; cards: boolean; last_sent_on: string | null; email: string; mail_configured: boolean }
export interface HouseholdInfo { household_id: string; you: string; owner: string | null; members: { app_user_id: string; email: string; joined: string; is_owner: boolean; you: boolean }[]; invites: { code: string; expires_at: string }[] }
export interface ImportPreview { headers: string[]; suggested_mapping: Record<string, string>; rows_total: number; sample: string[][]; max_rows: number }
export interface ImportResult { dry_run: boolean; rows_total: number; to_import: number; skipped_duplicates: number; error_count: number; errors: { row: number; message: string }[]; mapping: Record<string, string>; sample: { date: string; amount_paise: number; description: string }[]; imported: number }
