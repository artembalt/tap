"""Add archive fields to ads table for ad lifecycle management

Revision ID: 20260120_archive
Revises: 20260114_link
Create Date: 2026-01-20
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers
revision = '20260120_archive'
down_revision = 'be9d931bd0d2'  # current head
branch_labels = None
depends_on = None


def upgrade():
    """Add archive-related columns to ads table"""
    # Поля для архивного канала
    op.add_column('ads', sa.Column('archive_message_ids', JSONB, server_default='{}', nullable=True))
    op.add_column('ads', sa.Column('archived_to_channel_at', sa.DateTime(), nullable=True))
    op.add_column('ads', sa.Column('republish_count', sa.Integer(), server_default='0', nullable=True))
    op.add_column('ads', sa.Column('last_republished_at', sa.DateTime(), nullable=True))

    # Индекс для поиска старых архивных объявлений
    op.create_index('idx_ad_archived_to_channel', 'ads', ['archived_to_channel_at'])


def downgrade():
    """Remove archive-related columns from ads table"""
    op.drop_index('idx_ad_archived_to_channel', table_name='ads')
    op.drop_column('ads', 'last_republished_at')
    op.drop_column('ads', 'republish_count')
    op.drop_column('ads', 'archived_to_channel_at')
    op.drop_column('ads', 'archive_message_ids')
