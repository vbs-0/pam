"""Idempotency keys: a write the phone queued offline can be sent again after a dropped connection and is applied once.

Revision ID: 0005
Revises: 0004
"""
from alembic import op

revision = "0005"
down_revision = "0004"


def upgrade() -> None:
    op.execute("""CREATE TABLE idempotency_key (
        key char(64) PRIMARY KEY, status smallint NOT NULL, body bytea NOT NULL,
        content_type varchar(80) NOT NULL DEFAULT 'application/json', created_at timestamptz NOT NULL DEFAULT now())""")
    op.execute("CREATE INDEX ix_idempotency_created ON idempotency_key (created_at)")


def downgrade() -> None:
    op.execute("DROP TABLE idempotency_key")
