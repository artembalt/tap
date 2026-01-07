# bot/handlers/ad_creation.py
"""
Обработчики создания объявлений

НОВЫЕ ФУНКЦИИ:
1. Обработка медиагрупп (можно загружать сразу много фото)
2. Сообщение после каждой загрузки фото
3. Автоматическое скрытие кнопок после использования
4. Рубрики как хэштеги в объявлениях
5. История сообщений (видимая история выборов)
"""

import logging
from datetime import datetime
import uuid
from typing import Optional

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

# ========== FSM STATES ==========

class AdCreation(StatesGroup):
    """Состояния создания объявления"""
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
    """Начало создания объявления (через callback кнопку)"""
    await callback.answer()
    await state.clear()
    await state.update_data(history_messages=[])
    await ask_region(callback.message, state)

@router.message(F.text == "Создать объявление")
@router.message(F.text == "Подать объявление")
@router.message(F.text == "/create")
async def start_creation(message: Message, state: FSMContext):
    """Начало создания объявления (через текстовое сообщение)"""
    await state.clear()
    await state.update_data(history_messages=[])
    await ask_region(message, state)

async def ask_region(message: Message, state: FSMContext):
    """Запрос региона"""
    await state.set_state(AdCreation.region)
    
    from bot.keyboards.inline import get_regions_keyboard
    msg = await message.answer(
        "📍 <b>Шаг 1: Регион</b>\n\n"
        "Выберите регион для размещения объявления:",
        reply_markup=get_regions_keyboard()
    )
    
    # Сохраняем в историю
    data = await state.get_data()
    history = data.get('history_messages', [])
    history.append(msg.message_id)
    await state.update_data(history_messages=history)

@router.callback_query(AdCreation.region, F.data.startswith("region_"))
async def process_region(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора региона"""
    region = callback.data.replace("region_", "")
    await state.update_data(region=region)
    
    # Прячем кнопки
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except:
        pass
    
    # Показываем выбор с галочкой
    region_name = REGIONS.get(region, region)
    msg = await callback.message.answer(
        f"✅ <b>Регион:</b> {region_name}"
    )
    
    # Добавляем в историю
    data = await state.get_data()
    history = data.get('history_messages', [])
    history.append(msg.message_id)
    await state.update_data(history_messages=history)
    
    await ask_category(callback.message, state)
    await callback.answer()

# ========== КАТЕГОРИЯ ==========

async def ask_category(message: Message, state: FSMContext):
    """Запрос категории"""
    await state.set_state(AdCreation.category)
    
    from bot.keyboards.inline import get_categories_keyboard
    msg = await message.answer(
        "📂 <b>Шаг 2: Категория</b>\n\n"
        "Выберите категорию товара:",
        reply_markup=get_categories_keyboard()
    )
    
    data = await state.get_data()
    history = data.get('history_messages', [])
    history.append(msg.message_id)
    await state.update_data(history_messages=history)

@router.callback_query(AdCreation.category, F.data.startswith("category_"))
async def process_category(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора категории"""
    category = callback.data.replace("category_", "")
    await state.update_data(category=category)
    
    # Прячем кнопки
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except:
        pass
    
    # Показываем выбор с галочкой
    category_name = CATEGORIES.get(category, category)
    msg = await callback.message.answer(
        f"✅ <b>Категория:</b> {category_name}"
    )
    
    data = await state.get_data()
    history = data.get('history_messages', [])
    history.append(msg.message_id)
    await state.update_data(history_messages=history)
    
    await ask_subcategory(callback.message, state, category)
    await callback.answer()

# ========== РУБРИКА ==========

async def ask_subcategory(message: Message, state: FSMContext, category: str):
    """Запрос рубрики (подкатегории)"""
    await state.set_state(AdCreation.subcategory)
    
    from bot.keyboards.inline import get_subcategories_keyboard
    msg = await message.answer(
        "📑 <b>Шаг 3: Рубрика</b>\n\n"
        "Выберите рубрику:",
        reply_markup=get_subcategories_keyboard(category)
    )
    
    data = await state.get_data()
    history = data.get('history_messages', [])
    history.append(msg.message_id)
    await state.update_data(history_messages=history)

@router.callback_query(AdCreation.subcategory, F.data.startswith("subcategory_"))
async def process_subcategory(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора рубрики"""
    subcategory = callback.data.replace("subcategory_", "")
    await state.update_data(subcategory=subcategory)
    
    # Прячем кнопки
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except:
        pass
    
    # Показываем выбор с галочкой
    data = await state.get_data()
    category = data.get('category')
    subcategory_name = SUBCATEGORIES.get(category, {}).get(subcategory, subcategory)
    msg = await callback.message.answer(
        f"✅ <b>Рубрика:</b> {subcategory_name}"
    )
    
    history = data.get('history_messages', [])
    history.append(msg.message_id)
    await state.update_data(history_messages=history)
    
    await ask_deal_type(callback.message, state)
    await callback.answer()

# ========== ТИП СДЕЛКИ ==========

async def ask_deal_type(message: Message, state: FSMContext):
    """Запрос типа сделки"""
    await state.set_state(AdCreation.deal_type)
    
    from bot.keyboards.inline import get_deal_types_keyboard
    msg = await message.answer(
        "💼 <b>Шаг 4: Тип сделки</b>\n\n"
        "Что вы хотите сделать?",
        reply_markup=get_deal_types_keyboard()
    )
    
    data = await state.get_data()
    history = data.get('history_messages', [])
    history.append(msg.message_id)
    await state.update_data(history_messages=history)

@router.callback_query(AdCreation.deal_type, F.data.startswith("deal_"))
async def process_deal_type(callback: CallbackQuery, state: FSMContext):
    """Обработка типа сделки"""
    deal_type = callback.data.replace("deal_", "")
    await state.update_data(deal_type=deal_type)
    
    # Прячем кнопки
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except:
        pass
    
    # Показываем выбор с галочкой
    deal_type_name = DEAL_TYPES.get(deal_type, deal_type)
    msg = await callback.message.answer(
        f"✅ <b>Тип сделки:</b> {deal_type_name}"
    )
    
    data = await state.get_data()
    history = data.get('history_messages', [])
    history.append(msg.message_id)
    await state.update_data(history_messages=history)
    
    await ask_title(callback.message, state)
    await callback.answer()

# ========== ЗАГОЛОВОК ==========

async def ask_title(message: Message, state: FSMContext):
    """Запрос заголовка"""
    await state.set_state(AdCreation.title)
    
    msg = await message.answer(
        "📝 <b>Шаг 5: Заголовок</b>\n\n"
        "Введите краткий заголовок объявления (до 100 символов):"
    )
    
    data = await state.get_data()
    history = data.get('history_messages', [])
    history.append(msg.message_id)
    await state.update_data(history_messages=history)

@router.message(AdCreation.title)
async def process_title(message: Message, state: FSMContext):
    """Обработка заголовка"""
    title = message.text.strip()
    
    if len(title) > 100:
        await message.answer("❌ Заголовок слишком длинный. Максимум 100 символов.")
        return
    
    await state.update_data(title=title)
    
    # Показываем выбор с галочкой
    msg = await message.answer(
        f"✅ <b>Заголовок:</b> {title}"
    )
    
    data = await state.get_data()
    history = data.get('history_messages', [])
    history.append(message.message_id)  # Сообщение пользователя
    history.append(msg.message_id)  # Подтверждение
    await state.update_data(history_messages=history)
    
    await ask_description(message, state)

# ========== ОПИСАНИЕ ==========

async def ask_description(message: Message, state: FSMContext):
    """Запрос описания"""
    await state.set_state(AdCreation.description)
    
    msg = await message.answer(
        "📄 <b>Шаг 6: Описание</b>\n\n"
        "Опишите товар подробно (до 3000 символов):"
    )
    
    data = await state.get_data()
    history = data.get('history_messages', [])
    history.append(msg.message_id)
    await state.update_data(history_messages=history)

@router.message(AdCreation.description)
async def process_description(message: Message, state: FSMContext):
    """Обработка описания"""
    description = message.text.strip()
    
    if len(description) > 3000:
        await message.answer("❌ Описание слишком длинное. Максимум 3000 символов.")
        return
    
    await state.update_data(description=description)
    
    # Показываем выбор с галочкой (кратко)
    desc_preview = description[:100] + "..." if len(description) > 100 else description
    msg = await message.answer(
        f"✅ <b>Описание:</b> {desc_preview}"
    )
    
    data = await state.get_data()
    history = data.get('history_messages', [])
    history.append(message.message_id)
    history.append(msg.message_id)
    await state.update_data(history_messages=history)
    
    await ask_condition(message, state)

# ========== СОСТОЯНИЕ ==========

async def ask_condition(message: Message, state: FSMContext):
    """Запрос состояния товара"""
    await state.set_state(AdCreation.condition)
    
    from bot.keyboards.inline import get_condition_keyboard
    msg = await message.answer(
        "🔧 <b>Шаг 7: Состояние</b>\n\n"
        "Укажите состояние товара:",
        reply_markup=get_condition_keyboard()
    )
    
    data = await state.get_data()
    history = data.get('history_messages', [])
    history.append(msg.message_id)
    await state.update_data(history_messages=history)

@router.callback_query(AdCreation.condition, F.data.startswith("condition_"))
async def process_condition(callback: CallbackQuery, state: FSMContext):
    """Обработка состояния"""
    condition = callback.data.replace("condition_", "")
    await state.update_data(condition=condition)
    
    # Прячем кнопки
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except:
        pass
    
    # Показываем выбор с галочкой
    condition_name = CONDITION_TYPES.get(condition, condition)
    msg = await callback.message.answer(
        f"✅ <b>Состояние:</b> {condition_name}"
    )
    
    data = await state.get_data()
    history = data.get('history_messages', [])
    history.append(msg.message_id)
    await state.update_data(history_messages=history)
    
    await ask_photos(callback.message, state)
    await callback.answer()

# ========== ФОТОГРАФИИ (НОВАЯ ЛОГИКА) ==========

async def ask_photos(message: Message, state: FSMContext):
    """Запрос фотографий"""
    await state.set_state(AdCreation.photos)
    await state.update_data(photos=[])
    
    from bot.keyboards.inline import get_skip_and_done_keyboard
    msg = await message.answer(
        "📸 <b>Шаг 8: Фотографии</b>\n\n"
        "Отправьте фото товара (до 10 штук)\n\n"
        "💡 Можете отправить сразу несколько или по одному\n\n"
        "Когда закончите, нажмите 'Далее' или 'Пропустить'",
        reply_markup=get_skip_and_done_keyboard()
    )
    
    data = await state.get_data()
    history = data.get('history_messages', [])
    history.append(msg.message_id)
    await state.update_data(history_messages=history)

@router.callback_query(AdCreation.photos, F.data == "skip_photos")
async def skip_photos(callback: CallbackQuery, state: FSMContext):
    """Пропустить фотографии"""
    # Прячем кнопки
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
    # Прячем кнопки
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except:
        pass
    
    data = await state.get_data()
    photos = data.get('photos', [])
    
    msg = await callback.message.answer(
        f"✅ <b>Загружено фото:</b> {len(photos)} шт."
    )
    
    history = data.get('history_messages', [])
    history.append(msg.message_id)
    await state.update_data(history_messages=history)
    
    await ask_video(callback.message, state)
    await callback.answer()

@router.message(AdCreation.photos, F.photo)
async def process_photo(message: Message, state: FSMContext):
    """
    Обработка фото - НОВАЯ ЛОГИКА:
    - Поддержка медиагрупп (сразу много фото)
    - Сообщение после каждой загрузки
    - Кнопка Далее/Отмена обновляется
    """
    import asyncio
    
    data = await state.get_data()
    photos = data.get("photos", [])
    
    new_photo_id = message.photo[-1].file_id
    
    # Проверяем дубликат и лимит
    if new_photo_id not in photos:
        if len(photos) >= 10:
            await message.answer("⚠️ Максимум 10 фото.")
            return
            
        photos.append(new_photo_id)
        await state.update_data(photos=photos)
        
        # Добавляем в историю
        history = data.get('history_messages', [])
        history.append(message.message_id)
        await state.update_data(history_messages=history)
        
        # Задержка для обработки медиагруппы
        await asyncio.sleep(0.3)
        
        # Обновляем данные
        data = await state.get_data()
        photos = data.get("photos", [])
        
        # Удаляем предыдущее сообщение о прогрессе (если есть)
        last_progress_msg = data.get('last_progress_message_id')
        if last_progress_msg:
            try:
                await message.bot.delete_message(message.chat.id, last_progress_msg)
            except:
                pass
        
        # Показываем новое сообщение о прогрессе
        from bot.keyboards.inline import get_photo_done_only_keyboard
        
        if len(photos) >= 10:
            msg = await message.answer(
                f"✅ <b>Фото загружены ({len(photos)}/10)</b>\n\n"
                f"Достигнут максимум. Нажмите 'Далее'",
                reply_markup=get_photo_done_only_keyboard()
            )
        else:
            msg = await message.answer(
                f"✅ <b>Фото загружены ({len(photos)}/10)</b>\n\n"
                f"Добавьте ещё фотографии или нажмите 'Далее'",
                reply_markup=get_photo_done_only_keyboard()
            )
        
        # Сохраняем ID для удаления при следующей загрузке
        await state.update_data(last_progress_message_id=msg.message_id)
        
        # Добавляем в историю
        history = data.get('history_messages', [])
        history.append(msg.message_id)
        await state.update_data(history_messages=history)


# ========== ВИДЕО ==========

async def ask_video(message: Message, state: FSMContext):
    """Запрос видео"""
    await state.set_state(AdCreation.video)
    
    from bot.keyboards.inline import get_skip_keyboard
    msg = await message.answer(
        "🎥 <b>Шаг 9: Видео</b>\n\n"
        "Отправьте видео (не более 100 МБ)\n"
        "или нажмите 'Пропустить':",
        reply_markup=get_skip_keyboard()
    )
    
    data = await state.get_data()
    history = data.get('history_messages', [])
    history.append(msg.message_id)
    await state.update_data(history_messages=history)

@router.callback_query(AdCreation.video, F.data == "skip_video")
async def skip_video(callback: CallbackQuery, state: FSMContext):
    """Пропустить видео"""
    # Прячем кнопки
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
    """Обработка видео"""
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
    """Запрос цены"""
    await state.set_state(AdCreation.price)
    
    from bot.keyboards.inline import get_price_keyboard
    msg = await message.answer(
        "💰 <b>Шаг 10: Цена</b>\n\n"
        "Укажите цену в рублях (только цифры)\n"
        "или нажмите 'Договорная':",
        reply_markup=get_price_keyboard()
    )
    
    data = await state.get_data()
    history = data.get('history_messages', [])
    history.append(msg.message_id)
    await state.update_data(history_messages=history)

@router.callback_query(AdCreation.price, F.data == "negotiable")
async def price_negotiable(callback: CallbackQuery, state: FSMContext):
    """Договорная цена"""
    await state.update_data(price="Договорная")
    
    # Прячем кнопки
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
    """Обработка цены"""
    price_text = message.text.strip()
    
    logger.info(f"Обработка цены: {price_text}")
    
    # Проверка что только цифры
    if not price_text.isdigit():
        await message.answer("❌ Введите только цифры (например: 5000)")
        return
    
    price = int(price_text)
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
    
    logger.info(f"Цена сохранена: {price} ₽, переход к проверке доставки")
    await check_delivery_needed(message, state)

# ========== ДОСТАВКА ==========

async def check_delivery_needed(message: Message, state: FSMContext):
    """Проверка нужно ли указывать доставку"""
    data = await state.get_data()
    category = data.get('category')
    
    logger.info(f"Проверка доставки для категории: {category}")
    
    # Доставка нужна только для определённых категорий
    if category in CATEGORIES_WITH_DELIVERY:
        logger.info(f"Категория {category} требует доставку")
        await state.set_state(AdCreation.delivery)
        
        from bot.keyboards.inline import get_delivery_keyboard
        msg = await message.answer(
            "🚚 <b>Шаг 11: Доставка</b>\n\n"
            "Выберите способ доставки:",
            reply_markup=get_delivery_keyboard()
        )
        
        history = data.get('history_messages', [])
        history.append(msg.message_id)
        await state.update_data(history_messages=history)
    else:
        logger.info(f"Категория {category} не требует доставку, показываем превью")
        # Сразу показываем превью
        await show_preview(message, state)

@router.callback_query(AdCreation.delivery, F.data.startswith("delivery_"))
async def process_delivery(callback: CallbackQuery, state: FSMContext):
    """Обработка доставки"""
    delivery = callback.data.replace("delivery_", "")
    await state.update_data(delivery=delivery)
    
    # Прячем кнопки
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except:
        pass
    
    # Показываем выбор с галочкой
    delivery_name = DELIVERY_TYPES.get(delivery, delivery)
    msg = await callback.message.answer(
        f"✅ <b>Доставка:</b> {delivery_name}"
    )
    
    data = await state.get_data()
    history = data.get('history_messages', [])
    history.append(msg.message_id)
    await state.update_data(history_messages=history)
    
    await show_preview(callback.message, state)
    
    # ВАЖНО: Отвечаем быстро, чтобы избежать timeout
    try:
        await callback.answer()
    except:
        pass

# ========== ПРЕВЬЮ ==========

async def show_preview(message: Message, state: FSMContext):
    """Показать превью объявления"""
    logger.info("Показ превью объявления")
    
    data = await state.get_data()
    await state.set_state(AdCreation.confirm)
    
    from shared.regions_config import REGIONS
    from bot.utils.formatters import format_ad_preview
    from aiogram.types import InputMediaPhoto, InputMediaVideo
    
    # Формируем текст превью
    logger.info(f"Формирование превью для данных: категория={data.get('category')}, фото={len(data.get('photos', []))}")
    preview_text = format_ad_preview(data)
    
    # Проверка длины caption (Telegram лимит 1024 символа)
    if len(preview_text) > 1024:
        logger.warning(f"Caption слишком длинный ({len(preview_text)} символов), обрезаем до 1024")
        preview_text = preview_text[:1020] + "..."
    
    from bot.keyboards.inline import get_confirm_with_edit_keyboard
    
    # Отправляем превью с фото/видео если есть
    photos = data.get('photos', [])
    video = data.get('video')
    
    try:
        if video and photos:
            # Видео + фото = медиагруппа
            logger.info(f"Отправка превью: видео + {len(photos)} фото (медиагруппа)")
            media_group = [InputMediaVideo(media=video, caption=preview_text)]
            for photo in photos[:9]:  # До 9 фото + 1 видео = 10
                media_group.append(InputMediaPhoto(media=photo))
            
            await message.answer_media_group(media=media_group)
            # Кнопки отдельно
            msg = await message.answer(
                "👆 <b>Ваше объявление</b>",
                reply_markup=get_confirm_with_edit_keyboard()
            )
        elif video:
            # Только видео
            logger.info("Отправка превью: только видео")
            msg = await message.answer_video(
                video=video,
                caption=preview_text,
                reply_markup=get_confirm_with_edit_keyboard()
            )
        elif photos:
            # Только фото
            if len(photos) == 1:
                # Одно фото - с caption
                logger.info("Отправка превью: 1 фото с caption")
                msg = await message.answer_photo(
                    photo=photos[0],
                    caption=preview_text,
                    reply_markup=get_confirm_with_edit_keyboard()
                )
            else:
                # Несколько фото - медиагруппа
                logger.info(f"Отправка превью: {len(photos)} фото (медиагруппа)")
                media_group = [InputMediaPhoto(media=photos[0], caption=preview_text)]
                for photo in photos[1:10]:
                    media_group.append(InputMediaPhoto(media=photo))
                
                await message.answer_media_group(media=media_group)
                # Кнопки отдельно
                msg = await message.answer(
                    "👆 <b>Ваше объявление</b>",
                    reply_markup=get_confirm_with_edit_keyboard()
                )
        else:
            # Без медиа
            logger.info("Отправка превью: без медиа")
            msg = await message.answer(
                preview_text,
                reply_markup=get_confirm_with_edit_keyboard()
            )
        
        history = data.get('history_messages', [])
        history.append(msg.message_id)
        await state.update_data(history_messages=history)
        
        logger.info("Превью успешно отправлено")
        
    except Exception as e:
        logger.error(f"Ошибка при отправке превью: {e}", exc_info=True)
        # Упрощённое превью
        try:
            msg = await message.answer(
                f"📢 <b>Превью объявления</b>\n\n{preview_text[:500]}...",
                reply_markup=get_confirm_with_edit_keyboard()
            )
            history = data.get('history_messages', [])
            history.append(msg.message_id)
            await state.update_data(history_messages=history)
        except Exception as final_error:
            logger.error(f"Даже упрощённое превью не отправилось: {final_error}")


# ========== ПУБЛИКАЦИЯ ==========

@router.callback_query(AdCreation.confirm, F.data == "confirm_publish")
async def confirm_ad(callback: CallbackQuery, state: FSMContext):
    """Подтверждение и создание объявления"""
    data = await state.get_data()
    
    # Прячем кнопки
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except:
        pass
    
    # Быстро отвечаем на callback чтобы избежать timeout
    try:
        await callback.answer("⏳ Создаём объявление...")
    except:
        pass
    
    try:
        # Получаем информацию о боте
        bot_info = await callback.message.bot.get_me()
        
        # Создаем объявление
        async with get_db_session() as session:
            # Преобразуем цену
            price_str = data.get('price', 'Договорная')
            if price_str == 'Договорная':
                price_value = None
            else:
                price_value = float(price_str.replace(' ₽', '').replace(' ', ''))
            
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
                # Дополнительные поля в JSONB
                premium_features={
                    'subcategory': data.get('subcategory'),
                    'condition': data.get('condition'),
                    'delivery': data.get('delivery'),
                    'price_text': data.get('price')
                }
            )
            session.add(ad)
            await session.commit()
            
        success_text = (
            f"✅ <b>Объявление успешно создано!</b>\n\n"
            f"ID: <code>{ad.id}</code>\n\n"
            f"Ваше объявление опубликовано и доступно для просмотра."
        )
        
        # Отправляем успешное сообщение
        await callback.message.answer(success_text)
        
        # Публикуем в канал
        await publish_to_channel(callback.message.bot, bot_info, ad, data)
        
    except Exception as e:
        logger.error(f"Ошибка при создании объявления: {e}", exc_info=True)
        
        error_text = "❌ Произошла ошибка при создании объявления. Попробуйте позже."
        await callback.message.answer(error_text)
    
    await state.clear()

@router.callback_query(AdCreation.confirm, F.data == "cancel_ad")
async def cancel_ad(callback: CallbackQuery, state: FSMContext):
    """Отмена создания"""
    # Прячем кнопки
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except:
        pass
    
    await state.clear()
    await callback.message.answer("❌ Создание объявления отменено.")
    await callback.answer()

@router.callback_query(AdCreation.confirm, F.data == "edit_ad")
async def edit_ad_preview(callback: CallbackQuery, state: FSMContext):
    """Редактирование объявления перед публикацией"""
    # Прячем кнопки
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except:
        pass
    
    await callback.message.answer(
        "✏️ <b>Редактирование пока в разработке</b>\n\n"
        "Пожалуйста, создайте объявление заново."
    )
    await callback.answer()

# ========== ПУБЛИКАЦИЯ В КАНАЛ ==========

async def publish_to_channel(bot, bot_info, ad, data):
    """
    Публикация в канал
    
    НОВОЕ: Рубрики как хэштеги!
    """
    from shared.regions_config import CHANNELS_CONFIG
    from aiogram.types import InputMediaPhoto, InputMediaVideo
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    
    region = data.get('region', '')
    category = data.get('category', '')
    subcategory = data.get('subcategory', '')
    
    channel_config = CHANNELS_CONFIG.get(region, {})
    
    # Находим каналы
    category_channel = channel_config.get('categories', {}).get(category)
    main_channel = channel_config.get('main')
    
    # Получаем информацию о пользователе
    user_id = ad.user_id
    
    # Формируем текст объявления
    subcategory_name = SUBCATEGORIES.get(category, {}).get(subcategory, subcategory)
    deal_type_name = DEAL_TYPES.get(data.get('deal_type'), '')
    condition = data.get('condition')
    condition_text = f" / {CONDITION_TYPES.get(condition, '')}" if condition else ""
    
    title = data.get('title', '')
    title_text = f"<b>{title}</b>\n\n" if title else ""
    
    description = data.get('description', '')
    description_text = f"{description}\n\n" if description else ""
    
    delivery = data.get('delivery')
    delivery_text = f" | {DELIVERY_TYPES.get(delivery, '')}" if delivery else ""
    
    # ВАЖНО: Рубрика как ХЭШТЕГ!
    hashtag = f"#{subcategory.replace('_', '').replace('-', '')}"
    
    text = f"""{hashtag}

{deal_type_name}{condition_text}

{title_text}{description_text}💰 {data.get('price', 'Не указана')}{delivery_text}"""
    
    # Создаем клавиатуру
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="📢 Разместить объявление", url=f"https://t.me/{bot_info.username}")
    keyboard.button(text="😎 Написать продавцу", url=f"tg://user?id={user_id}")
    keyboard.adjust(1)
    reply_markup = keyboard.as_markup()
    
    photos = data.get('photos', [])
    video = data.get('video')
    
    channels_to_publish = []
    if category_channel:
        channels_to_publish.append(('категорию', category_channel))
    if main_channel:
        channels_to_publish.append(('главный канал', main_channel))
    
    # Публикуем
    for channel_name, channel in channels_to_publish:
        try:
            logger.info(f"Публикация в {channel_name}: {channel}")
            
            if video and photos:
                # Видео + фото
                media_group = [InputMediaVideo(media=video, caption=text)]
                for photo in photos[:9]:
                    media_group.append(InputMediaPhoto(media=photo))
                
                messages = await bot.send_media_group(chat_id=channel, media=media_group)
                if messages:
                    await bot.send_message(
                        chat_id=channel,
                        text="👆 Подробнее",
                        reply_markup=reply_markup
                    )
            elif video:
                # Только видео
                await bot.send_video(
                    chat_id=channel,
                    video=video,
                    caption=text,
                    reply_markup=reply_markup
                )
            elif photos:
                # Только фото
                if len(photos) == 1:
                    await bot.send_photo(
                        chat_id=channel,
                        photo=photos[0],
                        caption=text,
                        reply_markup=reply_markup
                    )
                else:
                    # Медиагруппа
                    media_group = [InputMediaPhoto(media=photos[0], caption=text)]
                    for photo in photos[1:10]:
                        media_group.append(InputMediaPhoto(media=photo))
                    
                    messages = await bot.send_media_group(chat_id=channel, media=media_group)
                    if messages:
                        await bot.send_message(
                            chat_id=channel,
                            text="👆 Подробнее",
                            reply_markup=reply_markup
                        )
            else:
                # Только текст
                await bot.send_message(
                    chat_id=channel,
                    text=text,
                    reply_markup=reply_markup
                )
            
            logger.info(f"Успешно опубликовано в {channel_name}")
            
        except Exception as e:
            logger.error(f"Ошибка публикации в {channel_name}: {e}", exc_info=True)

# ========== ОБРАБОТЧИК ОТМЕНЫ ==========

@router.callback_query(F.data == "cancel_creation")
async def cancel_creation(callback: CallbackQuery, state: FSMContext):
    """Отмена создания объявления на любом этапе"""
    await state.clear()
    
    # Прячем кнопки
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except:
        pass
    
    await callback.message.answer("❌ Создание объявления отменено.")
    await callback.answer()
