
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
