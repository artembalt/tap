# bot/handlers/ad_management.py
"""Обработчик управления объявлениями - с пагинацией по 50"""

import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramAPIError

from bot.database.queries import AdQueries
from bot.keyboards.inline import get_back_keyboard
from shared.regions_config import REGIONS, CATEGORIES, CHANNELS_CONFIG

router = Router(name='ad_management')
logger = logging.getLogger(__name__)

# Количество объявлений на странице
ADS_PER_PAGE = 50


class EditAdStates(StatesGroup):
    """Состояния для редактирования объявления"""
    waiting_for_new_title = State()
    waiting_for_new_description = State()
    waiting_for_new_price = State()


def get_my_ads_keyboard(offset: int, total: int) -> InlineKeyboardMarkup:
    """Клавиатура для пагинации объявлений"""
    buttons = []

    # Кнопка "Показать следующие 50" если есть ещё объявления
    if offset + ADS_PER_PAGE < total:
        remaining = total - offset - ADS_PER_PAGE
        next_count = min(remaining, ADS_PER_PAGE)
        buttons.append([
            InlineKeyboardButton(
                text=f"📄 Показать следующие {next_count}",
                callback_data=f"my_ads_page_{offset + ADS_PER_PAGE}"
            )
        ])

    # Кнопка назад
    buttons.append([
        InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


# =============================================================================
# ПРОСМОТР СПИСКА СВОИХ ОБЪЯВЛЕНИЙ
# =============================================================================

@router.message(Command("my_ads"))
@router.message(F.text == "📋 Мои объявления")
async def my_ads(message: Message):
    """Показать список объявлений пользователя"""
    logger.info(f"my_ads вызван, user={message.from_user.id}")
    await show_user_ads(message, message.from_user.id, offset=0)


@router.callback_query(F.data == "my_ads")
async def callback_my_ads(callback: CallbackQuery):
    """Показать список объявлений пользователя (через callback)"""
    logger.info(f"callback_my_ads вызван, user={callback.from_user.id}")
    await show_user_ads(callback.message, callback.from_user.id, offset=0, edit=True)
    await callback.answer()


@router.callback_query(F.data.startswith("my_ads_page_"))
async def callback_my_ads_page(callback: CallbackQuery):
    """Показать следующую страницу объявлений"""
    offset = int(callback.data.replace("my_ads_page_", ""))
    logger.info(f"my_ads_page вызван, user={callback.from_user.id}, offset={offset}")
    await show_user_ads(callback.message, callback.from_user.id, offset=offset, edit=True)
    await callback.answer()


async def show_user_ads(message: Message, user_id: int, offset: int = 0, edit: bool = False):
    """
    Показать объявления пользователя с пагинацией по 50.
    """
    try:
        # Получаем общее количество объявлений
        total_count = await AdQueries.get_user_ads_count(user_id)

        # Получаем объявления для текущей страницы
        ads = await AdQueries.get_user_ads(user_id, limit=ADS_PER_PAGE, offset=offset)
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

    if not ads and offset == 0:
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

    # Формируем заголовок с информацией о пагинации
    start_num = offset + 1
    end_num = offset + len(ads)

    if total_count > ADS_PER_PAGE:
        text = f"📋 <b>Ваши объявления</b> ({start_num}-{end_num} из {total_count})\n\n"
    else:
        text = f"📋 <b>Ваши объявления</b> ({total_count})\n\n"

    for i, ad in enumerate(ads, start_num):
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
            pf = ad.premium_features or {}
            price_text = pf.get('price_text', 'Договорная')

        # Получаем ссылку на объявление в канале
        channel_link = get_channel_link(ad)

        title_display = ad.title[:40] + "..." if len(ad.title) > 40 else ad.title

        if channel_link:
            text += f"{i}. {status_emoji} <a href=\"{channel_link}\">{title_display}</a>\n"
        else:
            text += f"{i}. {status_emoji} {title_display}\n"

        text += f"   💰 {price_text} | 👁 {ad.views_count or 0}\n\n"

    text += "👆 Нажмите на заголовок чтобы открыть объявление в канале"

    # Клавиатура с пагинацией
    keyboard = get_my_ads_keyboard(offset, total_count)

    if edit:
        if message.photo:
            await message.delete()
            await message.answer(text, reply_markup=keyboard, disable_web_page_preview=True)
        else:
            try:
                await message.edit_text(text, reply_markup=keyboard, disable_web_page_preview=True)
            except TelegramAPIError:
                await message.answer(text, reply_markup=keyboard, disable_web_page_preview=True)
    else:
        await message.answer(text, reply_markup=keyboard, disable_web_page_preview=True)


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
