
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
