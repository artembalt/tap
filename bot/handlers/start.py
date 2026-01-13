# bot/handlers/start.py
"""Обработчики старта и профиля продавца"""

import logging
import time
import asyncio
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart, Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramNetworkError
from sqlalchemy import select, func

from bot.keyboards.inline import get_main_menu_keyboard, get_back_keyboard
from bot.keyboards.reply import get_main_reply_keyboard
from bot.database.queries import UserQueries, FavoritesQueries, AdQueries
from bot.database.connection import get_db_session
from bot.database.models import User, Ad, AdStatus

router = Router(name='start')
logger = logging.getLogger(__name__)

# Защита от дублирования /start (user_id -> timestamp)
_start_timestamps = {}
START_DEBOUNCE_SECONDS = 3  # Игнорировать повторные /start в течение 3 секунд


def _should_process_start(user_id: int) -> bool:
    """Проверяет, нужно ли обрабатывать /start (защита от дублей)"""
    now = time.time()
    last_start = _start_timestamps.get(user_id, 0)
    
    if now - last_start < START_DEBOUNCE_SECONDS:
        logger.info(f"Игнорируем дублирующий /start от {user_id}")
        return False
    
    _start_timestamps[user_id] = now
    return True


@router.message(CommandStart(deep_link=True))
async def cmd_start_with_args(message: Message, command: CommandObject, state: FSMContext):
    """Обработка /start с параметрами (deep link)"""
    args = command.args
    logger.info(f"Deep link получен: args={args}, user={message.from_user.id}")

    # Обработка профиля продавца
    if args and args.startswith("profile_"):
        try:
            seller_id = int(args.replace("profile_", ""))
            logger.info(f"Показываем профиль продавца {seller_id}")
            await show_seller_profile(message, seller_id)
            return
        except ValueError:
            logger.error(f"Неверный формат seller_id: {args}")

    # Обработка удаления из избранного
    if args and args.startswith("fdel_"):
        try:
            ad_id = args.replace("fdel_", "")
            logger.info(f"Удаляем из избранного: ad_id={ad_id}, user={message.from_user.id}")
            await remove_from_favorites_deeplink(message, ad_id)
            return
        except Exception as e:
            logger.error(f"Ошибка удаления из избранного: {e}")

    # Обработка добавления в избранное
    if args and args.startswith("fav_"):
        try:
            ad_id = args.replace("fav_", "")
            logger.info(f"Добавляем в избранное: ad_id={ad_id}, user={message.from_user.id}")
            await add_to_favorites_from_deeplink(message, ad_id)
            return
        except Exception as e:
            logger.error(f"Ошибка добавления в избранное: {e}")

    # Обработка просмотра объявления
    if args and args.startswith("ad_"):
        try:
            ad_id = args.replace("ad_", "")
            logger.info(f"Показываем объявление {ad_id}")
            await show_ad_detail(message, ad_id)
            return
        except Exception as e:
            logger.error(f"Ошибка показа объявления: {e}")

    # Для обычного /start - проверяем дебаунс
    if not _should_process_start(message.from_user.id):
        return

    # Очищаем состояние при любом /start
    await state.clear()
    await _send_welcome(message)


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    """Обработка команды /start"""
    # Проверяем дебаунс
    if not _should_process_start(message.from_user.id):
        return
    
    # Очищаем состояние - это отменяет любые текущие операции
    await state.clear()
    await _send_welcome(message)


async def _send_welcome(message: Message):
    """Отправка приветственного сообщения"""
    # Получаем или создаем пользователя
    user = await UserQueries.get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        last_name=message.from_user.last_name
    )

    welcome_text = f"""
👋 Добро пожаловать, {message.from_user.first_name}!

🎯 <b>Продай БОТ</b> — платформа для размещения объявлений в Telegram.

📋 <b>Что вы можете делать:</b>
• Размещать объявления о продаже/покупке
• Искать товары и услуги в вашем регионе
• Связываться с продавцами напрямую

🚀 <b>Выберите действие из меню ниже:</b>
"""

    try:
        await message.answer(
            welcome_text,
            reply_markup=get_main_reply_keyboard()
        )
        await message.answer(
            "📍 Выберите нужный раздел:",
            reply_markup=get_main_menu_keyboard()
        )
    except TelegramNetworkError as e:
        logger.error(f"[START] Сетевая ошибка: {e}")


# Количество объявлений на странице в профиле
PROFILE_ADS_PER_PAGE = 50


def get_seller_profile_keyboard(seller_id: int, offset: int, total: int) -> InlineKeyboardMarkup:
    """Клавиатура для профиля продавца с пагинацией"""
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    buttons = []
    nav_row = []

    # Кнопка "Назад" если не первая страница
    if offset > 0:
        prev_offset = max(0, offset - PROFILE_ADS_PER_PAGE)
        nav_row.append(InlineKeyboardButton(
            text="◀️ Назад",
            callback_data=f"seller_page_{seller_id}_{prev_offset}"
        ))

    # Кнопка "Далее" если есть ещё
    if offset + PROFILE_ADS_PER_PAGE < total:
        nav_row.append(InlineKeyboardButton(
            text="Далее ▶️",
            callback_data=f"seller_page_{seller_id}_{offset + PROFILE_ADS_PER_PAGE}"
        ))

    if nav_row:
        buttons.append(nav_row)

    # Кнопка в главное меню
    buttons.append([
        InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_menu")
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def show_seller_profile(message: Message, seller_id: int, offset: int = 0, edit: bool = False):
    """Показать профиль продавца с пагинацией по 50 объявлений"""
    from shared.regions_config import CHANNELS_CONFIG
    from aiogram.exceptions import TelegramAPIError

    logger.info(f"Показ профиля продавца: {seller_id}, offset={offset}")

    try:
        async with get_db_session() as session:
            # Получаем данные продавца
            result = await session.execute(
                select(User).where(User.telegram_id == seller_id)
            )
            seller = result.scalar_one_or_none()

            if not seller:
                text = "❌ Продавец не найден"
                if edit:
                    await message.edit_text(text)
                else:
                    await message.answer(text)
                return

            # Инкрементируем просмотры профиля только при первом просмотре (offset=0)
            if offset == 0:
                seller.profile_views = (seller.profile_views or 0) + 1
                await session.commit()

            # Получаем общее количество активных объявлений
            total_count_result = await session.execute(
                select(func.count(Ad.id)).where(
                    Ad.user_id == seller_id,
                    Ad.status == AdStatus.ACTIVE.value
                )
            )
            total_active = total_count_result.scalar() or 0

            # Получаем активные объявления с пагинацией
            active_ads_result = await session.execute(
                select(Ad).where(
                    Ad.user_id == seller_id,
                    Ad.status == AdStatus.ACTIVE.value
                ).order_by(Ad.created_at.desc())
                .limit(PROFILE_ADS_PER_PAGE)
                .offset(offset)
            )
            active_ads = list(active_ads_result.scalars().all())

            # Получаем количество завершённых (архив + удалённые)
            completed_count_result = await session.execute(
                select(func.count(Ad.id)).where(
                    Ad.user_id == seller_id,
                    Ad.status.in_([AdStatus.ARCHIVED.value, AdStatus.DELETED.value])
                )
            )
            completed_count = completed_count_result.scalar() or 0

            # Формируем имя (кликабельное, если есть username)
            seller_name = seller.first_name or "Пользователь"
            if seller.last_name:
                seller_name += f" {seller.last_name}"

            # Делаем имя кликабельным через username
            if seller.username:
                seller_name_display = f"<a href=\"https://t.me/{seller.username}\">{seller_name}</a>"
            else:
                seller_name_display = seller_name

            # Дата регистрации
            reg_date = seller.created_at.strftime("%d.%m.%Y") if seller.created_at else "неизвестно"

            # Заголовок списка объявлений с пагинацией
            if total_active > PROFILE_ADS_PER_PAGE:
                start_num = offset + 1
                end_num = offset + len(active_ads)
                ads_header = f"📋 <b>Активные объявления</b> ({start_num}-{end_num} из {total_active}):"
            else:
                ads_header = f"📋 <b>Активные объявления</b> ({total_active}):"

            # Формируем список объявлений с ссылками на каналы категорий
            ads_list = ""
            if active_ads:
                for i, ad in enumerate(active_ads, offset + 1):
                    title = ad.title[:40] + "..." if len(ad.title) > 40 else ad.title

                    # Пытаемся получить ссылку на объявление в канале категории
                    ad_link = None
                    channel_msgs = ad.channel_message_ids or {}

                    # Сначала ищем канал категории
                    region_config = CHANNELS_CONFIG.get(ad.region, {})
                    category_channels = region_config.get("categories", {})
                    category_channel = category_channels.get(ad.category, "")

                    if category_channel and category_channel in channel_msgs:
                        msg_id = channel_msgs[category_channel]
                        channel_username = category_channel.replace("@", "")
                        ad_link = f"https://t.me/{channel_username}/{msg_id}"
                    elif channel_msgs:
                        # Берём первый доступный канал
                        for channel, msg_id in channel_msgs.items():
                            if channel.startswith("@"):
                                channel_username = channel.replace("@", "")
                                ad_link = f"https://t.me/{channel_username}/{msg_id}"
                                break

                    if ad_link:
                        ads_list += f"  {i}. <a href=\"{ad_link}\">{title}</a>\n"
                    else:
                        ads_list += f"  {i}. {title}\n"
            else:
                ads_list = "  Нет активных объявлений\n"

            profile_text = f"""👤 <b>Профиль продавца</b>

🆔 ID: <code>{seller_id}</code>
👤 Имя: {seller_name_display}
📅 Регистрация: {reg_date}

📊 <b>Статистика:</b>
• Просмотров профиля: {seller.profile_views or 0}
• Активных объявлений: {total_active}
• Завершённых: {completed_count}

{ads_header}
{ads_list}
👆 Нажмите на заголовок — открыть объявление"""

            keyboard = get_seller_profile_keyboard(seller_id, offset, total_active)

            # Отправляем профиль
            if edit:
                try:
                    await message.edit_text(
                        profile_text,
                        reply_markup=keyboard,
                        disable_web_page_preview=True
                    )
                except TelegramAPIError:
                    await message.answer(
                        profile_text,
                        reply_markup=keyboard,
                        disable_web_page_preview=True
                    )
            else:
                await message.answer(
                    profile_text,
                    reply_markup=keyboard,
                    disable_web_page_preview=True
                )
            logger.info(f"Профиль {seller_id} показан успешно")

    except Exception as e:
        logger.error(f"Ошибка при показе профиля: {e}", exc_info=True)
        text = "❌ Ошибка при загрузке профиля. Попробуйте ещё раз."
        if edit:
            try:
                await message.edit_text(text)
            except:
                await message.answer(text)
        else:
            await message.answer(text)


@router.callback_query(F.data.startswith("seller_page_"))
async def seller_profile_page(callback: CallbackQuery):
    """Навигация по страницам профиля продавца"""
    # Формат: seller_page_{seller_id}_{offset}
    parts = callback.data.replace("seller_page_", "").split("_")
    seller_id = int(parts[0])
    offset = int(parts[1])

    logger.info(f"Профиль продавца: страница, seller={seller_id}, offset={offset}")

    await show_seller_profile(callback.message, seller_id, offset=offset, edit=True)
    await callback.answer()


@router.message(Command("help"))
async def cmd_help(message: Message):
    """Показать справку"""
    help_text = """
📖 <b>Справка по использованию бота</b>

<b>Основные команды:</b>
/start — Перезапустить бота
/create — Создать объявление
/help — Эта справка
"""
    await message.answer(help_text)


@router.callback_query(F.data == "help")
async def callback_help(callback: CallbackQuery):
    """Обработка кнопки помощи"""
    await callback.answer("Справка отправлена в чат", show_alert=False)
    await cmd_help(callback.message)


@router.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: CallbackQuery, state: FSMContext):
    """Возврат в главное меню"""
    await state.clear()
    await callback.message.edit_text(
        "📍 Выберите нужный раздел:",
        reply_markup=get_main_menu_keyboard()
    )
    await callback.answer()


async def show_ad_detail(message: Message, ad_id: str):
    """Показать детали объявления"""
    from aiogram.types import InputMediaPhoto
    from shared.regions_config import (
        REGIONS, CITIES, CATEGORIES, SUBCATEGORIES, 
        DEAL_TYPES, CONDITION_TYPES, DELIVERY_TYPES
    )
    
    try:
        async with get_db_session() as session:
            from sqlalchemy import select
            import uuid
            
            # Пробуем преобразовать в UUID
            try:
                ad_uuid = uuid.UUID(ad_id)
            except ValueError:
                await message.answer("❌ Неверный формат ID объявления")
                return
            
            result = await session.execute(
                select(Ad).where(Ad.id == ad_uuid)
            )
            ad = result.scalar_one_or_none()

            if not ad:
                await message.answer("❌ Объявление не найдено")
                return

            if ad.status != AdStatus.ACTIVE.value:
                await message.answer("❌ Объявление неактивно или удалено")
                return

            # Инкрементируем просмотры объявления
            ad.views_count = (ad.views_count or 0) + 1
            await session.commit()
            
            # Получаем данные продавца
            seller_result = await session.execute(
                select(User).where(User.telegram_id == ad.user_id)
            )
            seller = seller_result.scalar_one_or_none()
            
            # Формируем текст объявления
            region_name = REGIONS.get(ad.region, ad.region or "")
            category_name = CATEGORIES.get(ad.category, ad.category or "")
            
            # Получаем доп. данные из premium_features
            pf = ad.premium_features or {}
            subcategory = pf.get('subcategory', '')
            subcategory_name = SUBCATEGORIES.get(ad.category, {}).get(subcategory, subcategory)
            condition = pf.get('condition', '')
            condition_name = CONDITION_TYPES.get(condition, '')
            delivery = pf.get('delivery', '')
            delivery_name = DELIVERY_TYPES.get(delivery, '')
            city = pf.get('city', '')
            city_name = CITIES.get(ad.region, {}).get(city, city)
            
            deal_type_name = DEAL_TYPES.get(ad.ad_type, ad.ad_type or "")
            
            # Цена
            if ad.price:
                price_text = f"{int(ad.price):,} ₽".replace(",", " ")
            else:
                price_text = pf.get('price_text', 'Договорная')
            
            # Seller info
            seller_name = "Продавец"
            if seller:
                seller_name = seller.first_name or "Продавец"
            
            # Получаем username бота
            bot_info = await message.bot.get_me()
            bot_username = bot_info.username
            
            text = f"""📢 <b>{ad.title}</b>

📍 {region_name}{f' • {city_name}' if city_name else ''}
📂 {category_name}{f' • {subcategory_name}' if subcategory_name else ''}
🏷 {deal_type_name}{f' • {condition_name}' if condition_name else ''}

{ad.description or ''}

💰 <b>Цена:</b> {price_text}
{f'🚚 <b>Доставка:</b> {delivery_name}' if delivery_name else ''}

━━━━━━━━━━━━━━━━━━━
😎 <a href="tg://user?id={ad.user_id}">Написать продавцу</a>
👾 <a href="https://t.me/{bot_username}?start=profile_{ad.user_id}">Профиль продавца</a>
📢 <a href="https://t.me/{bot_username}">Разместить объявление</a>
"""
            
            photos = ad.photos or []
            
            if photos:
                if len(photos) == 1:
                    await message.answer_photo(
                        photo=photos[0],
                        caption=text,
                        reply_markup=get_back_keyboard()
                    )
                else:
                    # Медиагруппа
                    media_group = [InputMediaPhoto(media=photos[0], caption=text)]
                    for photo in photos[1:10]:
                        media_group.append(InputMediaPhoto(media=photo))
                    
                    await message.answer_media_group(media=media_group)
                    await message.answer(
                        "👆 Объявление выше",
                        reply_markup=get_back_keyboard()
                    )
            else:
                await message.answer(
                    text,
                    reply_markup=get_back_keyboard(),
                    disable_web_page_preview=True
                )
                
    except Exception as e:
        logger.error(f"Ошибка при показе объявления: {e}", exc_info=True)
        await message.answer("❌ Ошибка при загрузке объявления")


async def add_to_favorites_from_deeplink(message: Message, ad_id: str):
    """Добавить объявление в избранное через deep link из канала"""
    user_id = message.from_user.id

    # Сначала регистрируем/получаем пользователя
    await UserQueries.get_or_create_user(
        telegram_id=user_id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        last_name=message.from_user.last_name
    )

    # Проверяем, существует ли объявление
    ad = await AdQueries.get_ad(ad_id)
    if not ad:
        await message.answer(
            "❌ Объявление не найдено или было удалено.",
            reply_markup=get_main_reply_keyboard()
        )
        return

    if ad.status != AdStatus.ACTIVE.value:
        await message.answer(
            "❌ Это объявление больше неактивно.",
            reply_markup=get_main_reply_keyboard()
        )
        return

    # Проверяем, есть ли уже в избранном
    is_favorite = await FavoritesQueries.is_in_favorites(user_id, ad_id)

    if is_favorite:
        # Уже в избранном - предлагаем удалить
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="❌ Удалить из избранного",
                callback_data=f"fav_remove_{ad_id}"
            )],
            [InlineKeyboardButton(text="⭐ Перейти в избранное", callback_data="favorites_back")]
        ])

        await message.answer(
            f"⭐ Объявление «{ad.title[:40]}...» уже в избранном!",
            reply_markup=keyboard
        )
    else:
        # Добавляем в избранное
        success = await FavoritesQueries.add_to_favorites(user_id, ad_id)

        if success:
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⭐ Перейти в избранное", callback_data="favorites_back")]
            ])

            await message.answer(
                f"✅ Объявление «{ad.title[:40]}...» добавлено в избранное!",
                reply_markup=keyboard
            )
        else:
            await message.answer(
                "❌ Не удалось добавить в избранное. Попробуйте позже.",
                reply_markup=get_main_reply_keyboard()
            )


async def remove_from_favorites_deeplink(message: Message, ad_id: str):
    """Удалить объявление из избранного через deep link"""
    user_id = message.from_user.id

    # Проверяем, есть ли в избранном
    is_favorite = await FavoritesQueries.is_in_favorites(user_id, ad_id)

    if not is_favorite:
        await message.answer(
            "❌ Это объявление не в вашем избранном.",
            reply_markup=get_main_reply_keyboard()
        )
        return

    # Удаляем из избранного
    success = await FavoritesQueries.remove_from_favorites(user_id, ad_id)

    if success:
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⭐ Перейти в избранное", callback_data="favorites_back")]
        ])

        await message.answer(
            "✅ Объявление удалено из избранного!",
            reply_markup=keyboard
        )
    else:
        await message.answer(
            "❌ Не удалось удалить из избранного. Попробуйте позже.",
            reply_markup=get_main_reply_keyboard()
        )
