"""add_users_email_verified

Revision ID: c1d2e3f4a5b6
Revises: b7c8d9e0f1a2
Create Date: 2026-10-25 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c1d2e3f4a5b6'
down_revision: Union[str, Sequence[str], None] = 'b7c8d9e0f1a2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Existing accounts predate verification: backfill them as verified, then default new rows to unverified.
    op.add_column('users', sa.Column('email_verified', sa.Boolean(), server_default=sa.true(), nullable=False))
    op.alter_column('users', 'email_verified', server_default=sa.false())


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('users', 'email_verified')
