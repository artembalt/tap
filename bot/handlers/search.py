from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command

router = Router(name='search')


@router.message(Command("search"))
@router.message(F.text == "🔍 Поиск")
async def search(message: Message):
    await message.answer("🔍 Функция поиска в разработке")


@router.callback_query(F.data == "search")
async def callback_search(callback: CallbackQuery):
    await callback.message.edit_text("🔍 Функция поиска в разработке")
    await callback.answer()
