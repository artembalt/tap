"""Add boost and notification fields to ads table

Revision ID: 20260121_boost
Revises: 20260120_archive
Create Date: 2026-01-21
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers
revision = '20260121_boost'
down_revision = '20260120_archive'
branch_labels = None
depends_on = None


def upgrade():
    """Add boost and notification columns to ads table"""
    # Поля для автоподнятия
    op.add_column('ads', sa.Column('boost_service', sa.String(50), nullable=True))
    op.add_column('ads', sa.Column('boost_remaining', sa.Integer(), server_default='0', nullable=True))
    op.add_column('ads', sa.Column('next_boost_at', sa.DateTime(), nullable=True))

    # Поля для продления и уведомлений
    op.add_column('ads', sa.Column('last_extended_at', sa.DateTime(), nullable=True))
    op.add_column('ads', sa.Column('notifications_sent', JSONB, server_default='{}', nullable=True))

    # Индекс для поиска объявлений с автоподнятием
    op.create_index('idx_ad_next_boost', 'ads', ['next_boost_at'])


def downgrade():
    """Remove boost and notification columns from ads table"""
    op.drop_index('idx_ad_next_boost', table_name='ads')
    op.drop_column('ads', 'notifications_sent')
    op.drop_column('ads', 'last_extended_at')
    op.drop_column('ads', 'next_boost_at')
    op.drop_column('ads', 'boost_remaining')
    op.drop_column('ads', 'boost_service')
