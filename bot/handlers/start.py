# bot/handlers/start.py
"""Обработчики старта и профиля продавца"""

import logging
import time
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart, Command, CommandObject
from aiogram.fsm.context import FSMContext
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
    
    # Обработка профиля продавца - всегда обрабатываем
    if args and args.startswith("profile_"):
        try:
            seller_id = int(args.replace("profile_", ""))
            await show_seller_profile(message, seller_id)
            return
        except ValueError:
            pass
    
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
    
    await message.answer(
        welcome_text,
        reply_markup=get_main_reply_keyboard()
    )
    
    await message.answer(
        "📍 Выберите нужный раздел:",
        reply_markup=get_main_menu_keyboard()
    )


async def show_seller_profile(message: Message, seller_id: int):
    """Показать профиль продавца"""
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
            
            # Увеличиваем счётчик просмотров профиля
            # (если есть такое поле, иначе пропускаем)
            
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
            
            # Формируем список объявлений
            ads_list = ""
            if active_ads:
                for i, ad in enumerate(active_ads[:10], 1):
                    title = ad.title[:40] + "..." if len(ad.title) > 40 else ad.title
                    ads_list += f"  {i}. {title}\n"
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

            await message.answer(
                profile_text,
                reply_markup=get_back_keyboard()
            )
            
    except Exception as e:
        logger.error(f"Ошибка при показе профиля: {e}", exc_info=True)
        await message.answer("❌ Ошибка при загрузке профиля")


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
