"""UPI app accounts (Paytm, PhonePe, Google Pay, BHIM, Amazon Pay, or a custom name) and a display label.

account_label is deliberately outside the dataset schema and has no foreign key: the sample dataset, its CSVs and a
dataset reload (which truncates account) are unaffected, and a custom name survives a reload like the account does.

Revision ID: 0003
Revises: 0002
"""
from alembic import op

revision = "0003"
down_revision = "0002"

OLD_BANKS = "'SBIN', 'HDFC', 'ICIC', 'UTIB', 'KKBK', 'BARB', 'PUNB', 'CNRB', 'OTHR'"
NEW_BANKS = OLD_BANKS + ", 'PTYM', 'PHPE', 'GPAY', 'BHIM', 'AMZN'"


def _allow(types: str, banks: str) -> None:
    # raw SQL: the metadata naming convention would prefix a name passed to op.drop_constraint a second time
    op.execute("ALTER TABLE account DROP CONSTRAINT ck_account_account_type_allowed")
    op.execute(f"ALTER TABLE account ADD CONSTRAINT ck_account_account_type_allowed CHECK (account_type IN ({types}))")
    op.execute("ALTER TABLE account DROP CONSTRAINT ck_account_bank_code_allowed")
    op.execute(f"ALTER TABLE account ADD CONSTRAINT ck_account_bank_code_allowed CHECK (bank_code IN ({banks}))")


def upgrade() -> None:
    _allow("'SAVINGS', 'CREDIT_CARD', 'UPI'", NEW_BANKS)
    op.execute("CREATE TABLE account_label (account_id varchar(32) PRIMARY KEY, label varchar(40) NOT NULL)")
    op.execute("COMMENT ON TABLE account_label IS 'Name a user gave an account (required for a custom UPI app).'")


def downgrade() -> None:
    op.execute("DROP TABLE account_label")
    op.execute("DELETE FROM account WHERE account_type = 'UPI' OR bank_code IN ('PTYM', 'PHPE', 'GPAY', 'BHIM', 'AMZN')")
    _allow("'SAVINGS', 'CREDIT_CARD'", OLD_BANKS)
