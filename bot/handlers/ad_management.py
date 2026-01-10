# bot/handlers/ad_management.py
"""Обработчик управления объявлениями пользователя - ОПТИМИЗИРОВАННАЯ ВЕРСИЯ"""

import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InputMediaPhoto
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.database.queries import AdQueries, FavoritesQueries
from bot.keyboards.inline import (
    get_user_ads_keyboard, 
    get_ad_actions_keyboard,
    get_confirm_delete_keyboard,
    get_back_keyboard
)
from bot.utils.formatters import format_ad_detail, format_ad_list_item
from shared.regions_config import REGIONS, CATEGORIES

router = Router(name='ad_management')
logger = logging.getLogger(__name__)

# Лимит объявлений на странице (было 50!)
ADS_PER_PAGE = 5

# =============================================================================
# FSM STATES
# =============================================================================

class EditAdStates(StatesGroup):
    """Состояния для редактирования объявления"""
    waiting_for_new_title = State()
    waiting_for_new_description = State()
    waiting_for_new_price = State()
    waiting_for_new_photos = State()

# =============================================================================
# ПРОСМОТР СПИСКА СВОИХ ОБЪЯВЛЕНИЙ
# =============================================================================

@router.message(F.text == "📋 Мои объявления")
async def my_ads(message: Message):
    """Показать список объявлений пользователя"""
    await show_user_ads(message, message.from_user.id, page=0)

@router.callback_query(F.data == "my_ads")
async def callback_my_ads(callback: CallbackQuery):
    """Показать список объявлений пользователя (через callback)"""
    await show_user_ads(callback.message, callback.from_user.id, edit=True, page=0)
    await callback.answer()

@router.callback_query(F.data.startswith("my_ads_page_"))
async def callback_my_ads_page(callback: CallbackQuery):
    """Пагинация списка объявлений"""
    page = int(callback.data.replace("my_ads_page_", ""))
    await show_user_ads(callback.message, callback.from_user.id, edit=True, page=page)
    await callback.answer()

async def show_user_ads(message: Message, user_id: int, edit: bool = False, page: int = 0):
    """
    Вспомогательная функция для показа объявлений.
    ОПТИМИЗИРОВАНО: limit=5, пагинация, компактный текст.
    """
    try:
        # Получаем объявления пользователя с пагинацией
        # ВАЖНО: limit уменьшен с 50 до 5!
        ads = await AdQueries.get_user_ads(
            user_id, 
            limit=ADS_PER_PAGE, 
            offset=page * ADS_PER_PAGE
        )
        
        # Получаем общее количество для пагинации (отдельный быстрый запрос)
        total_count = await AdQueries.get_user_ads_count(user_id)
        
    except Exception as e:
        logger.error(f"Ошибка получения объявлений: {e}")
        text = "❌ Ошибка загрузки объявлений. Попробуйте позже."
        if edit:
            try:
                await message.edit_text(text, reply_markup=get_back_keyboard())
            except:
                await message.answer(text, reply_markup=get_back_keyboard())
        else:
            await message.answer(text, reply_markup=get_back_keyboard())
        return
    
    if not ads and page == 0:
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
                except:
                    await message.answer(text, reply_markup=get_back_keyboard())
        else:
            await message.answer(text, reply_markup=get_back_keyboard())
        return
    
    # Формируем КОМПАКТНЫЙ список объявлений
    total_pages = (total_count + ADS_PER_PAGE - 1) // ADS_PER_PAGE
    text = f"📋 <b>Ваши объявления</b> ({total_count})\n"
    if total_pages > 1:
        text += f"📄 Страница {page + 1} из {total_pages}\n"
    text += "\n"
    
    for i, ad in enumerate(ads, 1 + page * ADS_PER_PAGE):
        status_emoji = {
            "active": "✅",
            "pending": "⏳",
            "archived": "📦",
            "rejected": "❌"
        }.get(ad.status, "❓")
        
        # Компактный формат - без лишних полей
        title = ad.title[:25] + "..." if len(ad.title) > 25 else ad.title
        price_text = f"{int(ad.price):,}₽".replace(",", " ") if ad.price else "Договорная"
        
        text += f"{i}. {status_emoji} <b>{title}</b>\n"
        text += f"   💰 {price_text} | 👁 {ad.views_count}\n\n"
    
    text += "👆 Нажмите на объявление для управления"
    
    # Клавиатура с пагинацией
    keyboard = get_user_ads_keyboard_paginated(ads, page, total_pages)
    
    if edit:
        if message.photo:
            await message.delete()
            await message.answer(text, reply_markup=keyboard)
        else:
            try:
                await message.edit_text(text, reply_markup=keyboard)
            except:
                await message.answer(text, reply_markup=keyboard)
    else:
        await message.answer(text, reply_markup=keyboard)


def get_user_ads_keyboard_paginated(ads: list, page: int, total_pages: int):
    """Клавиатура со списком объявлений и пагинацией"""
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    
    builder = InlineKeyboardBuilder()
    
    # Кнопки объявлений (максимум 5)
    for ad in ads[:ADS_PER_PAGE]:
        title = ad.title[:25] + "..." if len(ad.title) > 25 else ad.title
        builder.button(text=f"📌 {title}", callback_data=f"view_my_ad_{ad.id}")
    
    # Кнопки пагинации
    if total_pages > 1:
        pagination_buttons = []
        if page > 0:
            pagination_buttons.append(
                InlineKeyboardButton(text="⬅️", callback_data=f"my_ads_page_{page - 1}")
            )
        pagination_buttons.append(
            InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="noop")
        )
        if page < total_pages - 1:
            pagination_buttons.append(
                InlineKeyboardButton(text="➡️", callback_data=f"my_ads_page_{page + 1}")
            )
        builder.row(*pagination_buttons)
    
    builder.button(text="🔙 Главное меню", callback_data="back_to_menu")
    builder.adjust(1)  # Все кнопки в один столбец
    
    return builder.as_markup()


# =============================================================================
# ПРОСМОТР ДЕТАЛИ ОБЪЯВЛЕНИЯ
# =============================================================================

@router.callback_query(F.data.startswith("view_my_ad_"))
async def view_my_ad_detail(callback: CallbackQuery):
    """Просмотр деталей своего объявления"""
    ad_id = callback.data.replace("view_my_ad_", "")
    
    try:
        ad = await AdQueries.get_ad(ad_id)
    except Exception as e:
        logger.error(f"Ошибка получения объявления {ad_id}: {e}")
        await callback.answer("❌ Ошибка загрузки", show_alert=True)
        return
    
    if not ad:
        await callback.answer("❌ Объявление не найдено", show_alert=True)
        return
    
    # Проверяем, что это объявление пользователя
    if ad.user_id != callback.from_user.id:
        await callback.answer("❌ Это не ваше объявление", show_alert=True)
        return
    
    # Формируем КОМПАКТНЫЙ текст объявления
    text = format_ad_detail_compact(ad)
    
    # Если есть фото, отправляем с фото
    if ad.photos and len(ad.photos) > 0:
        try:
            await callback.message.delete()
        except:
            pass
        await callback.message.answer_photo(
            photo=ad.photos[0],
            caption=text,
            reply_markup=get_ad_actions_keyboard(str(ad.id), is_owner=True)
        )
    else:
        try:
            await callback.message.edit_text(
                text,
                reply_markup=get_ad_actions_keyboard(str(ad.id), is_owner=True)
            )
        except:
            await callback.message.answer(
                text,
                reply_markup=get_ad_actions_keyboard(str(ad.id), is_owner=True)
            )
    
    await callback.answer()


def format_ad_detail_compact(ad) -> str:
    """Компактное форматирование объявления (для быстрой отправки)"""
    status_emoji = {
        "active": "✅ Активно",
        "pending": "⏳ На модерации",
        "archived": "📦 В архиве",
        "rejected": "❌ Отклонено"
    }.get(ad.status, "❓")
    
    price_text = f"{int(ad.price):,} ₽".replace(",", " ") if ad.price else "Договорная"
    region_name = REGIONS.get(ad.region, ad.region or "")
    category_name = CATEGORIES.get(ad.category, ad.category or "")
    
    # Ограничиваем описание
    description = ad.description or ""
    if len(description) > 200:
        description = description[:200] + "..."
    
    text = f"""<b>{ad.title}</b>

{description}

💰 {price_text}
📍 {region_name}
📂 {category_name}
📊 {status_emoji}

👁 Просмотров: {ad.views_count}
⭐ В избранном: {ad.favorites_count}"""
    
    return text


# =============================================================================
# РЕДАКТИРОВАНИЕ ОБЪЯВЛЕНИЯ
# =============================================================================

@router.callback_query(F.data.startswith("edit_ad_"))
async def start_edit_ad(callback: CallbackQuery, state: FSMContext):
    """Начать редактирование объявления"""
    ad_id = callback.data.replace("edit_ad_", "")
    
    try:
        ad = await AdQueries.get_ad(ad_id)
    except Exception as e:
        logger.error(f"Ошибка получения объявления: {e}")
        await callback.answer("❌ Ошибка загрузки", show_alert=True)
        return
    
    if not ad or ad.user_id != callback.from_user.id:
        await callback.answer("❌ Объявление не найдено", show_alert=True)
        return
    
    await state.update_data(editing_ad_id=ad_id)
    
    # Компактный текст
    desc_preview = ad.description[:50] + "..." if len(ad.description) > 50 else ad.description
    price_text = f"{int(ad.price):,} ₽".replace(",", " ") if ad.price else "Договорная"
    
    text = f"""📝 <b>Редактирование</b>

📌 {ad.title}
📄 {desc_preview}
💰 {price_text}

Что изменить?"""
    
    from bot.keyboards.inline import get_edit_options_keyboard
    
    if callback.message.photo:
        await callback.message.delete()
        await callback.message.answer(text, reply_markup=get_edit_options_keyboard(ad_id))
    else:
        try:
            await callback.message.edit_text(text, reply_markup=get_edit_options_keyboard(ad_id))
        except:
            await callback.message.answer(text, reply_markup=get_edit_options_keyboard(ad_id))
    
    await callback.answer()


@router.callback_query(F.data.startswith("edit_title_"))
async def edit_ad_title(callback: CallbackQuery, state: FSMContext):
    """Редактировать заголовок"""
    ad_id = callback.data.replace("edit_title_", "")
    await state.update_data(editing_ad_id=ad_id)
    await state.set_state(EditAdStates.waiting_for_new_title)
    
    text = "📝 Введите новый заголовок (до 100 символов):"
    
    if callback.message.photo:
        await callback.message.delete()
        await callback.message.answer(text)
    else:
        try:
            await callback.message.edit_text(text)
        except:
            await callback.message.answer(text)
    
    await callback.answer()


@router.message(EditAdStates.waiting_for_new_title)
async def process_new_title(message: Message, state: FSMContext):
    """Обработка нового заголовка"""
    if len(message.text) > 100:
        await message.answer("❌ Максимум 100 символов")
        return
    
    data = await state.get_data()
    ad_id = data.get("editing_ad_id")
    
    try:
        success = await AdQueries.update_ad(ad_id, title=message.text)
    except Exception as e:
        logger.error(f"Ошибка обновления: {e}")
        await message.answer("❌ Ошибка сохранения")
        return
    
    if success:
        await message.answer("✅ Заголовок обновлён!")
        await state.clear()
    else:
        await message.answer("❌ Ошибка обновления")


@router.callback_query(F.data.startswith("edit_description_"))
async def edit_ad_description(callback: CallbackQuery, state: FSMContext):
    """Редактировать описание"""
    ad_id = callback.data.replace("edit_description_", "")
    await state.update_data(editing_ad_id=ad_id)
    await state.set_state(EditAdStates.waiting_for_new_description)
    
    text = "📄 Введите новое описание (до 1000 символов):"
    
    if callback.message.photo:
        await callback.message.delete()
        await callback.message.answer(text)
    else:
        try:
            await callback.message.edit_text(text)
        except:
            await callback.message.answer(text)
    
    await callback.answer()


@router.message(EditAdStates.waiting_for_new_description)
async def process_new_description(message: Message, state: FSMContext):
    """Обработка нового описания"""
    if len(message.text) > 1000:
        await message.answer("❌ Максимум 1000 символов")
        return
    
    data = await state.get_data()
    ad_id = data.get("editing_ad_id")
    
    try:
        success = await AdQueries.update_ad(ad_id, description=message.text)
    except Exception as e:
        logger.error(f"Ошибка обновления: {e}")
        await message.answer("❌ Ошибка сохранения")
        return
    
    if success:
        await message.answer("✅ Описание обновлено!")
        await state.clear()
    else:
        await message.answer("❌ Ошибка обновления")


@router.callback_query(F.data.startswith("edit_price_"))
async def edit_ad_price(callback: CallbackQuery, state: FSMContext):
    """Редактировать цену"""
    ad_id = callback.data.replace("edit_price_", "")
    await state.update_data(editing_ad_id=ad_id)
    await state.set_state(EditAdStates.waiting_for_new_price)
    
    text = "💰 Введите новую цену (число в рублях):"
    
    if callback.message.photo:
        await callback.message.delete()
        await callback.message.answer(text)
    else:
        try:
            await callback.message.edit_text(text)
        except:
            await callback.message.answer(text)
    
    await callback.answer()


@router.message(EditAdStates.waiting_for_new_price)
async def process_new_price(message: Message, state: FSMContext):
    """Обработка новой цены"""
    try:
        price = float(message.text.replace(" ", "").replace(",", "."))
        if price < 0:
            await message.answer("❌ Цена не может быть отрицательной")
            return
    except ValueError:
        await message.answer("❌ Введите число")
        return
    
    data = await state.get_data()
    ad_id = data.get("editing_ad_id")
    
    try:
        success = await AdQueries.update_ad(ad_id, price=price)
    except Exception as e:
        logger.error(f"Ошибка обновления: {e}")
        await message.answer("❌ Ошибка сохранения")
        return
    
    if success:
        await message.answer("✅ Цена обновлена!")
        await state.clear()
    else:
        await message.answer("❌ Ошибка обновления")


# =============================================================================
# ДЕАКТИВАЦИЯ/АКТИВАЦИЯ ОБЪЯВЛЕНИЯ
# =============================================================================

@router.callback_query(F.data.startswith("deactivate_ad_"))
async def deactivate_ad(callback: CallbackQuery):
    """Деактивировать объявление (в архив)"""
    ad_id = callback.data.replace("deactivate_ad_", "")
    
    try:
        ad = await AdQueries.get_ad(ad_id)
        if not ad or ad.user_id != callback.from_user.id:
            await callback.answer("❌ Объявление не найдено", show_alert=True)
            return
        
        success = await AdQueries.deactivate_ad(ad_id)
    except Exception as e:
        logger.error(f"Ошибка деактивации: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)
        return
    
    if success:
        await callback.answer("✅ В архив", show_alert=True)
        text = "📦 Объявление в архиве"
        
        if callback.message.photo:
            await callback.message.delete()
            await callback.message.answer(text, reply_markup=get_back_keyboard())
        else:
            try:
                await callback.message.edit_text(text, reply_markup=get_back_keyboard())
            except:
                await callback.message.answer(text, reply_markup=get_back_keyboard())
    else:
        await callback.answer("❌ Ошибка", show_alert=True)


@router.callback_query(F.data.startswith("activate_ad_"))
async def activate_ad(callback: CallbackQuery):
    """Активировать объявление"""
    ad_id = callback.data.replace("activate_ad_", "")
    
    try:
        ad = await AdQueries.get_ad(ad_id)
        if not ad or ad.user_id != callback.from_user.id:
            await callback.answer("❌ Объявление не найдено", show_alert=True)
            return
        
        success = await AdQueries.activate_ad(ad_id)
    except Exception as e:
        logger.error(f"Ошибка активации: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)
        return
    
    if success:
        await callback.answer("✅ Активировано", show_alert=True)
        # Показываем обновлённое объявление
        ad = await AdQueries.get_ad(ad_id)
        if ad:
            text = format_ad_detail_compact(ad)
            
            if callback.message.photo:
                await callback.message.delete()
                if ad.photos:
                    await callback.message.answer_photo(
                        photo=ad.photos[0],
                        caption=text,
                        reply_markup=get_ad_actions_keyboard(ad_id, is_owner=True)
                    )
                else:
                    await callback.message.answer(text, reply_markup=get_ad_actions_keyboard(ad_id, is_owner=True))
            else:
                try:
                    await callback.message.edit_text(text, reply_markup=get_ad_actions_keyboard(ad_id, is_owner=True))
                except:
                    await callback.message.answer(text, reply_markup=get_ad_actions_keyboard(ad_id, is_owner=True))
    else:
        await callback.answer("❌ Ошибка", show_alert=True)


# =============================================================================
# УДАЛЕНИЕ ОБЪЯВЛЕНИЯ
# =============================================================================

@router.callback_query(F.data.startswith("delete_ad_"))
async def confirm_delete_ad(callback: CallbackQuery):
    """Подтверждение удаления объявления"""
    ad_id = callback.data.replace("delete_ad_", "")
    
    try:
        ad = await AdQueries.get_ad(ad_id)
        if not ad or ad.user_id != callback.from_user.id:
            await callback.answer("❌ Объявление не найдено", show_alert=True)
            return
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)
        return
    
    title = ad.title[:30] + "..." if len(ad.title) > 30 else ad.title
    text = f"⚠️ Удалить '<b>{title}</b>'?\n\nЭто действие нельзя отменить!"
    
    if callback.message.photo:
        await callback.message.delete()
        await callback.message.answer(text, reply_markup=get_confirm_delete_keyboard(ad_id))
    else:
        try:
            await callback.message.edit_text(text, reply_markup=get_confirm_delete_keyboard(ad_id))
        except:
            await callback.message.answer(text, reply_markup=get_confirm_delete_keyboard(ad_id))
    
    await callback.answer()


@router.callback_query(F.data.startswith("confirm_delete_"))
async def delete_ad(callback: CallbackQuery):
    """Удалить объявление"""
    ad_id = callback.data.replace("confirm_delete_", "")
    
    try:
        ad = await AdQueries.get_ad(ad_id)
        if not ad or ad.user_id != callback.from_user.id:
            await callback.answer("❌ Объявление не найдено", show_alert=True)
            return
        
        success = await AdQueries.delete_ad(ad_id)
    except Exception as e:
        logger.error(f"Ошибка удаления: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)
        return
    
    if success:
        await callback.answer("✅ Удалено", show_alert=True)
        text = "🗑 Объявление удалено"
        
        if callback.message.photo:
            await callback.message.delete()
            await callback.message.answer(text, reply_markup=get_back_keyboard())
        else:
            try:
                await callback.message.edit_text(text, reply_markup=get_back_keyboard())
            except:
                await callback.message.answer(text, reply_markup=get_back_keyboard())
    else:
        await callback.answer("❌ Ошибка удаления", show_alert=True)


@router.callback_query(F.data == "cancel_delete")
async def cancel_delete(callback: CallbackQuery):
    """Отмена удаления"""
    await callback.answer("Отменено")
    text = "❌ Удаление отменено"
    
    if callback.message.photo:
        await callback.message.delete()
        await callback.message.answer(text, reply_markup=get_back_keyboard())
    else:
        try:
            await callback.message.edit_text(text, reply_markup=get_back_keyboard())
        except:
            await callback.message.answer(text, reply_markup=get_back_keyboard())


@router.callback_query(F.data == "noop")
async def noop_handler(callback: CallbackQuery):
    """Пустой обработчик для кнопок без действия (например, номер страницы)"""
    await callback.answer()


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
