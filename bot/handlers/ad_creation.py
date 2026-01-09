# bot/handlers/ad_creation.py
"""
Обработчики создания объявлений

ИСПРАВЛЕНО:
1. При запросе фото - только кнопка "Пропустить"
2. После загрузки фото - только кнопка "Далее" (без Пропустить)
3. Retry логика для сетевых ошибок
"""

import logging
import asyncio
from datetime import datetime
import uuid
from typing import Dict

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.database.connection import get_db_session
from bot.database.models import Ad, AdStatus

from shared.regions_config import (
    REGIONS, CATEGORIES, SUBCATEGORIES, DEAL_TYPES,
    CONDITION_TYPES, DELIVERY_TYPES, CATEGORIES_WITH_DELIVERY
)

logger = logging.getLogger(__name__)
router = Router()

# Хранилище для обработки медиагрупп
media_group_data: Dict[str, dict] = {}

# ========== FSM STATES ==========

class AdCreation(StatesGroup):
    region = State()
    category = State()
    subcategory = State()
    deal_type = State()
    title = State()
    description = State()
    condition = State()
    photos = State()
    video = State()
    price = State()
    delivery = State()
    confirm = State()

# ========== РЕГИОН ==========

@router.callback_query(F.data == "new_ad")
async def start_creation_callback(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    await state.update_data(history_messages=[], photos=[])
    await ask_region(callback.message, state)

@router.message(F.text == "Создать объявление")
@router.message(F.text == "Подать объявление")
@router.message(F.text == "📝 Подать объявление")
@router.message(F.text == "/create")
async def start_creation(message: Message, state: FSMContext):
    await state.clear()
    await state.update_data(history_messages=[], photos=[])
    await ask_region(message, state)

async def ask_region(message: Message, state: FSMContext):
    await state.set_state(AdCreation.region)
    from bot.keyboards.inline import get_regions_keyboard
    msg = await message.answer(
        "📍 <b>Шаг 1: Регион</b>\n\nВыберите регион для размещения объявления:",
        reply_markup=get_regions_keyboard()
    )
    data = await state.get_data()
    history = data.get('history_messages', [])
    history.append(msg.message_id)
    await state.update_data(history_messages=history)

@router.callback_query(AdCreation.region, F.data.startswith("region_"))
async def process_region(callback: CallbackQuery, state: FSMContext):
    region = callback.data.replace("region_", "")
    await state.update_data(region=region)
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except:
        pass
    region_name = REGIONS.get(region, region)
    msg = await callback.message.answer(f"✅ <b>Регион:</b> {region_name}")
    data = await state.get_data()
    history = data.get('history_messages', [])
    history.append(msg.message_id)
    await state.update_data(history_messages=history)
    await ask_category(callback.message, state)
    await callback.answer()

# ========== КАТЕГОРИЯ ==========

async def ask_category(message: Message, state: FSMContext):
    await state.set_state(AdCreation.category)
    from bot.keyboards.inline import get_categories_keyboard
    msg = await message.answer(
        "📂 <b>Шаг 2: Категория</b>\n\nВыберите категорию товара:",
        reply_markup=get_categories_keyboard()
    )
    data = await state.get_data()
    history = data.get('history_messages', [])
    history.append(msg.message_id)
    await state.update_data(history_messages=history)

@router.callback_query(AdCreation.category, F.data.startswith("category_"))
async def process_category(callback: CallbackQuery, state: FSMContext):
    category = callback.data.replace("category_", "")
    await state.update_data(category=category)
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except:
        pass
    category_name = CATEGORIES.get(category, category)
    msg = await callback.message.answer(f"✅ <b>Категория:</b> {category_name}")
    data = await state.get_data()
    history = data.get('history_messages', [])
    history.append(msg.message_id)
    await state.update_data(history_messages=history)
    await ask_subcategory(callback.message, state, category)
    await callback.answer()

# ========== РУБРИКА ==========

async def ask_subcategory(message: Message, state: FSMContext, category: str):
    await state.set_state(AdCreation.subcategory)
    from bot.keyboards.inline import get_subcategories_keyboard
    msg = await message.answer(
        "📑 <b>Шаг 3: Рубрика</b>\n\nВыберите рубрику:",
        reply_markup=get_subcategories_keyboard(category)
    )
    data = await state.get_data()
    history = data.get('history_messages', [])
    history.append(msg.message_id)
    await state.update_data(history_messages=history)

@router.callback_query(AdCreation.subcategory, F.data.startswith("subcategory_"))
async def process_subcategory(callback: CallbackQuery, state: FSMContext):
    subcategory = callback.data.replace("subcategory_", "")
    await state.update_data(subcategory=subcategory)
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except:
        pass
    data = await state.get_data()
    category = data.get('category')
    subcategory_name = SUBCATEGORIES.get(category, {}).get(subcategory, subcategory)
    msg = await callback.message.answer(f"✅ <b>Рубрика:</b> {subcategory_name}")
    history = data.get('history_messages', [])
    history.append(msg.message_id)
    await state.update_data(history_messages=history)
    await ask_deal_type(callback.message, state)
    await callback.answer()

# ========== ТИП СДЕЛКИ ==========

async def ask_deal_type(message: Message, state: FSMContext):
    await state.set_state(AdCreation.deal_type)
    from bot.keyboards.inline import get_deal_types_keyboard
    msg = await message.answer(
        "💼 <b>Шаг 4: Тип сделки</b>\n\nЧто вы хотите сделать?",
        reply_markup=get_deal_types_keyboard()
    )
    data = await state.get_data()
    history = data.get('history_messages', [])
    history.append(msg.message_id)
    await state.update_data(history_messages=history)

@router.callback_query(AdCreation.deal_type, F.data.startswith("deal_"))
async def process_deal_type(callback: CallbackQuery, state: FSMContext):
    deal_type = callback.data.replace("deal_", "")
    await state.update_data(deal_type=deal_type)
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except:
        pass
    deal_type_name = DEAL_TYPES.get(deal_type, deal_type)
    msg = await callback.message.answer(f"✅ <b>Тип сделки:</b> {deal_type_name}")
    data = await state.get_data()
    history = data.get('history_messages', [])
    history.append(msg.message_id)
    await state.update_data(history_messages=history)
    await ask_title(callback.message, state)
    await callback.answer()

# ========== ЗАГОЛОВОК ==========

async def ask_title(message: Message, state: FSMContext):
    await state.set_state(AdCreation.title)
    msg = await message.answer(
        "📝 <b>Шаг 5: Заголовок</b>\n\nВведите краткий заголовок объявления (до 100 символов):"
    )
    data = await state.get_data()
    history = data.get('history_messages', [])
    history.append(msg.message_id)
    await state.update_data(history_messages=history)

@router.message(AdCreation.title)
async def process_title(message: Message, state: FSMContext):
    title = message.text.strip()
    if len(title) > 100:
        await message.answer("❌ Заголовок слишком длинный. Максимум 100 символов.")
        return
    await state.update_data(title=title)
    msg = await message.answer(f"✅ <b>Заголовок:</b> {title}")
    data = await state.get_data()
    history = data.get('history_messages', [])
    history.append(message.message_id)
    history.append(msg.message_id)
    await state.update_data(history_messages=history)
    await ask_description(message, state)

# ========== ОПИСАНИЕ ==========

async def ask_description(message: Message, state: FSMContext):
    await state.set_state(AdCreation.description)
    msg = await message.answer(
        "📄 <b>Шаг 6: Описание</b>\n\nОпишите товар подробно (до 3000 символов):"
    )
    data = await state.get_data()
    history = data.get('history_messages', [])
    history.append(msg.message_id)
    await state.update_data(history_messages=history)

@router.message(AdCreation.description)
async def process_description(message: Message, state: FSMContext):
    description = message.text.strip()
    if len(description) > 3000:
        await message.answer("❌ Описание слишком длинное. Максимум 3000 символов.")
        return
    await state.update_data(description=description)
    desc_preview = description[:100] + "..." if len(description) > 100 else description
    msg = await message.answer(f"✅ <b>Описание:</b> {desc_preview}")
    data = await state.get_data()
    history = data.get('history_messages', [])
    history.append(message.message_id)
    history.append(msg.message_id)
    await state.update_data(history_messages=history)
    await ask_condition(message, state)

# ========== СОСТОЯНИЕ ==========

async def ask_condition(message: Message, state: FSMContext):
    await state.set_state(AdCreation.condition)
    from bot.keyboards.inline import get_condition_keyboard
    msg = await message.answer(
        "🔧 <b>Шаг 7: Состояние</b>\n\nУкажите состояние товара:",
        reply_markup=get_condition_keyboard()
    )
    data = await state.get_data()
    history = data.get('history_messages', [])
    history.append(msg.message_id)
    await state.update_data(history_messages=history)

@router.callback_query(AdCreation.condition, F.data.startswith("condition_"))
async def process_condition(callback: CallbackQuery, state: FSMContext):
    condition = callback.data.replace("condition_", "")
    await state.update_data(condition=condition)
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except:
        pass
    condition_name = CONDITION_TYPES.get(condition, condition)
    msg = await callback.message.answer(f"✅ <b>Состояние:</b> {condition_name}")
    data = await state.get_data()
    history = data.get('history_messages', [])
    history.append(msg.message_id)
    await state.update_data(history_messages=history)
    await ask_photos(callback.message, state)
    await callback.answer()

# ========== ФОТОГРАФИИ (ИСПРАВЛЕННАЯ ЛОГИКА) ==========

async def ask_photos(message: Message, state: FSMContext):
    """
    Запрос фотографий.
    Показываем ТОЛЬКО кнопку "Пропустить".
    """
    await state.set_state(AdCreation.photos)
    await state.update_data(
        photos=[],
        photo_progress_msg_id=None,
        photo_prompt_msg_id=None,
        processed_media_groups=[]
    )
    
    # ТОЛЬКО кнопка Пропустить
    from bot.keyboards.inline import get_photo_skip_keyboard
    msg = await message.answer(
        "📸 <b>Шаг 8: Фотографии</b>\n\n"
        "Отправьте фото товара (до 10 штук).\n"
        "Можно отправить сразу несколько или по одному.\n\n"
        "Если фото нет — нажмите <b>Пропустить</b>.",
        reply_markup=get_photo_skip_keyboard()
    )
    
    data = await state.get_data()
    history = data.get('history_messages', [])
    history.append(msg.message_id)
    await state.update_data(history_messages=history, photo_prompt_msg_id=msg.message_id)

@router.callback_query(AdCreation.photos, F.data == "skip_photos")
async def skip_photos(callback: CallbackQuery, state: FSMContext):
    """Пропустить фотографии"""
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except:
        pass
    msg = await callback.message.answer("⏭️ <b>Фото пропущены</b>")
    data = await state.get_data()
    history = data.get('history_messages', [])
    history.append(msg.message_id)
    await state.update_data(history_messages=history)
    await ask_video(callback.message, state)
    await callback.answer()

@router.callback_query(AdCreation.photos, F.data == "photos_done")
async def photos_done(callback: CallbackQuery, state: FSMContext):
    """Завершение загрузки фото"""
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except:
        pass
    data = await state.get_data()
    photos = data.get('photos', [])
    msg = await callback.message.answer(f"✅ <b>Загружено фото:</b> {len(photos)} шт.")
    history = data.get('history_messages', [])
    history.append(msg.message_id)
    await state.update_data(history_messages=history)
    await ask_video(callback.message, state)
    await callback.answer()

@router.message(AdCreation.photos, F.photo)
async def process_photo(message: Message, state: FSMContext):
    """Обработка фото с поддержкой медиагрупп"""
    global media_group_data
    data = await state.get_data()
    photos = data.get("photos", [])
    processed_groups = data.get("processed_media_groups", [])
    
    if len(photos) >= 10:
        await message.answer("⚠️ Достигнут лимит в 10 фото. Нажмите <b>Далее</b>.")
        return
    
    photo_id = message.photo[-1].file_id
    media_group_id = message.media_group_id
    
    if media_group_id:
        if media_group_id in processed_groups:
            return
        if media_group_id not in media_group_data:
            media_group_data[media_group_id] = {"photos": [], "chat_id": message.chat.id}
        current_total = len(photos) + len(media_group_data[media_group_id]["photos"])
        if photo_id not in media_group_data[media_group_id]["photos"] and current_total < 10:
            media_group_data[media_group_id]["photos"].append(photo_id)
        asyncio.create_task(process_media_group_delayed(media_group_id, message, state))
    else:
        if photo_id not in photos:
            photos.append(photo_id)
            await state.update_data(photos=photos)
            await show_photo_progress(message, state, len(photos))

async def process_media_group_delayed(media_group_id: str, message: Message, state: FSMContext):
    """Отложенная обработка медиагруппы"""
    global media_group_data
    await asyncio.sleep(1.0)
    if media_group_id not in media_group_data:
        return
    group_photos = media_group_data[media_group_id]["photos"]
    data = await state.get_data()
    photos = data.get("photos", [])
    processed_groups = data.get("processed_media_groups", [])
    if media_group_id in processed_groups:
        del media_group_data[media_group_id]
        return
    for photo_id in group_photos:
        if len(photos) < 10 and photo_id not in photos:
            photos.append(photo_id)
    processed_groups.append(media_group_id)
    await state.update_data(photos=photos, processed_media_groups=processed_groups)
    del media_group_data[media_group_id]
    await show_photo_progress(message, state, len(photos))

async def show_photo_progress(message: Message, state: FSMContext, photo_count: int):
    """
    Показать прогресс загрузки фото.
    После загрузки - ТОЛЬКО кнопка "Далее" (без Пропустить).
    """
    from bot.keyboards.inline import get_photo_done_keyboard
    
    data = await state.get_data()
    
    # Удаляем предыдущее сообщение о прогрессе
    old_msg_id = data.get('photo_progress_msg_id')
    if old_msg_id:
        try:
            await message.bot.delete_message(message.chat.id, old_msg_id)
        except:
            pass
    
    # Удаляем первоначальное сообщение с кнопкой "Пропустить"
    prompt_msg_id = data.get('photo_prompt_msg_id')
    if prompt_msg_id:
        try:
            await message.bot.delete_message(message.chat.id, prompt_msg_id)
            await state.update_data(photo_prompt_msg_id=None)  # Больше не удаляем
        except:
            pass
    
    # Формируем текст
    if photo_count >= 10:
        text = f"✅ <b>Загружено {photo_count} из 10 фото.</b>\n\nНажмите <b>Далее</b>."
    else:
        text = f"✅ <b>Загружено {photo_count} из 10 фото.</b>\n\nДобавьте ещё или нажмите <b>Далее</b>."
    
    # ТОЛЬКО кнопка "Далее"
    msg = await message.answer(text, reply_markup=get_photo_done_keyboard())
    await state.update_data(photo_progress_msg_id=msg.message_id)

# ========== ВИДЕО ==========

async def ask_video(message: Message, state: FSMContext):
    await state.set_state(AdCreation.video)
    from bot.keyboards.inline import get_skip_keyboard
    msg = await message.answer(
        "🎥 <b>Шаг 9: Видео</b>\n\nОтправьте видео (до 100 МБ) или нажмите <b>Пропустить</b>:",
        reply_markup=get_skip_keyboard()
    )
    data = await state.get_data()
    history = data.get('history_messages', [])
    history.append(msg.message_id)
    await state.update_data(history_messages=history)

@router.callback_query(AdCreation.video, F.data == "skip_video")
async def skip_video(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except:
        pass
    msg = await callback.message.answer("⏭️ <b>Видео пропущено</b>")
    data = await state.get_data()
    history = data.get('history_messages', [])
    history.append(msg.message_id)
    await state.update_data(history_messages=history)
    await ask_price(callback.message, state)
    await callback.answer()

@router.message(AdCreation.video, F.video)
async def process_video(message: Message, state: FSMContext):
    video = message.video
    if video.file_size and video.file_size > 104857600:
        await message.answer("❌ Видео слишком большое. Максимум 100 МБ.")
        return
    await state.update_data(video=video.file_id)
    msg = await message.answer("✅ <b>Видео загружено</b>")
    data = await state.get_data()
    history = data.get('history_messages', [])
    history.append(message.message_id)
    history.append(msg.message_id)
    await state.update_data(history_messages=history)
    await ask_price(message, state)

# ========== ЦЕНА ==========

async def ask_price(message: Message, state: FSMContext):
    await state.set_state(AdCreation.price)
    from bot.keyboards.inline import get_price_keyboard
    msg = await message.answer(
        "💰 <b>Шаг 10: Цена</b>\n\nУкажите цену в рублях (только цифры) или нажмите <b>Договорная</b>:",
        reply_markup=get_price_keyboard()
    )
    data = await state.get_data()
    history = data.get('history_messages', [])
    history.append(msg.message_id)
    await state.update_data(history_messages=history)

@router.callback_query(AdCreation.price, F.data == "negotiable")
async def price_negotiable(callback: CallbackQuery, state: FSMContext):
    await state.update_data(price="Договорная")
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except:
        pass
    msg = await callback.message.answer("✅ <b>Цена:</b> Договорная")
    data = await state.get_data()
    history = data.get('history_messages', [])
    history.append(msg.message_id)
    await state.update_data(history_messages=history)
    await check_delivery_needed(callback.message, state)
    await callback.answer()

@router.message(AdCreation.price)
async def process_price(message: Message, state: FSMContext):
    price_text = message.text.strip()
    price_clean = price_text.replace(" ", "").replace(",", "").replace(".", "")
    if not price_clean.isdigit():
        await message.answer("❌ Введите только цифры (например: 5000)")
        return
    price = int(price_clean)
    if price < 0:
        await message.answer("❌ Цена не может быть отрицательной")
        return
    await state.update_data(price=f"{price} ₽")
    msg = await message.answer(f"✅ <b>Цена:</b> {price} ₽")
    data = await state.get_data()
    history = data.get('history_messages', [])
    history.append(message.message_id)
    history.append(msg.message_id)
    await state.update_data(history_messages=history)
    await check_delivery_needed(message, state)

# ========== ДОСТАВКА ==========

async def check_delivery_needed(message: Message, state: FSMContext):
    data = await state.get_data()
    category = data.get('category')
    if category in CATEGORIES_WITH_DELIVERY:
        await state.set_state(AdCreation.delivery)
        from bot.keyboards.inline import get_delivery_keyboard
        msg = await message.answer(
            "🚚 <b>Шаг 11: Доставка</b>\n\nВыберите способ доставки:",
            reply_markup=get_delivery_keyboard()
        )
        history = data.get('history_messages', [])
        history.append(msg.message_id)
        await state.update_data(history_messages=history)
    else:
        await show_preview(message, state)

@router.callback_query(AdCreation.delivery, F.data.startswith("delivery_"))
async def process_delivery(callback: CallbackQuery, state: FSMContext):
    delivery = callback.data.replace("delivery_", "")
    await state.update_data(delivery=delivery)
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except:
        pass
    delivery_name = DELIVERY_TYPES.get(delivery, delivery)
    msg = await callback.message.answer(f"✅ <b>Доставка:</b> {delivery_name}")
    data = await state.get_data()
    history = data.get('history_messages', [])
    history.append(msg.message_id)
    await state.update_data(history_messages=history)
    await show_preview(callback.message, state)
    try:
        await callback.answer()
    except:
        pass

# ========== ПРЕВЬЮ (С RETRY) ==========

async def send_with_retry(coro, retries=3, delay=1):
    """Отправка с повторными попытками при сетевых ошибках"""
    for attempt in range(retries):
        try:
            return await coro
        except Exception as e:
            if "ServerDisconnectedError" in str(e) or "NetworkError" in str(e):
                if attempt < retries - 1:
                    logger.warning(f"Сетевая ошибка, попытка {attempt + 2}/{retries}")
                    await asyncio.sleep(delay)
                    continue
            raise
    return None

async def show_preview(message: Message, state: FSMContext):
    logger.info("Показ превью объявления")
    data = await state.get_data()
    await state.set_state(AdCreation.confirm)
    
    from bot.utils.formatters import format_ad_preview
    from aiogram.types import InputMediaPhoto, InputMediaVideo
    from bot.keyboards.inline import get_confirm_with_edit_keyboard
    
    preview_text = format_ad_preview(data)
    if len(preview_text) > 1024:
        preview_text = preview_text[:1020] + "..."
    
    photos = data.get('photos', [])
    video = data.get('video')
    logger.info(f"Превью: {len(photos)} фото, видео: {bool(video)}")
    
    try:
        if video and photos:
            media_group = [InputMediaVideo(media=video, caption=preview_text)]
            for photo in photos[:9]:
                media_group.append(InputMediaPhoto(media=photo))
            await send_with_retry(message.answer_media_group(media=media_group))
            msg = await message.answer("👆 <b>Ваше объявление</b>\n\nВсё верно?", reply_markup=get_confirm_with_edit_keyboard())
        elif video:
            msg = await send_with_retry(message.answer_video(video=video, caption=preview_text, reply_markup=get_confirm_with_edit_keyboard()))
        elif photos:
            if len(photos) == 1:
                msg = await send_with_retry(message.answer_photo(photo=photos[0], caption=preview_text, reply_markup=get_confirm_with_edit_keyboard()))
            else:
                media_group = [InputMediaPhoto(media=photos[0], caption=preview_text)]
                for photo in photos[1:10]:
                    media_group.append(InputMediaPhoto(media=photo))
                await send_with_retry(message.answer_media_group(media=media_group))
                msg = await message.answer("👆 <b>Ваше объявление</b>\n\nВсё верно?", reply_markup=get_confirm_with_edit_keyboard())
        else:
            msg = await message.answer(preview_text, reply_markup=get_confirm_with_edit_keyboard())
        
        history = data.get('history_messages', [])
        history.append(msg.message_id)
        await state.update_data(history_messages=history)
        logger.info("Превью успешно отправлено")
    except Exception as e:
        logger.error(f"Ошибка при отправке превью: {e}", exc_info=True)
        # Упрощённое превью без медиа
        msg = await message.answer(
            f"📢 <b>Превью</b>\n\n{preview_text[:800]}...\n\n📸 Фото: {len(photos)} шт.",
            reply_markup=get_confirm_with_edit_keyboard()
        )

# ========== ПУБЛИКАЦИЯ ==========

@router.callback_query(AdCreation.confirm, F.data == "confirm_publish")
async def confirm_ad(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except:
        pass
    try:
        await callback.answer("⏳ Создаём объявление...")
    except:
        pass
    
    try:
        bot_info = await callback.message.bot.get_me()
        async with get_db_session() as session:
            price_str = data.get('price', 'Договорная')
            price_value = None if price_str == 'Договорная' else float(price_str.replace(' ₽', '').replace(' ', ''))
            ad = Ad(
                id=uuid.uuid4(),
                user_id=callback.from_user.id,
                title=data.get('title', ''),
                description=data.get('description', ''),
                price=price_value,
                region=data.get('region'),
                category=data.get('category'),
                ad_type=data.get('deal_type'),
                photos=data.get('photos', []),
                video=data.get('video'),
                status=AdStatus.ACTIVE.value,
                created_at=datetime.utcnow(),
                premium_features={
                    'subcategory': data.get('subcategory'),
                    'condition': data.get('condition'),
                    'delivery': data.get('delivery'),
                    'price_text': data.get('price')
                }
            )
            session.add(ad)
            await session.commit()
        
        await callback.message.answer(f"✅ <b>Объявление создано!</b>\n\nID: <code>{ad.id}</code>")
        await publish_to_channel(callback.message.bot, bot_info, ad, data)
    except Exception as e:
        logger.error(f"Ошибка создания: {e}", exc_info=True)
        await callback.message.answer("❌ Ошибка при создании объявления. Попробуйте позже.")
    await state.clear()

@router.callback_query(AdCreation.confirm, F.data == "cancel_ad")
async def cancel_ad(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except:
        pass
    await state.clear()
    await callback.message.answer("❌ Создание отменено.")
    await callback.answer()

@router.callback_query(AdCreation.confirm, F.data == "edit_ad")
async def edit_ad_preview(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except:
        pass
    await callback.message.answer("✏️ <b>Редактирование в разработке</b>\n\nСоздайте объявление заново.")
    await callback.answer()

# ========== ПУБЛИКАЦИЯ В КАНАЛ ==========

def format_channel_ad_text(data: dict, bot_username: str, user_id: int) -> str:
    """Формат объявления для канала"""
    subcategory = data.get('subcategory', '')
    deal_type = data.get('deal_type', '')
    condition = data.get('condition')
    title = data.get('title', '')
    description = data.get('description', '')
    price = data.get('price', 'Договорная')
    delivery = data.get('delivery')
    
    hashtag = f"#{subcategory.replace('_', '').replace('-', '')}" if subcategory else ""
    deal_name = DEAL_TYPES.get(deal_type, '')
    cond_name = CONDITION_TYPES.get(condition, '') if condition else ""
    type_line = deal_name
    if cond_name:
        type_line += f" / {cond_name}"
    
    price_line = f"💰 {price}"
    if delivery:
        price_line += f" | {DELIVERY_TYPES.get(delivery, '')}"
    
    bot_link = f"https://t.me/{bot_username}"
    user_link = f"tg://user?id={user_id}"
    profile_link = f"https://t.me/{bot_username}?start=profile_{user_id}"
    
    lines = []
    if hashtag:
        lines.append(hashtag)
        lines.append("")
    if type_line:
        lines.append(type_line)
        lines.append("")
    if title:
        lines.append(f"<b>{title}</b>")
        lines.append("")
    if description:
        desc = description[:700] + "..." if len(description) > 700 else description
        lines.append(desc)
        lines.append("")
    lines.append(price_line)
    lines.append("")
    lines.append("━━━━━━━━━━━━━━━")
    lines.append(f'📢 <a href="{bot_link}">Разместить объявление</a>')
    lines.append(f'😎 <a href="{user_link}">Написать продавцу</a>')
    lines.append(f'👾 <a href="{profile_link}">Профиль продавца</a>')
    
    return "\n".join(lines)

async def publish_to_channel(bot, bot_info, ad, data):
    """Публикация в каналы"""
    from shared.regions_config import CHANNELS_CONFIG
    from aiogram.types import InputMediaPhoto, InputMediaVideo
    
    region = data.get('region', '')
    category = data.get('category', '')
    
    config = CHANNELS_CONFIG.get(region, {})
    cat_channel = config.get('categories', {}).get(category)
    main_channel = config.get('main')
    
    text = format_channel_ad_text(data, bot_info.username, ad.user_id)
    if len(text) > 1024:
        text = text[:1020] + "..."
    
    photos = data.get('photos', [])
    video = data.get('video')
    
    channels = []
    if cat_channel:
        channels.append(('категорию', cat_channel))
    if main_channel:
        channels.append(('главный', main_channel))
    
    for name, channel in channels:
        try:
            logger.info(f"Публикация в {name}: {channel}")
            if video and photos:
                media = [InputMediaVideo(media=video, caption=text, parse_mode="HTML")]
                for p in photos[:9]:
                    media.append(InputMediaPhoto(media=p))
                await send_with_retry(bot.send_media_group(chat_id=channel, media=media))
            elif video:
                await send_with_retry(bot.send_video(chat_id=channel, video=video, caption=text, parse_mode="HTML"))
            elif photos:
                if len(photos) == 1:
                    await send_with_retry(bot.send_photo(chat_id=channel, photo=photos[0], caption=text, parse_mode="HTML"))
                else:
                    media = [InputMediaPhoto(media=photos[0], caption=text, parse_mode="HTML")]
                    for p in photos[1:10]:
                        media.append(InputMediaPhoto(media=p))
                    await send_with_retry(bot.send_media_group(chat_id=channel, media=media))
            else:
                await send_with_retry(bot.send_message(chat_id=channel, text=text, parse_mode="HTML"))
            logger.info(f"Опубликовано в {name}")
        except Exception as e:
            logger.error(f"Ошибка публикации в {name}: {e}", exc_info=True)

# ========== ОТМЕНА ==========

@router.callback_query(F.data == "cancel_creation")
async def cancel_creation(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except:
        pass
    await callback.message.answer("❌ Создание отменено.")
    await callback.answer()
