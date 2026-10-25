"""add_audit_logs_and_fk_indexes

Revision ID: d4e5f6a7b8c9
Revises: c1d2e3f4a5b6
Create Date: 2026-10-25 13:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, Sequence[str], None] = 'c1d2e3f4a5b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Postgres does not index foreign keys automatically; every list/eager-load query filters on these.
FK_INDEXES = [
    ('categories', 'user_id'),
    ('gross_incomes', 'user_id'),
    ('expenses', 'user_id'),
    ('expenses', 'category_id'),
    ('expenses', 'gross_income_id'),
    ('expense_items', 'expense_id'),
    ('savings', 'user_id'),
    ('savings', 'expense_id'),
    ('saving_items', 'saving_id'),
    ('tax_deductions', 'expense_id'),
    ('tax_deductions', 'gross_income_id'),
    ('medications', 'user_id'),
    ('medications', 'category_id'),
    ('medications', 'gross_income_id'),
]


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'audit_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('actor_user_id', sa.Integer(), nullable=True),
        sa.Column('action', sa.String(), nullable=False),
        sa.Column('target_type', sa.String(), nullable=True),
        sa.Column('target_id', sa.String(), nullable=True),
        sa.Column('details', sa.JSON(), nullable=True),
        sa.Column('ip', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_audit_logs_id'), 'audit_logs', ['id'], unique=False)
    op.create_index(op.f('ix_audit_logs_actor_user_id'), 'audit_logs', ['actor_user_id'], unique=False)
    op.create_index(op.f('ix_audit_logs_action'), 'audit_logs', ['action'], unique=False)
    op.create_index(op.f('ix_audit_logs_created_at'), 'audit_logs', ['created_at'], unique=False)

    for table, column in FK_INDEXES:
        op.create_index(op.f(f'ix_{table}_{column}'), table, [column], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    for table, column in FK_INDEXES:
        op.drop_index(op.f(f'ix_{table}_{column}'), table_name=table)

    op.drop_index(op.f('ix_audit_logs_created_at'), table_name='audit_logs')
    op.drop_index(op.f('ix_audit_logs_action'), table_name='audit_logs')
    op.drop_index(op.f('ix_audit_logs_actor_user_id'), table_name='audit_logs')
    op.drop_index(op.f('ix_audit_logs_id'), table_name='audit_logs')
    op.drop_table('audit_logs')
