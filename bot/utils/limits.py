# bot/utils/limits.py
"""
Проверка лимитов пользователя.

ВСЕ проверки лимитов — здесь.
Изменение лимитов — в bot/config/pricing.py

Использование:
    from bot.utils.limits import can_create_ad, get_user_limits

    can, reason = await can_create_ad(user, session)
    if not can:
        await message.answer(f"❌ {reason}")
        return
"""

import logging
from datetime import datetime
from typing import Tuple, Dict, Any, Optional, TYPE_CHECKING

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config.pricing import ACCOUNT_TYPES, PAID_SERVICES
from bot.database.models import User, Ad, AdStatus, UserServicePurchase

if TYPE_CHECKING:
    from bot.database.models import User as UserType

logger = logging.getLogger(__name__)


def get_user_limits(user: "UserType") -> Dict[str, Any]:
    """
    Получить лимиты пользователя по его типу аккаунта.

    Возвращает словарь с лимитами из pricing.py
    """
    account_type = user.account_type or "free"

    # Проверяем истёк ли срок подписки
    if account_type != "free" and user.account_until:
        if user.account_until < datetime.utcnow():
            account_type = "free"  # Подписка истекла

    account_config = ACCOUNT_TYPES.get(account_type, ACCOUNT_TYPES["free"])
    return account_config.get("limits", ACCOUNT_TYPES["free"]["limits"])


def get_user_account_info(user: "UserType") -> Dict[str, Any]:
    """
    Получить полную информацию об аккаунте пользователя.
    """
    account_type = user.account_type or "free"
    is_expired = False

    if account_type != "free" and user.account_until:
        if user.account_until < datetime.utcnow():
            is_expired = True
            account_type = "free"

    account_config = ACCOUNT_TYPES.get(account_type, ACCOUNT_TYPES["free"])

    return {
        "type": account_type,
        "name": account_config["name"],
        "emoji": account_config["emoji"],
        "limits": account_config["limits"],
        "features": account_config["features"],
        "is_expired": is_expired,
        "expires_at": user.account_until,
        "extra_ads_limit": user.extra_ads_limit or 0,
    }


async def can_create_ad(user: "UserType", session: AsyncSession) -> Tuple[bool, str]:
    """
    Проверка: может ли пользователь создать объявление?

    >>> ЗДЕСЬ ПРОВЕРЯЕТСЯ ЛИМИТ 100 ОБЪЯВЛЕНИЙ <<<

    Возвращает:
        (True, "") — можно создать
        (False, "причина") — нельзя, с описанием причины
    """
    limits = get_user_limits(user)

    # Считаем активные объявления пользователя
    result = await session.execute(
        select(func.count(Ad.id))
        .where(Ad.user_id == user.telegram_id)
        .where(Ad.status.in_([AdStatus.ACTIVE.value, AdStatus.PENDING.value]))
    )
    active_count = result.scalar() or 0

    # Базовый лимит + докупленные объявления
    max_allowed = limits["max_active_ads"] + (user.extra_ads_limit or 0)

    if active_count >= max_allowed:
        account_info = get_user_account_info(user)
        if account_info["type"] == "free":
            return False, (
                f"Достигнут лимит объявлений ({max_allowed}).\n"
                f"Оформите подписку PRO или Бизнес для увеличения лимита."
            )
        else:
            return False, (
                f"Достигнут лимит объявлений ({max_allowed}).\n"
                f"Вы можете докупить дополнительные слоты."
            )

    return True, ""


async def can_add_region(
    user: "UserType",
    ad: Ad,
    session: AsyncSession
) -> Tuple[bool, str]:
    """
    Может ли добавить дополнительный регион к объявлению?

    Возвращает:
        (True, "") — можно бесплатно
        (False, "requires_payment") — нужна оплата
        (False, "причина") — нельзя
    """
    limits = get_user_limits(user)

    # Считаем текущие регионы (пока 1, но подготовка к мультирегиону)
    current_regions = 1  # TODO: ad.regions когда будет мультирегион
    max_free_regions = limits["max_regions_per_ad"]

    # Проверяем купленные доп. регионы для этого объявления
    result = await session.execute(
        select(func.sum(UserServicePurchase.quantity))
        .where(UserServicePurchase.ad_id == ad.id)
        .where(UserServicePurchase.service_code == "ad_multiregion")
        .where(UserServicePurchase.is_active == True)
    )
    purchased_regions = result.scalar() or 0

    total_allowed = max_free_regions + purchased_regions

    if current_regions >= total_allowed:
        return False, "requires_payment"

    return True, ""


async def can_add_link(
    user: "UserType",
    ad: Optional[Ad] = None,
    current_links_count: int = 0,
    session: Optional[AsyncSession] = None
) -> Tuple[bool, str]:
    """
    Может ли добавить ссылку к объявлению?

    Возвращает:
        (True, "") — можно бесплатно
        (False, "requires_payment") — нужна оплата за доп. ссылку
    """
    limits = get_user_limits(user)
    max_free_links = limits["max_links_per_ad"]

    # Считаем текущие ссылки
    if ad and ad.links:
        current_links_count = len(ad.links)

    # Проверяем купленные доп. ссылки
    purchased_links = 0
    if ad and session:
        result = await session.execute(
            select(func.sum(UserServicePurchase.quantity))
            .where(UserServicePurchase.ad_id == ad.id)
            .where(UserServicePurchase.service_code == "ad_extra_link")
            .where(UserServicePurchase.is_active == True)
        )
        purchased_links = result.scalar() or 0

    total_allowed = max_free_links + purchased_links

    if current_links_count >= total_allowed:
        return False, "requires_payment"

    return True, ""


async def can_add_video(
    user: "UserType",
    ad: Optional[Ad] = None,
    session: Optional[AsyncSession] = None
) -> Tuple[bool, str]:
    """
    Может ли добавить видео к объявлению?

    Возвращает:
        (True, "") — можно (включено в подписку или куплено)
        (False, "requires_payment") — нужна оплата
    """
    limits = get_user_limits(user)

    # Проверяем включено ли видео в подписку
    if limits["video_allowed"]:
        return True, ""

    # Проверяем куплена ли услуга для этого объявления
    if ad and session:
        result = await session.execute(
            select(UserServicePurchase)
            .where(UserServicePurchase.ad_id == ad.id)
            .where(UserServicePurchase.service_code == "ad_video")
            .where(UserServicePurchase.is_active == True)
        )
        if result.scalar_one_or_none():
            return True, ""

    return False, "requires_payment"


async def can_add_photos(
    user: "UserType",
    current_photos_count: int = 0
) -> Tuple[bool, int]:
    """
    Может ли добавить ещё фото? Сколько?

    Возвращает:
        (True, remaining) — можно, осталось remaining
        (False, 0) — лимит исчерпан
    """
    limits = get_user_limits(user)
    max_photos = limits["max_photos_per_ad"]
    remaining = max_photos - current_photos_count

    if remaining <= 0:
        return False, 0

    return True, remaining


def get_ad_duration_days(user: "UserType") -> int:
    """
    Получить срок публикации объявления для пользователя (в днях).
    """
    limits = get_user_limits(user)
    return limits["ad_duration_days"]


async def check_service_availability(
    user: "UserType",
    service_code: str,
    ad: Optional[Ad] = None,
    session: Optional[AsyncSession] = None
) -> Tuple[bool, str, Optional[float]]:
    """
    Проверить доступность услуги для пользователя.

    Возвращает:
        (True, "", price) — услуга доступна, цена в рублях
        (True, "included", 0) — услуга включена в подписку бесплатно
        (False, "причина", None) — услуга недоступна
    """
    service = PAID_SERVICES.get(service_code)
    if not service:
        return False, "Услуга не найдена", None

    if not service.get("is_active"):
        return False, "Услуга временно недоступна", None

    limits = get_user_limits(user)
    price = service["price_rub"]

    # Проверки для специфических услуг
    if service_code == "ad_video":
        if limits["video_allowed"]:
            return True, "included", 0

    if service_code == "ad_extra_link":
        can, reason = await can_add_link(user, ad, session=session)
        if can:
            return True, "included", 0

    if service_code == "ad_multiregion":
        can, reason = await can_add_region(user, ad, session)
        if can:
            return True, "included", 0

    return True, "", price


def format_limits_info(user: "UserType") -> str:
    """
    Форматирование информации о лимитах для отображения пользователю.
    """
    info = get_user_account_info(user)
    limits = info["limits"]

    lines = [
        f"{info['emoji']} Аккаунт: {info['name']}",
    ]

    if info["expires_at"] and info["type"] != "free":
        if info["is_expired"]:
            lines.append("⚠️ Подписка истекла")
        else:
            lines.append(f"📅 Активна до: {info['expires_at'].strftime('%d.%m.%Y')}")

    lines.extend([
        "",
        "📊 Лимиты:",
        f"• Объявлений: {limits['max_active_ads']} + {info['extra_ads_limit']} доп.",
        f"• Срок публикации: {limits['ad_duration_days']} дней",
        f"• Регионов: {limits['max_regions_per_ad']}",
        f"• Ссылок: {limits['max_links_per_ad']}",
        f"• Фото: {limits['max_photos_per_ad']}",
        f"• Видео: {'✅' if limits['video_allowed'] else '❌ (платно)'}",
    ])

    return "\n".join(lines)
