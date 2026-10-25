"""add_gross_incomes_table_and_relationships

Revision ID: 8f2a1b9e3c4d
Revises: 6e5717f426aa
Create Date: 2026-09-28 21:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8f2a1b9e3c4d'
down_revision: Union[str, Sequence[str], None] = '6e5717f426aa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Databases bootstrapped by the old startup create_all() may already have this table.
    if not sa.inspect(op.get_bind()).has_table('gross_incomes'):
        op.create_table(
            'gross_incomes',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('title', sa.String(), nullable=False),
            sa.Column('amount', sa.Float(), nullable=False, server_default='0.0'),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_gross_incomes_id'), 'gross_incomes', ['id'], unique=False)

    op.add_column('tax_deductions', sa.Column('gross_income_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_tax_deductions_gross_income_id', 'tax_deductions', 'gross_incomes', ['gross_income_id'], ['id'])
    # Make expense_id nullable in tax_deductions
    op.alter_column('tax_deductions', 'expense_id', existing_type=sa.Integer(), nullable=True)

    op.add_column('expenses', sa.Column('gross_income_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_expenses_gross_income_id', 'expenses', 'gross_incomes', ['gross_income_id'], ['id'])

    op.add_column('medications', sa.Column('gross_income_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_medications_gross_income_id', 'medications', 'gross_incomes', ['gross_income_id'], ['id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('fk_medications_gross_income_id', 'medications', type_='foreignkey')
    op.drop_column('medications', 'gross_income_id')

    op.drop_constraint('fk_expenses_gross_income_id', 'expenses', type_='foreignkey')
    op.drop_column('expenses', 'gross_income_id')

    op.drop_constraint('fk_tax_deductions_gross_income_id', 'tax_deductions', type_='foreignkey')
    op.drop_column('tax_deductions', 'gross_income_id')
    op.alter_column('tax_deductions', 'expense_id', existing_type=sa.Integer(), nullable=False)

    op.drop_index(op.f('ix_gross_incomes_id'), table_name='gross_incomes')
    op.drop_table('gross_incomes')
