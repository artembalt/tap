
from aiogram import Router, F
from aiogram.types import CallbackQuery

router = Router(name='payment')

@router.callback_query(F.data == "paid_services")
async def paid_services(callback: CallbackQuery):
    await callback.message.edit_text("💳 Платные услуги в разработке")
    await callback.answer()
