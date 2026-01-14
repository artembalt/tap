"""Add link_title and link_url fields to ads table

Revision ID: 20260114_link
Revises:
Create Date: 2026-01-14
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = '20260114_link'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    """Add link_title and link_url columns to ads table"""
    op.add_column('ads', sa.Column('link_title', sa.String(100), nullable=True))
    op.add_column('ads', sa.Column('link_url', sa.String(500), nullable=True))


def downgrade():
    """Remove link_title and link_url columns from ads table"""
    op.drop_column('ads', 'link_url')
    op.drop_column('ads', 'link_title')
