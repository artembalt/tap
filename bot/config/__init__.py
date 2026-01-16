# bot/config/__init__.py
"""Конфигурация бота"""

# Основные настройки (из settings.py)
from bot.config.settings import settings, Settings

# Ценообразование и подписки (из pricing.py)
from bot.config.pricing import (
    ACCOUNT_TYPES,
    PAID_SERVICES,
    STARS_CONFIG,
    PROMO_TYPES,
    SERVICE_CATEGORIES,
    get_service_price,
    get_account_limits,
    get_active_services,
    get_subscription_price,
)
