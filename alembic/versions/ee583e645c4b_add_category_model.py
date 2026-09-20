"""Add category model

Revision ID: ee583e645c4b
Revises: 3341dc869d14
Create Date: 2026-09-21 00:54:21.134912

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'ee583e645c4b'
down_revision: Union[str, Sequence[str], None] = '3341dc869d14'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()

    if 'categories' not in tables:
        op.create_table(
            'categories',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('title', sa.String(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['user_id'], ['users.id']),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index(op.f('ix_categories_id'), 'categories', ['id'], unique=False)

    columns_expenses = [c['name'] for c in inspector.get_columns('expenses')]
    if 'category_id' not in columns_expenses:
        op.add_column('expenses', sa.Column('category_id', sa.Integer(), nullable=True))
        op.create_foreign_key('fk_expenses_category_id_categories', 'expenses', 'categories', ['category_id'], ['id'])

    columns_medications = [c['name'] for c in inspector.get_columns('medications')]
    if 'category_id' not in columns_medications:
        op.add_column('medications', sa.Column('category_id', sa.Integer(), nullable=True))
        op.create_foreign_key('fk_medications_category_id_categories', 'medications', 'categories', ['category_id'], ['id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('fk_medications_category_id_categories', 'medications', type_='foreignkey')
    op.drop_column('medications', 'category_id')
    op.drop_constraint('fk_expenses_category_id_categories', 'expenses', type_='foreignkey')
    op.drop_column('expenses', 'category_id')
    op.drop_index(op.f('ix_categories_id'), table_name='categories')
    op.drop_table('categories')
