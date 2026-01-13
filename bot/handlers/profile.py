# bot/handlers/profile.py
"""Профиль пользователя - исправленная версия"""

import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery

from bot.database.queries import UserQueries, AdQueries, FavoritesQueries
from bot.database.connection import get_db_session
from bot.database.models import Ad, AdStatus, ad_favorites
from sqlalchemy import select, func

logger = logging.getLogger(__name__)
router = Router(name='profile')


async def get_user_stats(user_id: int) -> dict:
    """Получить реальную статистику пользователя из БД"""
    try:
        async with get_db_session() as session:
            # Количество объявлений пользователя
            ads_count_stmt = select(func.count(Ad.id)).where(
                Ad.user_id == user_id,
                Ad.status.in_([AdStatus.ACTIVE.value, AdStatus.PENDING.value, AdStatus.ARCHIVED.value])
            )
            ads_result = await session.execute(ads_count_stmt)
            ads_count = ads_result.scalar() or 0

            # Суммарные просмотры всех объявлений пользователя
            views_stmt = select(func.coalesce(func.sum(Ad.views_count), 0)).where(
                Ad.user_id == user_id,
                Ad.status != AdStatus.DELETED.value
            )
            views_result = await session.execute(views_stmt)
            views_count = views_result.scalar() or 0

            # Сколько раз объявления пользователя добавлены в избранное
            favorites_stmt = select(func.coalesce(func.sum(Ad.favorites_count), 0)).where(
                Ad.user_id == user_id,
                Ad.status != AdStatus.DELETED.value
            )
            favorites_result = await session.execute(favorites_stmt)
            favorites_count = favorites_result.scalar() or 0

            return {
                "ads_count": ads_count,
                "views_count": int(views_count),
                "favorites_count": int(favorites_count)
            }
    except Exception as e:
        logger.error(f"Ошибка получения статистики: {e}")
        return {"ads_count": 0, "views_count": 0, "favorites_count": 0}


@router.message(F.text == "👤 Профиль")
async def profile(message: Message):
    """Показать профиль текущего пользователя"""
    user_id = message.from_user.id

    # Получаем данные пользователя из БД
    user = await UserQueries.get_user(user_id)

    # Получаем статистику
    stats = await get_user_stats(user_id)

    # Имя из БД или из Telegram
    if user and user.first_name:
        name = user.first_name
        if user.last_name:
            name += f" {user.last_name}"
    else:
        name = message.from_user.first_name or "Не указано"
        if message.from_user.last_name:
            name += f" {message.from_user.last_name}"

    # Username
    if user and user.username:
        username = f"@{user.username}"
    elif message.from_user.username:
        username = f"@{message.from_user.username}"
    else:
        username = "не указан"

    user_info = f"""
👤 <b>Ваш профиль</b>

🆔 ID: <code>{user_id}</code>
📛 Имя: {name}
👤 Username: {username}

📊 <b>Статистика:</b>
• Объявлений: {stats['ads_count']}
• Просмотров: {stats['views_count']}
• В избранном: {stats['favorites_count']}
"""
    await message.answer(user_info)


@router.callback_query(F.data == "profile")
async def callback_profile(callback: CallbackQuery):
    """Показать профиль через callback"""
    user_id = callback.from_user.id

    # Получаем данные пользователя из БД
    user = await UserQueries.get_user(user_id)

    # Получаем статистику
    stats = await get_user_stats(user_id)

    # Имя из БД или из Telegram
    if user and user.first_name:
        name = user.first_name
        if user.last_name:
            name += f" {user.last_name}"
    else:
        name = callback.from_user.first_name or "Не указано"
        if callback.from_user.last_name:
            name += f" {callback.from_user.last_name}"

    # Username
    if user and user.username:
        username = f"@{user.username}"
    elif callback.from_user.username:
        username = f"@{callback.from_user.username}"
    else:
        username = "не указан"

    user_info = f"""
👤 <b>Ваш профиль</b>

🆔 ID: <code>{user_id}</code>
📛 Имя: {name}
👤 Username: {username}

📊 <b>Статистика:</b>
• Объявлений: {stats['ads_count']}
• Просмотров: {stats['views_count']}
• В избранном: {stats['favorites_count']}
"""
    try:
        await callback.message.edit_text(user_info)
    except:
        await callback.message.answer(user_info)
    await callback.answer()
