# bot/handlers/favorites.py
"""Обработчик избранного - просмотр и управление"""

import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from bot.database.queries import FavoritesQueries, AdQueries
from bot.database.connection import get_db_session
from bot.database.models import Ad, AdStatus
from sqlalchemy import select
from shared.regions_config import CHANNELS_CONFIG

logger = logging.getLogger(__name__)
router = Router(name='favorites')

# Количество объявлений на странице
FAVORITES_PER_PAGE = 50


def get_favorites_keyboard(favorites: list, offset: int, total: int) -> InlineKeyboardMarkup:
    """Клавиатура со списком избранного"""
    buttons = []

    # Кликабельные заголовки объявлений
    for ad in favorites:
        # Формируем ссылку на объявление в канале
        link = get_ad_link(ad)
        title = ad.title[:40] + "..." if len(ad.title) > 40 else ad.title

        if link:
            buttons.append([InlineKeyboardButton(text=f"📌 {title}", url=link)])
        else:
            # Если ссылка недоступна, показываем кнопку для удаления из избранного
            buttons.append([InlineKeyboardButton(
                text=f"📌 {title}",
                callback_data=f"fav_view_{ad.id}"
            )])

    # Кнопка "Показать следующие" если есть ещё
    if offset + FAVORITES_PER_PAGE < total:
        remaining = total - offset - FAVORITES_PER_PAGE
        next_count = min(remaining, FAVORITES_PER_PAGE)
        buttons.append([
            InlineKeyboardButton(
                text=f"📄 Показать следующие {next_count}",
                callback_data=f"favorites_page_{offset + FAVORITES_PER_PAGE}"
            )
        ])

    # Кнопка назад
    buttons.append([
        InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_ad_link(ad: Ad) -> str:
    """Получить ссылку на объявление в канале"""
    if not ad.channel_message_ids:
        return ""

    region = ad.region
    category = ad.category

    # Ищем канал категории
    channel_config = CHANNELS_CONFIG.get(region, {})
    category_channel = channel_config.get('categories', {}).get(category, '')

    if category_channel and category_channel in ad.channel_message_ids:
        msg_id = ad.channel_message_ids[category_channel]
        channel_username = category_channel.replace("@", "")
        return f"https://t.me/{channel_username}/{msg_id}"

    # Если нет канала категории, ищем основной канал
    main_channel = channel_config.get('main', '')
    if main_channel and main_channel in ad.channel_message_ids:
        msg_id = ad.channel_message_ids[main_channel]
        channel_username = main_channel.replace("@", "")
        return f"https://t.me/{channel_username}/{msg_id}"

    return ""


async def get_user_favorites_with_count(user_id: int, limit: int = 50, offset: int = 0):
    """Получить избранное с подсчетом общего количества"""
    try:
        async with get_db_session() as session:
            # Получаем избранные объявления пользователя
            from bot.database.models import ad_favorites, User

            # Подсчет общего количества
            from sqlalchemy import func
            count_stmt = (
                select(func.count())
                .select_from(ad_favorites)
                .join(Ad, Ad.id == ad_favorites.c.ad_id)
                .where(
                    ad_favorites.c.user_id == user_id,
                    Ad.status == AdStatus.ACTIVE.value
                )
            )
            count_result = await session.execute(count_stmt)
            total = count_result.scalar() or 0

            # Получаем объявления
            stmt = (
                select(Ad)
                .join(ad_favorites, Ad.id == ad_favorites.c.ad_id)
                .where(
                    ad_favorites.c.user_id == user_id,
                    Ad.status == AdStatus.ACTIVE.value
                )
                .order_by(ad_favorites.c.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
            result = await session.execute(stmt)
            favorites = list(result.scalars().all())

            return favorites, total
    except Exception as e:
        logger.error(f"Ошибка получения избранного: {e}")
        return [], 0


@router.message(F.text == "⭐ Избранное")
async def show_favorites(message: Message):
    """Показать список избранного"""
    user_id = message.from_user.id
    logger.info(f"[FAVORITES] show, user={user_id}")

    favorites, total = await get_user_favorites_with_count(user_id, limit=FAVORITES_PER_PAGE, offset=0)

    if not favorites:
        await message.answer(
            "⭐ <b>Избранное пусто</b>\n\n"
            "Добавляйте объявления в избранное, нажимая кнопку "
            "«⭐ В избранное» под объявлениями в каналах."
        )
        return

    text = f"⭐ <b>Избранное</b> ({total} шт.)\n\n"
    text += "Нажмите на заголовок, чтобы перейти к объявлению:"

    keyboard = get_favorites_keyboard(favorites, offset=0, total=total)
    await message.answer(text, reply_markup=keyboard)


@router.callback_query(F.data.startswith("favorites_page_"))
async def favorites_page(callback: CallbackQuery):
    """Следующая страница избранного"""
    offset = int(callback.data.replace("favorites_page_", ""))
    user_id = callback.from_user.id

    logger.info(f"[FAVORITES] page, user={user_id}, offset={offset}")

    favorites, total = await get_user_favorites_with_count(user_id, limit=FAVORITES_PER_PAGE, offset=offset)

    text = f"⭐ <b>Избранное</b> ({total} шт.)\n\n"
    text += "Нажмите на заголовок, чтобы перейти к объявлению:"

    keyboard = get_favorites_keyboard(favorites, offset=offset, total=total)

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except:
        await callback.message.answer(text, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("fav_view_"))
async def view_favorite_ad(callback: CallbackQuery):
    """Просмотр объявления из избранного (если ссылка недоступна)"""
    ad_id = callback.data.replace("fav_view_", "")
    user_id = callback.from_user.id

    logger.info(f"[FAVORITES] view, user={user_id}, ad_id={ad_id}")

    ad = await AdQueries.get_ad(ad_id)
    if not ad:
        await callback.answer("❌ Объявление не найдено", show_alert=True)
        return

    # Показываем краткую информацию
    price_text = ad.premium_features.get('price_text', 'Не указана') if ad.premium_features else 'Не указана'

    text = f"""📌 <b>{ad.title}</b>

{ad.description[:300]}{'...' if len(ad.description) > 300 else ''}

💰 {price_text}
"""

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="❌ Удалить из избранного",
            callback_data=f"fav_remove_{ad_id}"
        )],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="favorites_back")]
    ])

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except:
        await callback.message.answer(text, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("fav_remove_"))
async def remove_from_favorites(callback: CallbackQuery):
    """Удалить из избранного"""
    ad_id = callback.data.replace("fav_remove_", "")
    user_id = callback.from_user.id

    logger.info(f"[FAVORITES] remove, user={user_id}, ad_id={ad_id}")

    success = await FavoritesQueries.remove_from_favorites(user_id, ad_id)

    if success:
        await callback.answer("✅ Удалено из избранного", show_alert=False)
        # Возвращаемся к списку
        favorites, total = await get_user_favorites_with_count(user_id, limit=FAVORITES_PER_PAGE, offset=0)

        if not favorites:
            await callback.message.edit_text(
                "⭐ <b>Избранное пусто</b>\n\n"
                "Добавляйте объявления в избранное, нажимая кнопку "
                "«⭐ В избранное» под объявлениями в каналах."
            )
        else:
            text = f"⭐ <b>Избранное</b> ({total} шт.)\n\n"
            text += "Нажмите на заголовок, чтобы перейти к объявлению:"
            keyboard = get_favorites_keyboard(favorites, offset=0, total=total)
            await callback.message.edit_text(text, reply_markup=keyboard)
    else:
        await callback.answer("❌ Ошибка удаления", show_alert=True)


@router.callback_query(F.data == "favorites_back")
async def favorites_back(callback: CallbackQuery):
    """Вернуться к списку избранного"""
    user_id = callback.from_user.id

    favorites, total = await get_user_favorites_with_count(user_id, limit=FAVORITES_PER_PAGE, offset=0)

    if not favorites:
        await callback.message.edit_text(
            "⭐ <b>Избранное пусто</b>\n\n"
            "Добавляйте объявления в избранное, нажимая кнопку "
            "«⭐ В избранное» под объявлениями в каналах."
        )
    else:
        text = f"⭐ <b>Избранное</b> ({total} шт.)\n\n"
        text += "Нажмите на заголовок, чтобы перейти к объявлению:"
        keyboard = get_favorites_keyboard(favorites, offset=0, total=total)
        await callback.message.edit_text(text, reply_markup=keyboard)

    await callback.answer()


# =============================================================================
# ДОБАВЛЕНИЕ В ИЗБРАННОЕ (из каналов)
# =============================================================================

@router.callback_query(F.data.startswith("add_fav_"))
async def add_to_favorites(callback: CallbackQuery):
    """Добавить объявление в избранное (callback из канала)"""
    ad_id = callback.data.replace("add_fav_", "")
    user_id = callback.from_user.id

    logger.info(f"[FAVORITES] add, user={user_id}, ad_id={ad_id}")

    # Проверяем, есть ли уже в избранном
    is_favorite = await FavoritesQueries.is_in_favorites(user_id, ad_id)

    if is_favorite:
        # Удаляем из избранного
        success = await FavoritesQueries.remove_from_favorites(user_id, ad_id)
        if success:
            await callback.answer("❌ Удалено из избранного", show_alert=False)
        else:
            await callback.answer("❌ Ошибка", show_alert=True)
    else:
        # Добавляем в избранное
        success = await FavoritesQueries.add_to_favorites(user_id, ad_id)
        if success:
            await callback.answer("⭐ Добавлено в избранное!", show_alert=False)
        else:
            await callback.answer("❌ Ошибка добавления", show_alert=True)
