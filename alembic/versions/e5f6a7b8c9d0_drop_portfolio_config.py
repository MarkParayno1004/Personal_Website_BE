"""drop_portfolio_config

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-10-28 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, Sequence[str], None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Portfolio content now ships as static data in the client project.
    op.drop_index(op.f('ix_portfolio_config_id'), table_name='portfolio_config')
    op.drop_table('portfolio_config')


def downgrade() -> None:
    """Downgrade schema."""
    op.create_table('portfolio_config',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('full_name', sa.String(), nullable=False),
    sa.Column('headline', sa.String(), nullable=False),
    sa.Column('location', sa.String(), nullable=False),
    sa.Column('phone', sa.String(), nullable=False),
    sa.Column('email', sa.String(), nullable=False),
    sa.Column('linkedin_url', sa.String(), nullable=False),
    sa.Column('github_username', sa.String(), nullable=False),
    sa.Column('about_summary', sa.String(), nullable=False),
    sa.Column('skills', sa.JSON(), nullable=True),
    sa.Column('experience', sa.JSON(), nullable=True),
    sa.Column('education', sa.JSON(), nullable=True),
    sa.Column('theme_config', sa.JSON(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.Column('cv_url', sa.String(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_portfolio_config_id'), 'portfolio_config', ['id'], unique=False)
