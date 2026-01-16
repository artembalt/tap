"""Migrate link_title/link_url to links JSONB array

Revision ID: 20260116_links
Revises: 9fdb05a48fe3
Create Date: 2026-01-16
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers
revision = '20260116_links'
down_revision = '9fdb05a48fe3'
branch_labels = None
depends_on = None


def upgrade():
    """Migrate to links JSONB array"""
    # 1. Добавляем новое поле links
    op.add_column('ads', sa.Column('links', JSONB, server_default='[]', nullable=True))

    # 2. Мигрируем существующие данные (link_title + link_url -> links)
    op.execute("""
        UPDATE ads
        SET links = jsonb_build_array(
            jsonb_build_object('title', link_title, 'url', link_url)
        )
        WHERE link_title IS NOT NULL AND link_url IS NOT NULL
    """)

    # 3. Устанавливаем пустой массив где links is null
    op.execute("UPDATE ads SET links = '[]'::jsonb WHERE links IS NULL")

    # 4. Удаляем старые поля
    op.drop_column('ads', 'link_title')
    op.drop_column('ads', 'link_url')


def downgrade():
    """Rollback to link_title/link_url"""
    # 1. Добавляем старые поля обратно
    op.add_column('ads', sa.Column('link_title', sa.String(100), nullable=True))
    op.add_column('ads', sa.Column('link_url', sa.String(500), nullable=True))

    # 2. Мигрируем данные обратно (берём первую ссылку из массива)
    op.execute("""
        UPDATE ads
        SET link_title = links->0->>'title',
            link_url = links->0->>'url'
        WHERE jsonb_array_length(links) > 0
    """)

    # 3. Удаляем поле links
    op.drop_column('ads', 'links')
