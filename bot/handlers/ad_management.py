# bot/handlers/ad_management.py
"""Обработчик управления объявлениями - БЕЗ КЛАВИАТУРЫ, ссылки на каналы"""

import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramAPIError

from bot.database.queries import AdQueries
from bot.keyboards.inline import get_back_keyboard
from shared.regions_config import REGIONS, CATEGORIES, CHANNELS_CONFIG

router = Router(name='ad_management')
logger = logging.getLogger(__name__)


class EditAdStates(StatesGroup):
    """Состояния для редактирования объявления"""
    waiting_for_new_title = State()
    waiting_for_new_description = State()
    waiting_for_new_price = State()


# =============================================================================
# ПРОСМОТР СПИСКА СВОИХ ОБЪЯВЛЕНИЙ
# =============================================================================

@router.message(Command("my_ads"))
@router.message(F.text == "📋 Мои объявления")
async def my_ads(message: Message):
    """Показать список объявлений пользователя"""
    logger.info(f"my_ads вызван, user={message.from_user.id}")
    await show_user_ads(message, message.from_user.id)


@router.callback_query(F.data == "my_ads")
async def callback_my_ads(callback: CallbackQuery):
    """Показать список объявлений пользователя (через callback)"""
    logger.info(f"callback_my_ads вызван, user={callback.from_user.id}")
    await show_user_ads(callback.message, callback.from_user.id, edit=True)
    await callback.answer()


async def show_user_ads(message: Message, user_id: int, edit: bool = False):
    """
    Показать объявления пользователя.
    БЕЗ КЛАВИАТУРЫ - заголовки как ссылки на каналы.
    """
    try:
        # Получаем ВСЕ объявления пользователя (без лимита)
        ads = await AdQueries.get_user_ads(user_id, limit=100)
    except Exception as e:
        logger.error(f"Ошибка получения объявлений: {e}")
        text = "❌ Ошибка загрузки объявлений. Попробуйте позже."
        if edit:
            try:
                await message.edit_text(text, reply_markup=get_back_keyboard())
            except TelegramAPIError:
                await message.answer(text, reply_markup=get_back_keyboard())
        else:
            await message.answer(text, reply_markup=get_back_keyboard())
        return
    
    if not ads:
        text = (
            "📋 <b>Ваши объявления</b>\n\n"
            "У вас пока нет объявлений.\n"
            "Создайте своё первое объявление!"
        )
        
        if edit:
            if message.photo:
                await message.delete()
                await message.answer(text, reply_markup=get_back_keyboard())
            else:
                try:
                    await message.edit_text(text, reply_markup=get_back_keyboard())
                except TelegramAPIError:
                    await message.answer(text, reply_markup=get_back_keyboard())
        else:
            await message.answer(text, reply_markup=get_back_keyboard())
        return
    
    # Формируем список с кликабельными заголовками
    text = f"📋 <b>Ваши объявления</b> ({len(ads)})\n\n"
    
    for i, ad in enumerate(ads, 1):
        status_emoji = {
            "active": "✅",
            "pending": "⏳",
            "archived": "📦",
            "rejected": "❌"
        }.get(ad.status, "❓")
        
        # Формируем цену
        if ad.price:
            price_text = f"{int(ad.price):,}₽".replace(",", " ")
        else:
            # Пробуем получить из premium_features
            pf = ad.premium_features or {}
            price_text = pf.get('price_text', 'Договорная')
        
        # Получаем ссылку на объявление в канале
        channel_link = get_channel_link(ad)
        
        if channel_link:
            # Заголовок как ссылка на канал
            title_display = ad.title[:40] + "..." if len(ad.title) > 40 else ad.title
            text += f"{i}. {status_emoji} <a href=\"{channel_link}\">{title_display}</a>\n"
        else:
            # Без ссылки (не опубликовано)
            title_display = ad.title[:40] + "..." if len(ad.title) > 40 else ad.title
            text += f"{i}. {status_emoji} {title_display}\n"
        
        text += f"   💰 {price_text} | 👁 {ad.views_count}\n\n"
    
    text += "👆 Нажмите на заголовок чтобы открыть объявление в канале"
    
    # Отправляем БЕЗ inline клавиатуры (только кнопка назад)
    if edit:
        if message.photo:
            await message.delete()
            await message.answer(text, reply_markup=get_back_keyboard(), disable_web_page_preview=True)
        else:
            try:
                await message.edit_text(text, reply_markup=get_back_keyboard(), disable_web_page_preview=True)
            except TelegramAPIError:
                await message.answer(text, reply_markup=get_back_keyboard(), disable_web_page_preview=True)
    else:
        await message.answer(text, reply_markup=get_back_keyboard(), disable_web_page_preview=True)


def get_channel_link(ad) -> str | None:
    """
    Получить ссылку на объявление в канале.
    Формат: https://t.me/channel_username/message_id
    """
    # channel_message_ids хранит {"@channel_name": message_id}
    channel_message_ids = ad.channel_message_ids or {}
    
    if not channel_message_ids:
        return None
    
    # Берём первый доступный канал
    for channel_username, message_id in channel_message_ids.items():
        if channel_username and message_id:
            # Убираем @ если есть
            channel_clean = channel_username.lstrip('@')
            return f"https://t.me/{channel_clean}/{message_id}"
    
    return None


# =============================================================================
# ОТМЕНА РЕДАКТИРОВАНИЯ
# =============================================================================

@router.message(F.text == "/cancel")
async def cancel_editing(message: Message, state: FSMContext):
    """Отмена редактирования"""
    current_state = await state.get_state()
    if current_state:
        await state.clear()
        await message.answer("❌ Отменено", reply_markup=get_back_keyboard())
    else:
        await message.answer("Нечего отменять")
