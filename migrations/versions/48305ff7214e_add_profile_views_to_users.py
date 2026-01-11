"""add_profile_views_to_users

Revision ID: 48305ff7214e
Revises: 261093b4522f
Create Date: 2026-01-11 19:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '48305ff7214e'
down_revision: Union[str, None] = '261093b4522f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('profile_views', sa.Integer(), nullable=True, server_default='0'))


def downgrade() -> None:
    op.drop_column('users', 'profile_views')
