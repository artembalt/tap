#!/usr/bin/env python3
"""
Скрипт для создания всех необходимых файлов бота
"""

import os
import sys

# Словарь с содержимым всех файлов
FILES = {
    # Клавиатуры
    "bot/keyboards/__init__.py": "",
    
    "bot/keyboards/inline.py": '''
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    """Главное меню бота"""
    builder = InlineKeyboardBuilder()
    
    buttons = [
        ("📝 Подать объявление", "new_ad"),
        ("🔍 Поиск объявлений", "search"),
        ("📋 Мои объявления", "my_ads"),
        ("👤 Профиль", "profile"),
        ("ℹ️ Помощь", "help")
    ]
    
    for text, callback_data in buttons:
        builder.button(text=text, callback_data=callback_data)
    
    builder.adjust(2)
    return builder.as_markup()

def get_regions_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора региона"""
    builder = InlineKeyboardBuilder()
    builder.button(text="Калининград", callback_data="region_kaliningrad")
    builder.button(text="Санкт-Петербург", callback_data="region_spb")
    builder.button(text="❌ Отмена", callback_data="cancel")
    builder.adjust(2)
    return builder.as_markup()

def get_categories_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора категории"""
    builder = InlineKeyboardBuilder()
    builder.button(text="🏠 Недвижимость", callback_data="category_realty")
    builder.button(text="🚗 Автомобили", callback_data="category_auto")
    builder.button(text="❌ Отмена", callback_data="cancel")
    builder.adjust(2)
    return builder.as_markup()

def get_ad_type_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора типа объявления"""
    builder = InlineKeyboardBuilder()
    builder.button(text="💰 Продаю", callback_data="type_sell")
    builder.button(text="🔍 Куплю", callback_data="type_buy")
    builder.adjust(2)
    return builder.as_markup()

def get_skip_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для пропуска шага"""
    builder = InlineKeyboardBuilder()
    builder.button(text="➡️ Пропустить", callback_data="skip")
    builder.button(text="❌ Отмена", callback_data="cancel")
    return builder.as_markup()

def get_confirm_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура подтверждения"""
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Опубликовать", callback_data="confirm")
    builder.button(text="❌ Отмена", callback_data="cancel")
    return builder.as_markup()

def get_phone_settings_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура настроек телефона"""
    builder = InlineKeyboardBuilder()
    builder.button(text="📱 Показывать номер", callback_data="phone_show")
    builder.button(text="🔒 Скрыть номер", callback_data="phone_hide")
    return builder.as_markup()
''',

    "bot/keyboards/reply.py": '''
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder

def get_main_reply_keyboard() -> ReplyKeyboardMarkup:
    """Основная reply клавиатура"""
    builder = ReplyKeyboardBuilder()
    
    buttons = [
        "📝 Подать объявление",
        "🔍 Поиск",
        "📋 Мои объявления", 
        "👤 Профиль"
    ]
    
    for button in buttons:
        builder.add(KeyboardButton(text=button))
    
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)

def get_cancel_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура с кнопкой отмены"""
    builder = ReplyKeyboardBuilder()
    builder.add(KeyboardButton(text="❌ Отмена"))
    return builder.as_markup(resize_keyboard=True)

def get_phone_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура для отправки телефона"""
    builder = ReplyKeyboardBuilder()
    builder.add(
        KeyboardButton(text="📱 Отправить мой номер", request_contact=True)
    )
    builder.add(KeyboardButton(text="Пропустить"))
    builder.adjust(1)
    return builder.as_markup(resize_keyboard=True)
''',

    # Обработчики (упрощенные версии)
    "bot/handlers/__init__.py": '''
from . import start
from . import ad_creation
from . import ad_management
from . import search
from . import profile
from . import admin
from . import payment
''',

    "bot/handlers/start.py": '''
import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext

from bot.keyboards.inline import get_main_menu_keyboard
from bot.keyboards.reply import get_main_reply_keyboard
from bot.database.queries import UserQueries

router = Router(name='start')
logger = logging.getLogger(__name__)

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    """Обработка команды /start"""
    await state.clear()
    
    # Получаем или создаем пользователя
    user = await UserQueries.get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        last_name=message.from_user.last_name
    )
    
    welcome_text = f"""
👋 Добро пожаловать, {message.from_user.first_name}!

🎯 <b>Telegram Ads Platform</b> - платформа для размещения объявлений в Telegram.

📋 <b>Что вы можете делать:</b>
• Размещать объявления о продаже/покупке
• Искать товары и услуги в вашем регионе
• Сохранять интересные объявления
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

@router.message(Command("help"))
async def cmd_help(message: Message):
    """Показать справку"""
    help_text = """
📖 <b>Справка по использованию бота</b>

<b>Основные команды:</b>
/start - Перезапустить бота
/new_ad - Создать объявление
/my_ads - Мои объявления
/search - Поиск объявлений
/help - Эта справка
"""
    await message.answer(help_text)

@router.callback_query(F.data == "help")
async def callback_help(callback: CallbackQuery):
    """Обработка кнопки помощи"""
    await callback.answer("Справка отправлена в чат", show_alert=False)
    await cmd_help(callback.message)
''',

    "bot/handlers/ad_management.py": '''
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery

router = Router(name='ad_management')

@router.message(F.text == "📋 Мои объявления")
async def my_ads(message: Message):
    await message.answer("📋 Ваши объявления будут здесь (в разработке)")

@router.callback_query(F.data == "my_ads")
async def callback_my_ads(callback: CallbackQuery):
    await callback.message.edit_text("📋 Ваши объявления будут здесь (в разработке)")
    await callback.answer()
''',

    "bot/handlers/search.py": '''
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery

router = Router(name='search')

@router.message(F.text == "🔍 Поиск")
async def search(message: Message):
    await message.answer("🔍 Функция поиска в разработке")

@router.callback_query(F.data == "search")
async def callback_search(callback: CallbackQuery):
    await callback.message.edit_text("🔍 Функция поиска в разработке")
    await callback.answer()
''',

    "bot/handlers/profile.py": '''
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery

router = Router(name='profile')

@router.message(F.text == "👤 Профиль")
async def profile(message: Message):
    user_info = f"""
👤 <b>Ваш профиль</b>

ID: {message.from_user.id}
Имя: {message.from_user.first_name}
Username: @{message.from_user.username or 'не указан'}

📊 Статистика:
• Объявлений: 0
• Просмотров: 0
• В избранном: 0
"""
    await message.answer(user_info)

@router.callback_query(F.data == "profile")
async def callback_profile(callback: CallbackQuery):
    await callback.message.edit_text("👤 Загрузка профиля...")
    await profile(callback.message)
''',

    "bot/handlers/admin.py": '''
from aiogram import Router, F
from aiogram.types import Message
from bot.config import settings

router = Router(name='admin')

@router.message(F.text == "/admin")
async def admin_panel(message: Message):
    if not settings.is_admin(message.from_user.id):
        await message.answer("❌ У вас нет доступа к админ панели")
        return
    await message.answer("🔧 Админ панель в разработке")
''',

    "bot/handlers/payment.py": '''
from aiogram import Router, F
from aiogram.types import CallbackQuery

router = Router(name='payment')

@router.callback_query(F.data == "paid_services")
async def paid_services(callback: CallbackQuery):
    await callback.message.edit_text("💳 Платные услуги в разработке")
    await callback.answer()
''',

    # Утилиты
    "bot/utils/__init__.py": "",
    
    "bot/utils/commands.py": '''
from aiogram import Bot
from aiogram.types import BotCommand

async def set_bot_commands(bot: Bot):
    """Установить команды бота"""
    commands = [
        BotCommand(command="start", description="Перезапустить бота"),
        BotCommand(command="new_ad", description="Создать объявление"),
        BotCommand(command="my_ads", description="Мои объявления"),
        BotCommand(command="search", description="Поиск объявлений"),
        BotCommand(command="help", description="Справка"),
    ]
    await bot.set_my_commands(commands)
''',

    "bot/utils/validators.py": '''
import re
from typing import Optional, List, Dict, Any

def validate_price(price_text: str) -> Optional[float]:
    """Валидация цены"""
    try:
        price_text = re.sub(r'[^\d.]', '', price_text)
        return float(price_text)
    except:
        return None

def validate_phone(phone: str) -> Optional[str]:
    """Валидация телефона"""
    phone = re.sub(r'\D', '', phone)
    
    if len(phone) == 11 and phone[0] in '78':
        return f"+7{phone[1:]}"
    elif len(phone) == 10:
        return f"+7{phone}"
    
    return None

async def validate_description(description: str) -> Dict[str, Any]:
    """Валидация описания"""
    result = {"valid": True, "error": None}
    
    if len(description) < 10:
        result["valid"] = False
        result["error"] = "Описание слишком короткое (минимум 10 символов)"
    elif len(description) > 2000:
        result["valid"] = False
        result["error"] = "Описание слишком длинное (максимум 2000 символов)"
    
    return result

async def check_spam_words(text: str) -> bool:
    """Проверка на спам-слова"""
    spam_words = ["заработок", "криптовалюта", "млм"]
    text_lower = text.lower()
    return any(word in text_lower for word in spam_words)

def validate_hashtags(text: str) -> List[str]:
    """Извлечение хэштегов из текста"""
    hashtags = re.findall(r'#\w+', text)
    return hashtags[:10]
''',

    "bot/utils/formatters.py": '''
from typing import Dict, Any

async def format_ad_preview(data: Dict[str, Any]) -> str:
    """Форматирование превью объявления"""
    text = f"""
📢 <b>Превью объявления</b>

📍 Регион: {data.get('region', 'Не указан')}
📂 Категория: {data.get('category', 'Не указана')}

📝 <b>{data.get('title', 'Без заголовка')}</b>

{data.get('description', 'Без описания')}

💰 Цена: {data.get('price', 'Договорная')} ₽
"""
    return text

async def format_ad_for_channel(ad) -> str:
    """Форматирование объявления для канала"""
    return f"{ad.title}\\n\\n{ad.description}\\n\\n💰 Цена: {ad.price or 'Договорная'} ₽"
''',

    "bot/utils/messages.py": '''
MESSAGES = {
    "welcome": "Добро пожаловать!",
    "banned": "Вы заблокированы",
    "error": "Произошла ошибка",
    "success": "Успешно выполнено"
}
''',

    # Сервисы
    "bot/services/__init__.py": "",
    
    "bot/services/ad_service.py": '''
from typing import Dict, Any
from bot.database.queries import AdQueries

class AdService:
    @staticmethod
    async def create_ad(data: Dict[str, Any]):
        """Создать объявление"""
        return await AdQueries.create_ad(data)

    @staticmethod
    async def check_user_limits(user, db) -> bool:
        """Проверка лимитов пользователя"""
        return True  # Временно всегда разрешаем
''',

    "bot/services/channel_service.py": '''
from aiogram import Bot

class ChannelService:
    def __init__(self, bot: Bot):
        self.bot = bot
    
    async def publish_ad(self, ad) -> Dict[str, Any]:
        """Публикация объявления в каналы"""
        return {"success": True, "channels": [], "error": None}
''',

    "bot/services/user_service.py": '''
class UserService:
    @staticmethod
    async def get_user_stats(user_id: int):
        """Получить статистику пользователя"""
        return {
            "total_ads": 0,
            "active_ads": 0,
            "views": 0
        }
''',

    # States
    "bot/states/__init__.py": "",
    
    "bot/states/ad_states.py": '''
from aiogram.fsm.state import State, StatesGroup

class AdCreation(StatesGroup):
    region = State()
    category = State()
    ad_type = State()
    title = State()
    description = State()
    photos = State()
    video = State()
    price = State()
    phone = State()
    phone_settings = State()
    hashtags = State()
    preview = State()
    confirmation = State()
''',

    "bot/states/search_states.py": '''
from aiogram.fsm.state import State, StatesGroup

class SearchStates(StatesGroup):
    region = State()
    category = State()
    query = State()
    results = State()
''',

    # Database queries (упрощенная версия)
    "bot/database/queries.py": '''
import logging
from typing import Optional
from datetime import datetime
from bot.database.connection import get_db_session
from bot.database.models import User

logger = logging.getLogger(__name__)

class UserQueries:
    @staticmethod
    async def get_user(telegram_id: int) -> Optional[User]:
        """Получить пользователя по telegram_id"""
        try:
            async with get_db_session() as session:
                return await session.get(User, telegram_id)
        except Exception as e:
            logger.error(f"Error getting user: {e}")
            return None
    
    @staticmethod
    async def create_user(telegram_id: int, username: Optional[str] = None,
                         first_name: Optional[str] = None, last_name: Optional[str] = None) -> User:
        """Создать нового пользователя"""
        async with get_db_session() as session:
            user = User(
                telegram_id=telegram_id,
                username=username,
                first_name=first_name,
                last_name=last_name,
                created_at=datetime.utcnow()
            )
            session.add(user)
            await session.commit()
            return user
    
    @staticmethod
    async def get_or_create_user(telegram_id: int, username: Optional[str] = None,
                                first_name: Optional[str] = None, last_name: Optional[str] = None) -> User:
        """Получить или создать пользователя"""
        user = await UserQueries.get_user(telegram_id)
        if not user:
            user = await UserQueries.create_user(telegram_id, username, first_name, last_name)
        return user
    
    @staticmethod
    async def increment_warnings(telegram_id: int) -> int:
        """Увеличить счетчик предупреждений"""
        return 0  # Временная заглушка

class AdQueries:
    @staticmethod
    async def get_user_ads_count_today(telegram_id: int) -> int:
        """Получить количество объявлений пользователя за сегодня"""
        return 0  # Временная заглушка
    
    @staticmethod
    async def create_ad(ad_data):
        """Создать объявление"""
        return None  # Временная заглушка
''',
}

def create_files():
    """Создать все необходимые файлы"""
    created = 0
    errors = 0
    
    for filepath, content in FILES.items():
        try:
            # Создаем директории если их нет
            directory = os.path.dirname(filepath)
            if directory:
                os.makedirs(directory, exist_ok=True)
            
            # Записываем файл
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            
            print(f"✅ Создан: {filepath}")
            created += 1
            
        except Exception as e:
            print(f"❌ Ошибка при создании {filepath}: {e}")
            errors += 1
    
    print(f"\n📊 Результат: создано {created} файлов, ошибок: {errors}")
    
    # Проверяем структуру
    print("\n📁 Проверка структуры:")
    for directory in ['bot', 'bot/handlers', 'bot/keyboards', 'bot/database', 
                      'bot/utils', 'bot/services', 'bot/states', 'bot/middlewares']:
        if os.path.exists(directory):
            files_count = len([f for f in os.listdir(directory) if f.endswith('.py')])
            print(f"  ✓ {directory}: {files_count} файлов")
        else:
            print(f"  ✗ {directory}: не найдена")

if __name__ == "__main__":
    print("🚀 Создание файлов для бота...")
    print("=" * 50)
    create_files()
    print("=" * 50)
    print("\n✅ Готово! Теперь попробуйте запустить бота:")
    print("  python bot/main.py")
