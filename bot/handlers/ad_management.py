# bot/handlers/ad_management.py
"""Обработчик управления объявлениями пользователя"""

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
    await show_user_ads(message, message.from_user.id)

@router.callback_query(F.data == "my_ads")
async def callback_my_ads(callback: CallbackQuery):
    """Показать список объявлений пользователя (через callback)"""
    await show_user_ads(callback.message, callback.from_user.id, edit=True)
    await callback.answer()

async def show_user_ads(message: Message, user_id: int, edit: bool = False):
    """Вспомогательная функция для показа объявлений"""
    # Получаем объявления пользователя
    ads = await AdQueries.get_user_ads(user_id, limit=50)
    
    if not ads:
        text = "📋 <b>Ваши объявления</b>\n\n" \
               "У вас пока нет объявлений.\n" \
               "Создайте своё первое объявление!"
        
        if edit:
            # Проверяем тип сообщения
            if message.photo:
                await message.delete()
                await message.answer(text, reply_markup=get_back_keyboard())
            else:
                await message.edit_text(text, reply_markup=get_back_keyboard())
        else:
            await message.answer(text, reply_markup=get_back_keyboard())
        return
    
    # Формируем список объявлений
    text = f"📋 <b>Ваши объявления</b> ({len(ads)})\n\n"
    
    for i, ad in enumerate(ads, 1):
        status_emoji = {
            "active": "✅",
            "pending": "⏳",
            "archived": "📦",
            "rejected": "❌"
        }.get(ad.status, "❓")
        
        text += f"{i}. {status_emoji} <b>{ad.title}</b>\n"
        text += f"   💰 {ad.price} ₽ | 👁 {ad.views_count} | "
        text += f"📂 {CATEGORIES.get(ad.category, ad.category)}\n\n"
    
    text += "Нажмите на объявление, чтобы управлять им:"
    
    if edit:
        # Проверяем тип сообщения
        if message.photo:
            await message.delete()
            await message.answer(text, reply_markup=get_user_ads_keyboard(ads))
        else:
            await message.edit_text(text, reply_markup=get_user_ads_keyboard(ads))
    else:
        await message.answer(text, reply_markup=get_user_ads_keyboard(ads))

# =============================================================================
# ПРОСМОТР ДЕТАЛИ ОБЪЯВЛЕНИЯ
# =============================================================================

@router.callback_query(F.data.startswith("view_my_ad_"))
async def view_my_ad_detail(callback: CallbackQuery):
    """Просмотр деталей своего объявления"""
    ad_id = callback.data.replace("view_my_ad_", "")
    
    ad = await AdQueries.get_ad(ad_id)
    
    if not ad:
        await callback.answer("❌ Объявление не найдено", show_alert=True)
        return
    
    # Проверяем, что это объявление пользователя
    if ad.user_id != callback.from_user.id:
        await callback.answer("❌ Это не ваше объявление", show_alert=True)
        return
    
    # Формируем текст объявления
    text = format_ad_detail(ad)
    
    # Если есть фото, отправляем с фото
    if ad.photos and len(ad.photos) > 0:
        await callback.message.delete()
        await callback.message.answer_photo(
            photo=ad.photos[0],
            caption=text,
            reply_markup=get_ad_actions_keyboard(ad_id, is_owner=True)
        )
    else:
        await callback.message.edit_text(
            text,
            reply_markup=get_ad_actions_keyboard(ad_id, is_owner=True)
        )
    
    await callback.answer()

# =============================================================================
# РЕДАКТИРОВАНИЕ ОБЪЯВЛЕНИЯ
# =============================================================================

@router.callback_query(F.data.startswith("edit_ad_"))
async def start_edit_ad(callback: CallbackQuery, state: FSMContext):
    """Начать редактирование объявления"""
    ad_id = callback.data.replace("edit_ad_", "")
    
    ad = await AdQueries.get_ad(ad_id)
    
    if not ad or ad.user_id != callback.from_user.id:
        await callback.answer("❌ Объявление не найдено", show_alert=True)
        return
    
    # Сохраняем ID объявления в состояние
    await state.update_data(editing_ad_id=ad_id)
    
    text = f"""
📝 <b>Редактирование объявления</b>

<b>Текущие данные:</b>
📌 Заголовок: {ad.title}
📄 Описание: {ad.description[:100]}...
💰 Цена: {ad.price} ₽

<b>Что вы хотите изменить?</b>
"""
    
    from bot.keyboards.inline import get_edit_options_keyboard
    
    # Проверяем есть ли фото в текущем сообщении
    if callback.message.photo:
        await callback.message.delete()
        await callback.message.answer(text, reply_markup=get_edit_options_keyboard(ad_id))
    else:
        await callback.message.edit_text(text, reply_markup=get_edit_options_keyboard(ad_id))
    
    await callback.answer()

@router.callback_query(F.data.startswith("edit_title_"))
async def edit_ad_title(callback: CallbackQuery, state: FSMContext):
    """Редактировать заголовок"""
    ad_id = callback.data.replace("edit_title_", "")
    await state.update_data(editing_ad_id=ad_id)
    await state.set_state(EditAdStates.waiting_for_new_title)
    
    text = (
        "📝 <b>Введите новый заголовок</b>\n\n"
        "Максимум 100 символов.\n"
        "Или отправьте /cancel для отмены."
    )
    
    # Проверяем есть ли фото в текущем сообщении
    if callback.message.photo:
        await callback.message.delete()
        await callback.message.answer(text)
    else:
        await callback.message.edit_text(text)
    
    await callback.answer()

@router.message(EditAdStates.waiting_for_new_title)
async def process_new_title(message: Message, state: FSMContext):
    """Обработка нового заголовка"""
    if len(message.text) > 100:
        await message.answer("❌ Заголовок слишком длинный. Максимум 100 символов.")
        return
    
    data = await state.get_data()
    ad_id = data.get("editing_ad_id")
    
    success = await AdQueries.update_ad(ad_id, title=message.text)
    
    if success:
        await message.answer("✅ Заголовок успешно обновлён!")
        await state.clear()
        
        # Показываем обновлённое объявление
        ad = await AdQueries.get_ad(ad_id)
        if ad:
            text = format_ad_detail(ad)
            if ad.photos and len(ad.photos) > 0:
                await message.answer_photo(
                    photo=ad.photos[0],
                    caption=text,
                    reply_markup=get_ad_actions_keyboard(ad_id, is_owner=True)
                )
            else:
                await message.answer(text, reply_markup=get_ad_actions_keyboard(ad_id, is_owner=True))
    else:
        await message.answer("❌ Ошибка при обновлении заголовка")

@router.callback_query(F.data.startswith("edit_description_"))
async def edit_ad_description(callback: CallbackQuery, state: FSMContext):
    """Редактировать описание"""
    ad_id = callback.data.replace("edit_description_", "")
    await state.update_data(editing_ad_id=ad_id)
    await state.set_state(EditAdStates.waiting_for_new_description)
    
    text = (
        "📄 <b>Введите новое описание</b>\n\n"
        "Максимум 1000 символов.\n"
        "Или отправьте /cancel для отмены."
    )
    
    # Проверяем есть ли фото в текущем сообщении
    if callback.message.photo:
        await callback.message.delete()
        await callback.message.answer(text)
    else:
        await callback.message.edit_text(text)
    
    await callback.answer()

@router.message(EditAdStates.waiting_for_new_description)
async def process_new_description(message: Message, state: FSMContext):
    """Обработка нового описания"""
    if len(message.text) > 1000:
        await message.answer("❌ Описание слишком длинное. Максимум 1000 символов.")
        return
    
    data = await state.get_data()
    ad_id = data.get("editing_ad_id")
    
    success = await AdQueries.update_ad(ad_id, description=message.text)
    
    if success:
        await message.answer("✅ Описание успешно обновлено!")
        await state.clear()
        
        ad = await AdQueries.get_ad(ad_id)
        if ad:
            text = format_ad_detail(ad)
            if ad.photos and len(ad.photos) > 0:
                await message.answer_photo(
                    photo=ad.photos[0],
                    caption=text,
                    reply_markup=get_ad_actions_keyboard(ad_id, is_owner=True)
                )
            else:
                await message.answer(text, reply_markup=get_ad_actions_keyboard(ad_id, is_owner=True))
    else:
        await message.answer("❌ Ошибка при обновлении описания")

@router.callback_query(F.data.startswith("edit_price_"))
async def edit_ad_price(callback: CallbackQuery, state: FSMContext):
    """Редактировать цену"""
    ad_id = callback.data.replace("edit_price_", "")
    await state.update_data(editing_ad_id=ad_id)
    await state.set_state(EditAdStates.waiting_for_new_price)
    
    text = (
        "💰 <b>Введите новую цену</b>\n\n"
        "Только число в рублях.\n"
        "Или отправьте /cancel для отмены."
    )
    
    # Проверяем есть ли фото в текущем сообщении
    if callback.message.photo:
        await callback.message.delete()
        await callback.message.answer(text)
    else:
        await callback.message.edit_text(text)
    
    await callback.answer()

@router.message(EditAdStates.waiting_for_new_price)
async def process_new_price(message: Message, state: FSMContext):
    """Обработка новой цены"""
    try:
        price = float(message.text)
        if price < 0:
            await message.answer("❌ Цена не может быть отрицательной")
            return
    except ValueError:
        await message.answer("❌ Введите корректную цену (только число)")
        return
    
    data = await state.get_data()
    ad_id = data.get("editing_ad_id")
    
    success = await AdQueries.update_ad(ad_id, price=price)
    
    if success:
        await message.answer("✅ Цена успешно обновлена!")
        await state.clear()
        
        ad = await AdQueries.get_ad(ad_id)
        if ad:
            text = format_ad_detail(ad)
            if ad.photos and len(ad.photos) > 0:
                await message.answer_photo(
                    photo=ad.photos[0],
                    caption=text,
                    reply_markup=get_ad_actions_keyboard(ad_id, is_owner=True)
                )
            else:
                await message.answer(text, reply_markup=get_ad_actions_keyboard(ad_id, is_owner=True))
    else:
        await message.answer("❌ Ошибка при обновлении цены")

# =============================================================================
# ДЕАКТИВАЦИЯ/АКТИВАЦИЯ ОБЪЯВЛЕНИЯ
# =============================================================================

@router.callback_query(F.data.startswith("deactivate_ad_"))
async def deactivate_ad(callback: CallbackQuery):
    """Деактивировать объявление (в архив)"""
    ad_id = callback.data.replace("deactivate_ad_", "")
    
    ad = await AdQueries.get_ad(ad_id)
    if not ad or ad.user_id != callback.from_user.id:
        await callback.answer("❌ Объявление не найдено", show_alert=True)
        return
    
    success = await AdQueries.deactivate_ad(ad_id)
    
    if success:
        await callback.answer("✅ Объявление отправлено в архив", show_alert=True)
        
        text = (
            "📦 Объявление перемещено в архив.\n"
            "Вы можете активировать его снова в любое время."
        )
        
        # Проверяем есть ли фото в текущем сообщении
        if callback.message.photo:
            await callback.message.delete()
            await callback.message.answer(text, reply_markup=get_back_keyboard())
        else:
            await callback.message.edit_text(text, reply_markup=get_back_keyboard())
    else:
        await callback.answer("❌ Ошибка при деактивации", show_alert=True)

@router.callback_query(F.data.startswith("activate_ad_"))
async def activate_ad(callback: CallbackQuery):
    """Активировать объявление"""
    ad_id = callback.data.replace("activate_ad_", "")
    
    ad = await AdQueries.get_ad(ad_id)
    if not ad or ad.user_id != callback.from_user.id:
        await callback.answer("❌ Объявление не найдено", show_alert=True)
        return
    
    success = await AdQueries.activate_ad(ad_id)
    
    if success:
        await callback.answer("✅ Объявление активировано", show_alert=True)
        # Показываем обновлённое объявление
        ad = await AdQueries.get_ad(ad_id)  # Перезагружаем объявление
        if ad:
            text = format_ad_detail(ad)
            
            # Проверяем есть ли фото в текущем сообщении
            if callback.message.photo:
                await callback.message.delete()
                if ad.photos and len(ad.photos) > 0:
                    await callback.message.answer_photo(
                        photo=ad.photos[0],
                        caption=text,
                        reply_markup=get_ad_actions_keyboard(ad_id, is_owner=True)
                    )
                else:
                    await callback.message.answer(text, reply_markup=get_ad_actions_keyboard(ad_id, is_owner=True))
            else:
                await callback.message.edit_text(text, reply_markup=get_ad_actions_keyboard(ad_id, is_owner=True))
    else:
        await callback.answer("❌ Ошибка при активации", show_alert=True)

# =============================================================================
# УДАЛЕНИЕ ОБЪЯВЛЕНИЯ
# =============================================================================

@router.callback_query(F.data.startswith("delete_ad_"))
async def confirm_delete_ad(callback: CallbackQuery):
    """Подтверждение удаления объявления"""
    ad_id = callback.data.replace("delete_ad_", "")
    
    ad = await AdQueries.get_ad(ad_id)
    if not ad or ad.user_id != callback.from_user.id:
        await callback.answer("❌ Объявление не найдено", show_alert=True)
        return
    
    text = (
        f"⚠️ <b>Вы уверены?</b>\n\n"
        f"Объявление '<b>{ad.title}</b>' будет удалено.\n"
        f"Это действие нельзя отменить!"
    )
    
    # Проверяем есть ли фото в текущем сообщении
    if callback.message.photo:
        # Если есть фото, удаляем сообщение и отправляем новое
        await callback.message.delete()
        await callback.message.answer(
            text,
            reply_markup=get_confirm_delete_keyboard(ad_id)
        )
    else:
        # Если нет фото, просто редактируем текст
        await callback.message.edit_text(
            text,
            reply_markup=get_confirm_delete_keyboard(ad_id)
        )
    
    await callback.answer()

@router.callback_query(F.data.startswith("confirm_delete_"))
async def delete_ad(callback: CallbackQuery):
    """Удалить объявление"""
    ad_id = callback.data.replace("confirm_delete_", "")
    
    ad = await AdQueries.get_ad(ad_id)
    if not ad or ad.user_id != callback.from_user.id:
        await callback.answer("❌ Объявление не найдено", show_alert=True)
        return
    
    success = await AdQueries.delete_ad(ad_id)
    
    if success:
        await callback.answer("✅ Объявление удалено", show_alert=True)
        
        text = (
            "🗑 <b>Объявление удалено</b>\n\n"
            "Объявление больше не отображается в каталоге."
        )
        
        # Проверяем есть ли фото в текущем сообщении
        if callback.message.photo:
            await callback.message.delete()
            await callback.message.answer(text, reply_markup=get_back_keyboard())
        else:
            await callback.message.edit_text(text, reply_markup=get_back_keyboard())
    else:
        await callback.answer("❌ Ошибка при удалении", show_alert=True)

@router.callback_query(F.data == "cancel_delete")
async def cancel_delete(callback: CallbackQuery):
    """Отмена удаления"""
    await callback.answer("Удаление отменено")
    
    text = "Удаление отменено"
    
    # Проверяем есть ли фото в текущем сообщении
    if callback.message.photo:
        await callback.message.delete()
        await callback.message.answer(text, reply_markup=get_back_keyboard())
    else:
        await callback.message.edit_text(text, reply_markup=get_back_keyboard())

# =============================================================================
# ОТМЕНА РЕДАКТИРОВАНИЯ
# =============================================================================

@router.message(F.text == "/cancel")
async def cancel_editing(message: Message, state: FSMContext):
    """Отмена редактирования"""
    current_state = await state.get_state()
    if current_state:
        await state.clear()
        await message.answer("❌ Редактирование отменено", reply_markup=get_back_keyboard())
    else:
        await message.answer("Нечего отменять")
