
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

@router.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: CallbackQuery):
    """Возврат в главное меню"""
    await callback.message.edit_text(
        "📍 Выберите нужный раздел:",
        reply_markup=get_main_menu_keyboard()
    )
    await callback.answer()
