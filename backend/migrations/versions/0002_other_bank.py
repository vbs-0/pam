"""Real households can hold accounts at banks outside the synthetic set (bank_code OTHR).

Revision ID: 0002
Revises: 0001
"""
from alembic import op

revision = "0002"
down_revision = "0001"

OLD = "'SBIN', 'HDFC', 'ICIC', 'UTIB', 'KKBK', 'BARB', 'PUNB', 'CNRB'"


def _allow(codes: str) -> None:
    # raw SQL: the metadata naming convention would prefix a name passed to op.drop_constraint a second time
    op.execute("ALTER TABLE account DROP CONSTRAINT ck_account_bank_code_allowed")
    op.execute(f"ALTER TABLE account ADD CONSTRAINT ck_account_bank_code_allowed CHECK (bank_code IN ({codes}))")


def upgrade() -> None:
    _allow(f"{OLD}, 'OTHR'")


def downgrade() -> None:
    _allow(OLD)
