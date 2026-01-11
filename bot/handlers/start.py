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
from bot.database.queries import UserQueries
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
    """Отправка приветственного сообщения с retry"""
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

    # Retry для первого сообщения (cold start fix)
    for attempt in range(3):
        try:
            await message.answer(
                welcome_text,
                reply_markup=get_main_reply_keyboard()
            )
            break
        except TelegramNetworkError as e:
            if attempt < 2:
                logger.warning(f"[START] Сетевая ошибка (попытка {attempt+1}), повтор: {e}")
                await asyncio.sleep(0.3)
            else:
                logger.error(f"[START] Не удалось отправить приветствие: {e}")
                return

    # Retry для второго сообщения
    for attempt in range(3):
        try:
            await message.answer(
                "📍 Выберите нужный раздел:",
                reply_markup=get_main_menu_keyboard()
            )
            break
        except TelegramNetworkError as e:
            if attempt < 2:
                await asyncio.sleep(0.3)
            else:
                logger.error(f"[START] Не удалось отправить меню: {e}")


async def show_seller_profile(message: Message, seller_id: int):
    """Показать профиль продавца с просмотрами и кликабельными объявлениями"""
    import asyncio
    from aiogram.exceptions import TelegramNetworkError
    
    logger.info(f"Показ профиля продавца: {seller_id}")
    
    try:
        async with get_db_session() as session:
            # Получаем данные продавца
            result = await session.execute(
                select(User).where(User.telegram_id == seller_id)
            )
            seller = result.scalar_one_or_none()
            
            if not seller:
                await message.answer("❌ Продавец не найден")
                return
            
            # Получаем активные объявления
            active_ads_result = await session.execute(
                select(Ad).where(
                    Ad.user_id == seller_id,
                    Ad.status == AdStatus.ACTIVE.value
                ).order_by(Ad.created_at.desc())
            )
            active_ads = active_ads_result.scalars().all()
            
            # Получаем количество завершённых (архив + удалённые)
            completed_count_result = await session.execute(
                select(func.count(Ad.id)).where(
                    Ad.user_id == seller_id,
                    Ad.status.in_([AdStatus.ARCHIVED.value, AdStatus.DELETED.value])
                )
            )
            completed_count = completed_count_result.scalar() or 0
            
            # Формируем имя
            seller_name = seller.first_name or "Пользователь"
            if seller.last_name:
                seller_name += f" {seller.last_name}"
            
            # Username
            username_text = f"@{seller.username}" if seller.username else "не указан"
            
            # Дата регистрации
            reg_date = seller.created_at.strftime("%d.%m.%Y") if seller.created_at else "неизвестно"
            
            # Получаем username бота для ссылок
            bot_info = await message.bot.get_me()
            bot_username = bot_info.username
            
            # Формируем список объявлений с КЛИКАБЕЛЬНЫМИ ссылками
            ads_list = ""
            if active_ads:
                for i, ad in enumerate(active_ads[:10], 1):
                    title = ad.title[:35] + "..." if len(ad.title) > 35 else ad.title
                    # Ссылка на объявление через deep link
                    ad_link = f"https://t.me/{bot_username}?start=ad_{ad.id}"
                    ads_list += f"  {i}. <a href=\"{ad_link}\">{title}</a>\n"
            else:
                ads_list = "  Нет активных объявлений\n"
            
            profile_text = f"""👤 <b>Профиль продавца</b>

🆔 ID: <code>{seller_id}</code>
👤 Имя: {seller_name}
📱 Username: {username_text}
📅 Регистрация: {reg_date}

📊 <b>Статистика:</b>
• Активных объявлений: {len(active_ads)}
• Завершённых: {completed_count}

📋 <b>Активные объявления:</b>
{ads_list}"""

            # Отправляем профиль (RetryMiddleware автоматически повторит при ошибках)
            await message.answer(
                profile_text,
                reply_markup=get_back_keyboard(),
                disable_web_page_preview=True
            )
            logger.info(f"Профиль {seller_id} показан успешно")
            
    except Exception as e:
        logger.error(f"Ошибка при показе профиля: {e}", exc_info=True)
        await message.answer("❌ Ошибка при загрузке профиля. Попробуйте ещё раз.")


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
