"""Per-user extras: entry notes and tags, card dates, savings goals, budget carry-over, email digest preferences, and
household invites.

None of these tables is part of the dataset schema and none has a foreign key: a dataset reload (which truncates the
sample tables) leaves them alone, and rows for a household that no longer exists are harmless.

Revision ID: 0004
Revises: 0003
"""
from alembic import op

revision = "0004"
down_revision = "0003"


def upgrade() -> None:
    op.execute("""CREATE TABLE txn_note (
        txn_id varchar(32) PRIMARY KEY, user_id varchar(32) NOT NULL, note varchar(300) NOT NULL DEFAULT '',
        tags text[] NOT NULL DEFAULT '{}', updated_at timestamptz NOT NULL DEFAULT now())""")
    op.execute("CREATE INDEX ix_txn_note_user ON txn_note (user_id)")
    op.execute("""CREATE TABLE account_meta (
        account_id varchar(32) PRIMARY KEY, due_day smallint CHECK (due_day BETWEEN 1 AND 31),
        statement_day smallint CHECK (statement_day BETWEEN 1 AND 31))""")
    op.execute("""CREATE TABLE goal (
        goal_id varchar(40) PRIMARY KEY, user_id varchar(32) NOT NULL, name varchar(60) NOT NULL,
        target_paise bigint NOT NULL CHECK (target_paise > 0), saved_paise bigint NOT NULL DEFAULT 0 CHECK (saved_paise >= 0),
        deadline date, created_at timestamptz NOT NULL DEFAULT now(), completed_at timestamptz)""")
    op.execute("CREATE INDEX ix_goal_user ON goal (user_id)")
    op.execute("""CREATE TABLE budget_carry (
        user_id varchar(32) NOT NULL, category_code varchar(40) NOT NULL, PRIMARY KEY (user_id, category_code))""")
    op.execute("""CREATE TABLE notify_pref (
        app_user_id varchar(32) PRIMARY KEY, email_digest boolean NOT NULL DEFAULT false,
        bills boolean NOT NULL DEFAULT true, budgets boolean NOT NULL DEFAULT true, cards boolean NOT NULL DEFAULT true,
        last_sent_on date)""")
    op.execute("CREATE TABLE digest_run (day date PRIMARY KEY, sent integer NOT NULL DEFAULT 0, at timestamptz NOT NULL DEFAULT now())")
    op.execute("""CREATE TABLE household_invite (
        code varchar(12) PRIMARY KEY, household_id varchar(32) NOT NULL, created_by varchar(32) NOT NULL,
        expires_at timestamptz NOT NULL, used_by varchar(32), used_at timestamptz)""")


def downgrade() -> None:
    for t in ("household_invite", "digest_run", "notify_pref", "budget_carry", "goal", "account_meta", "txn_note"):
        op.execute(f"DROP TABLE {t}")
