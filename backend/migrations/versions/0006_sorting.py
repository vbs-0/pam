"""Your own sorting rules ("remember my choice") and optional AI suggestions.

Revision ID: 0006
Revises: 0005
"""
from alembic import op

revision = "0006"
down_revision = "0005"


def upgrade() -> None:
    op.execute("""CREATE TABLE user_rule (
        rule_id varchar(24) PRIMARY KEY, user_id varchar(32) NOT NULL, phrase varchar(60) NOT NULL,
        direction char(2) NOT NULL CHECK (direction IN ('DR', 'CR')), category_code varchar(40) NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now(), UNIQUE (user_id, phrase, direction))""")
    op.execute("CREATE INDEX ix_user_rule_user ON user_rule (user_id)")
    op.execute("""CREATE TABLE user_ai (
        user_id varchar(32) PRIMARY KEY, enabled boolean NOT NULL DEFAULT false, updated_at timestamptz NOT NULL DEFAULT now())""")
    op.execute("""CREATE TABLE ai_cache (
        key char(64) PRIMARY KEY, category_code varchar(40) NOT NULL, confidence real NOT NULL, model varchar(60) NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now())""")


def downgrade() -> None:
    for t in ("ai_cache", "user_ai", "user_rule"):
        op.execute(f"DROP TABLE {t}")
