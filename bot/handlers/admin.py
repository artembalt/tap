
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
