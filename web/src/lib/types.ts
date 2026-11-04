export type Role = "CUSTOMER" | "ANALYST" | "REVIEWER" | "ADMIN";
export interface Me { app_user_id: string; email: string; role: Role; profile_user_id: string | null }
export interface LoginOut { access_token: string; user: Me; expires_in: number }

export interface Txn {
  txn_id: string; local_date: string; posted_at: string; account_id: string; amount_paise: number; channel: string;
  descriptor: string; counterparty_vpa: string | null; merchant_id: string | null; merchant_name: string | null;
  category_code: string; kind: string; confidence: number | null; decision: string; overridden: boolean;
  link_txn_id?: string | null; series_id?: string | null; reference_no?: string | null; rule_id?: string | null;
  rule_version?: number | null;
  overrides?: { override_id: string; category_code: string; actor: string; reason: string | null; created_at: string }[];
}
export interface TxnPage { items: Txn[]; next_cursor: string | null }
export interface Category { code: string; name: string; group: string; kind: string; active: boolean; replaced_by: string | null }
export interface Account {
  account_id: string; account_type: "SAVINGS" | "CREDIT_CARD"; bank_code: string; masked_number: string; vpa: string | null;
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
  ratio: number | null; status: "UNDER" | "NEAR" | "OVER" | "NO_BUDGET"; budget_ids: string[];
}
export interface Budgets {
  month: string; lines: BudgetLine[]; total_budget_paise: number; total_actual_paise: number;
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
  result: Record<string, any> | null; error: string | null;
}
export interface Page<T> { items: T[]; next_cursor: string | null }
