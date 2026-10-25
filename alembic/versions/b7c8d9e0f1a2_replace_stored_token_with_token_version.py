"""replace_stored_token_with_token_version

Revision ID: b7c8d9e0f1a2
Revises: 9a1b2c3d4e5f
Create Date: 2026-10-25 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7c8d9e0f1a2'
down_revision: Union[str, Sequence[str], None] = '9a1b2c3d4e5f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('users', sa.Column('token_version', sa.Integer(), server_default='0', nullable=False))
    op.drop_column('users', 'token')


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column('users', sa.Column('token', sa.String(), nullable=True))
    op.drop_column('users', 'token_version')
