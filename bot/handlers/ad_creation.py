# bot/handlers/ad_creation.py
"""Обработчики создания объявлений - ИСПРАВЛЕННАЯ ВЕРСИЯ"""

import logging
import asyncio
from datetime import datetime
import uuid
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InputMediaPhoto, InputMediaVideo
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramNetworkError

from bot.database.connection import get_db_session
from bot.database.models import Ad, AdStatus
from shared.regions_config import (
    REGIONS, CITIES, CATEGORIES, SUBCATEGORIES, DEAL_TYPES,
    CONDITION_TYPES, DELIVERY_TYPES, CATEGORIES_WITH_DELIVERY,
    DEAL_TYPES_WITH_CONDITION, CHANNELS_CONFIG,
    get_city_hashtag, get_subcategory_hashtag
)

logger = logging.getLogger(__name__)
router = Router(name='ad_creation')


class AdCreation(StatesGroup):
    region = State()
    city = State()
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


# ========== НАЧАЛО ==========
@router.callback_query(F.data == "new_ad")
async def start_creation_callback(callback: CallbackQuery, state: FSMContext):
    """Начало создания объявления через callback"""
    logger.info(f"[AD_CREATION] start_creation_callback, user={callback.from_user.id}")
    await callback.answer()
    await state.clear()
    await ask_region(callback.message, state)


@router.message(F.text.in_(["Создать объявление", "📝 Подать объявление", "/create"]))
async def start_creation(message: Message, state: FSMContext):
    """Начало создания объявления через сообщение"""
    logger.info(f"[AD_CREATION] start_creation, user={message.from_user.id}")
    await state.clear()
    await ask_region(message, state)


# ========== РЕГИОН ==========
async def ask_region(message: Message, state: FSMContext):
    """Запрос региона"""
    logger.info(f"[AD_CREATION] ask_region")
    await state.set_state(AdCreation.region)
    
    from bot.keyboards.inline import get_regions_keyboard
    await message.answer(
        "📍 <b>Шаг 1: Регион</b>\n\nВыберите регион:", 
        reply_markup=get_regions_keyboard()
    )


@router.callback_query(F.data.startswith("region_"))
async def process_region(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора региона"""
    logger.info(f"[AD_CREATION] process_region: {callback.data}, user={callback.from_user.id}")
    
    region = callback.data.replace("region_", "")
    await state.update_data(region=region)
    
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except:
        pass
    
    region_name = REGIONS.get(region, region)
    await callback.message.answer(f"✅ <b>Регион:</b> {region_name}")
    
    await ask_city(callback.message, state, region)
    await callback.answer()


# ========== ГОРОД ==========
async def ask_city(message: Message, state: FSMContext, region: str):
    """Запрос города"""
    logger.info(f"[AD_CREATION] ask_city, region={region}")
    await state.set_state(AdCreation.city)
    
    from bot.keyboards.inline import get_cities_keyboard
    await message.answer(
        "🏙 <b>Шаг 2: Город</b>\n\nВыберите город:", 
        reply_markup=get_cities_keyboard(region)
    )


@router.callback_query(F.data.startswith("city_"))
async def process_city(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора города"""
    logger.info(f"[AD_CREATION] process_city: {callback.data}")
    
    city = callback.data.replace("city_", "")
    data = await state.get_data()
    region = data.get('region', '')
    
    await state.update_data(city=city)
    
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except:
        pass
    
    city_name = CITIES.get(region, {}).get(city, city)
    await callback.message.answer(f"✅ <b>Город:</b> {city_name}")
    
    await ask_category(callback.message, state)
    await callback.answer()


@router.callback_query(F.data == "back_to_region")
async def back_to_region(callback: CallbackQuery, state: FSMContext):
    """Назад к выбору региона"""
    logger.info(f"[AD_CREATION] back_to_region")
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except:
        pass
    await ask_region(callback.message, state)
    await callback.answer()


# ========== КАТЕГОРИЯ ==========
async def ask_category(message: Message, state: FSMContext):
    """Запрос категории"""
    logger.info(f"[AD_CREATION] ask_category")
    await state.set_state(AdCreation.category)
    
    from bot.keyboards.inline import get_categories_keyboard
    await message.answer(
        "📂 <b>Шаг 3: Категория</b>\n\nВыберите категорию:", 
        reply_markup=get_categories_keyboard()
    )


@router.callback_query(F.data.startswith("category_"))
async def process_category(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора категории"""
    logger.info(f"[AD_CREATION] process_category: {callback.data}")
    
    category = callback.data.replace("category_", "")
    await state.update_data(category=category)
    
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except:
        pass
    
    category_name = CATEGORIES.get(category, category)
    await callback.message.answer(f"✅ <b>Категория:</b> {category_name}")
    
    await ask_subcategory(callback.message, state, category)
    await callback.answer()


@router.callback_query(F.data == "back_to_city")
async def back_to_city(callback: CallbackQuery, state: FSMContext):
    """Назад к выбору города"""
    logger.info(f"[AD_CREATION] back_to_city")
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except:
        pass
    data = await state.get_data()
    region = data.get('region', '')
    await ask_city(callback.message, state, region)
    await callback.answer()


# ========== РУБРИКА ==========
async def ask_subcategory(message: Message, state: FSMContext, category: str):
    """Запрос рубрики"""
    logger.info(f"[AD_CREATION] ask_subcategory, category={category}")
    await state.set_state(AdCreation.subcategory)
    
    from bot.keyboards.inline import get_subcategories_keyboard
    await message.answer(
        "📑 <b>Шаг 4: Рубрика</b>\n\nВыберите рубрику:", 
        reply_markup=get_subcategories_keyboard(category)
    )


@router.callback_query(F.data.startswith("subcategory_"))
async def process_subcategory(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора рубрики"""
    logger.info(f"[AD_CREATION] process_subcategory: {callback.data}")
    
    subcategory = callback.data.replace("subcategory_", "")
    data = await state.get_data()
    category = data.get('category', '')
    
    await state.update_data(subcategory=subcategory)
    
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except:
        pass
    
    subcategory_name = SUBCATEGORIES.get(category, {}).get(subcategory, subcategory)
    await callback.message.answer(f"✅ <b>Рубрика:</b> {subcategory_name}")
    
    await ask_deal_type(callback.message, state)
    await callback.answer()


@router.callback_query(F.data == "back_to_category")
async def back_to_category(callback: CallbackQuery, state: FSMContext):
    """Назад к выбору категории"""
    logger.info(f"[AD_CREATION] back_to_category")
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except:
        pass
    await ask_category(callback.message, state)
    await callback.answer()


# ========== ТИП СДЕЛКИ ==========
async def ask_deal_type(message: Message, state: FSMContext):
    """Запрос типа сделки"""
    logger.info(f"[AD_CREATION] ask_deal_type")
    await state.set_state(AdCreation.deal_type)
    
    from bot.keyboards.inline import get_deal_types_keyboard
    await message.answer(
        "💼 <b>Шаг 5: Тип сделки</b>\n\nЧто вы хотите сделать?", 
        reply_markup=get_deal_types_keyboard()
    )


@router.callback_query(F.data.startswith("deal_"))
async def process_deal_type(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора типа сделки"""
    logger.info(f"[AD_CREATION] process_deal_type: {callback.data}")
    
    deal_type = callback.data.replace("deal_", "")
    await state.update_data(deal_type=deal_type)
    
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except:
        pass
    
    deal_type_name = DEAL_TYPES.get(deal_type, deal_type)
    await callback.message.answer(f"✅ <b>Тип:</b> {deal_type_name}")
    
    await ask_title(callback.message, state)
    await callback.answer()


@router.callback_query(F.data == "back_to_subcategory")
async def back_to_subcategory(callback: CallbackQuery, state: FSMContext):
    """Назад к выбору рубрики"""
    logger.info(f"[AD_CREATION] back_to_subcategory")
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except:
        pass
    data = await state.get_data()
    category = data.get('category', '')
    await ask_subcategory(callback.message, state, category)
    await callback.answer()


# ========== ЗАГОЛОВОК ==========
async def ask_title(message: Message, state: FSMContext):
    """Запрос заголовка"""
    logger.info(f"[AD_CREATION] ask_title")
    await state.set_state(AdCreation.title)
    await message.answer("📝 <b>Шаг 6: Заголовок</b>\n\nВведите заголовок (до 100 символов):")


@router.message(AdCreation.title)
async def process_title(message: Message, state: FSMContext):
    """Обработка заголовка"""
    logger.info(f"[AD_CREATION] process_title")
    
    if not message.text:
        await message.answer("❌ Введите текст заголовка")
        return
    
    title = message.text.strip()[:100]
    await state.update_data(title=title)
    await message.answer(f"✅ <b>Заголовок:</b> {title}")
    
    await ask_description(message, state)


# ========== ОПИСАНИЕ ==========
async def ask_description(message: Message, state: FSMContext):
    """Запрос описания"""
    logger.info(f"[AD_CREATION] ask_description")
    await state.set_state(AdCreation.description)
    await message.answer("📄 <b>Шаг 7: Описание</b>\n\nВведите описание (до 1000 символов):")


@router.message(AdCreation.description)
async def process_description(message: Message, state: FSMContext):
    """Обработка описания"""
    logger.info(f"[AD_CREATION] process_description")
    
    if not message.text:
        await message.answer("❌ Введите текст описания")
        return
    
    description = message.text.strip()[:1000]
    await state.update_data(description=description)
    
    display_desc = description[:50] + "..." if len(description) > 50 else description
    await message.answer(f"✅ <b>Описание:</b> {display_desc}")
    
    data = await state.get_data()
    deal_type = data.get('deal_type')
    
    if deal_type in DEAL_TYPES_WITH_CONDITION:
        await ask_condition(message, state)
    else:
        await ask_photos(message, state)


# ========== СОСТОЯНИЕ ==========
async def ask_condition(message: Message, state: FSMContext):
    """Запрос состояния товара"""
    logger.info(f"[AD_CREATION] ask_condition")
    await state.set_state(AdCreation.condition)
    
    from bot.keyboards.inline import get_condition_keyboard
    await message.answer(
        "📦 <b>Шаг 8: Состояние</b>\n\nВыберите состояние:", 
        reply_markup=get_condition_keyboard()
    )


@router.callback_query(F.data.startswith("condition_"))
async def process_condition(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора состояния"""
    logger.info(f"[AD_CREATION] process_condition: {callback.data}")
    
    condition = callback.data.replace("condition_", "")
    await state.update_data(condition=condition)
    
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except:
        pass
    
    condition_name = CONDITION_TYPES.get(condition, condition)
    await callback.message.answer(f"✅ <b>Состояние:</b> {condition_name}")
    
    await ask_photos(callback.message, state)
    await callback.answer()


# ========== ФОТО ==========
from typing import Dict
media_group_data: Dict[str, dict] = {}


async def ask_photos(message: Message, state: FSMContext):
    """Запрос фото"""
    logger.info(f"[AD_CREATION] ask_photos")
    await state.set_state(AdCreation.photos)
    await state.update_data(
        photos=[], 
        photo_progress_msg_id=None,
        processed_media_groups=[],
        photo_prompt_msg_id=None
    )
    
    from bot.keyboards.inline import get_photo_skip_keyboard
    msg = await message.answer(
        "📸 <b>Шаг 9: Фото</b>\n\n"
        "Отправьте фото товара (до 10 шт).\n"
        "Можно отправить сразу несколько или по одному.\n\n"
        "Когда закончите — нажмите <b>Далее</b>.",
        reply_markup=get_photo_skip_keyboard()
    )
    await state.update_data(photo_prompt_msg_id=msg.message_id)


@router.message(AdCreation.photos, F.photo)
async def process_photo(message: Message, state: FSMContext):
    """Обработка фото"""
    global media_group_data
    
    data = await state.get_data()
    photos = data.get("photos", [])
    processed_groups = data.get("processed_media_groups", [])
    
    if len(photos) >= 10:
        return
    
    photo_id = message.photo[-1].file_id
    media_group_id = message.media_group_id
    
    if media_group_id:
        if media_group_id in processed_groups:
            return
        
        if media_group_id not in media_group_data:
            media_group_data[media_group_id] = {"photos": []}
        
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
    
    added_count = 0
    for photo_id in group_photos:
        if len(photos) >= 10:
            break
        if photo_id not in photos:
            photos.append(photo_id)
            added_count += 1
    
    processed_groups.append(media_group_id)
    await state.update_data(photos=photos, processed_media_groups=processed_groups)
    
    del media_group_data[media_group_id]
    
    if added_count > 0:
        await show_photo_progress(message, state, len(photos))


async def show_photo_progress(message: Message, state: FSMContext, photo_count: int):
    """Показать прогресс загрузки фото"""
    from bot.keyboards.inline import get_photo_done_keyboard
    
    data = await state.get_data()
    
    old_msg_id = data.get('photo_progress_msg_id')
    if old_msg_id:
        try:
            await message.bot.delete_message(message.chat.id, old_msg_id)
        except:
            pass
    
    prompt_msg_id = data.get('photo_prompt_msg_id')
    if prompt_msg_id:
        try:
            await message.bot.delete_message(message.chat.id, prompt_msg_id)
        except:
            pass
        await state.update_data(photo_prompt_msg_id=None)
    
    text = f"✅ Загружено {photo_count}/10 фото.\n\nДобавьте ещё или нажмите <b>Далее</b>."
    msg = await message.answer(text, reply_markup=get_photo_done_keyboard())
    await state.update_data(photo_progress_msg_id=msg.message_id)


@router.callback_query(F.data == "photos_skip")
async def skip_photos(callback: CallbackQuery, state: FSMContext):
    """Пропустить фото"""
    logger.info(f"[AD_CREATION] skip_photos")
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except:
        pass
    await ask_video(callback.message, state)
    await callback.answer()


@router.callback_query(F.data == "photos_done")
async def photos_done(callback: CallbackQuery, state: FSMContext):
    """Фото загружены"""
    logger.info(f"[AD_CREATION] photos_done")
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except:
        pass
    
    data = await state.get_data()
    photos_count = len(data.get('photos', []))
    await state.update_data(photo_progress_msg_id=None)
    await callback.message.answer(f"✅ <b>Фото:</b> {photos_count} шт.")
    
    await ask_video(callback.message, state)
    await callback.answer()


# ========== ВИДЕО ==========
async def ask_video(message: Message, state: FSMContext):
    """Запрос видео"""
    logger.info(f"[AD_CREATION] ask_video")
    await state.set_state(AdCreation.video)
    
    from bot.keyboards.inline import get_video_keyboard
    await message.answer(
        "🎬 <b>Шаг 10: Видео</b>\n\n"
        "Отправьте видео (до 50 МБ) или нажмите <b>Пропустить</b>.",
        reply_markup=get_video_keyboard()
    )


@router.message(AdCreation.video, F.video)
async def process_video(message: Message, state: FSMContext):
    """Обработка видео"""
    logger.info(f"[AD_CREATION] process_video")
    
    video_id = message.video.file_id
    await state.update_data(video=video_id)
    await message.answer("✅ <b>Видео:</b> загружено")
    
    await ask_price(message, state)


@router.callback_query(F.data == "video_skip")
async def skip_video(callback: CallbackQuery, state: FSMContext):
    """Пропустить видео"""
    logger.info(f"[AD_CREATION] skip_video")
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except:
        pass
    await ask_price(callback.message, state)
    await callback.answer()


# ========== ЦЕНА ==========
async def ask_price(message: Message, state: FSMContext):
    """Запрос цены"""
    logger.info(f"[AD_CREATION] ask_price")
    await state.set_state(AdCreation.price)
    
    from bot.keyboards.inline import get_price_keyboard
    await message.answer(
        "💰 <b>Шаг 11: Цена</b>\n\nВведите цену (число):", 
        reply_markup=get_price_keyboard()
    )


@router.message(AdCreation.price)
async def process_price(message: Message, state: FSMContext):
    """Обработка цены"""
    logger.info(f"[AD_CREATION] process_price")
    
    if not message.text:
        await message.answer("❌ Введите число")
        return
    
    price_text = message.text.strip().replace(" ", "").replace(",", ".")
    try:
        price = float(price_text)
        price_display = f"{int(price):,} ₽".replace(",", " ")
    except ValueError:
        await message.answer("❌ Введите число. Например: 15000")
        return
    
    await state.update_data(price=price_display)
    await message.answer(f"✅ <b>Цена:</b> {price_display}")
    
    data = await state.get_data()
    category = data.get('category')
    
    if category in CATEGORIES_WITH_DELIVERY:
        await ask_delivery(message, state)
    else:
        await show_preview(message, state)


@router.callback_query(F.data == "price_negotiable")
async def price_negotiable(callback: CallbackQuery, state: FSMContext):
    """Цена договорная"""
    logger.info(f"[AD_CREATION] price_negotiable")
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except:
        pass
    
    await state.update_data(price="Договорная")
    await callback.message.answer("✅ <b>Цена:</b> Договорная")
    
    data = await state.get_data()
    category = data.get('category')
    
    if category in CATEGORIES_WITH_DELIVERY:
        await ask_delivery(callback.message, state)
    else:
        await show_preview(callback.message, state)
    await callback.answer()


# ========== ДОСТАВКА ==========
async def ask_delivery(message: Message, state: FSMContext):
    """Запрос доставки"""
    logger.info(f"[AD_CREATION] ask_delivery")
    await state.set_state(AdCreation.delivery)
    
    from bot.keyboards.inline import get_delivery_keyboard
    await message.answer(
        "🚚 <b>Шаг 12: Доставка</b>\n\nВыберите доставку:", 
        reply_markup=get_delivery_keyboard()
    )


@router.callback_query(F.data.startswith("delivery_"))
async def process_delivery(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора доставки"""
    logger.info(f"[AD_CREATION] process_delivery: {callback.data}")
    
    delivery = callback.data.replace("delivery_", "")
    await state.update_data(delivery=delivery)
    
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except:
        pass
    
    delivery_name = DELIVERY_TYPES.get(delivery, delivery)
    await callback.message.answer(f"✅ <b>Доставка:</b> {delivery_name}")
    
    await show_preview(callback.message, state)
    await callback.answer()


# ========== ПРЕВЬЮ ==========
async def show_preview(message: Message, state: FSMContext):
    """Показ превью объявления"""
    logger.info("[AD_CREATION] show_preview")
    data = await state.get_data()
    await state.set_state(AdCreation.confirm)
    
    preview_text = format_ad_preview(data)
    
    from bot.keyboards.inline import get_confirm_with_edit_keyboard
    await message.answer(preview_text, reply_markup=get_confirm_with_edit_keyboard())


def format_ad_preview(data: dict) -> str:
    """Форматирование превью"""
    region = data.get('region', '')
    city = data.get('city', '')
    category = data.get('category', '')
    subcategory = data.get('subcategory', '')
    deal_type = data.get('deal_type', '')
    condition = data.get('condition')
    title = data.get('title', '')
    description = data.get('description', '')
    price = data.get('price', 'Не указана')
    delivery = data.get('delivery')
    photos_count = len(data.get('photos', []))
    has_video = bool(data.get('video'))
    
    region_name = REGIONS.get(region, region)
    city_name = CITIES.get(region, {}).get(city, city)
    category_name = CATEGORIES.get(category, category)
    subcategory_name = SUBCATEGORIES.get(category, {}).get(subcategory, subcategory)
    deal_type_name = DEAL_TYPES.get(deal_type, '')
    condition_text = f" / {CONDITION_TYPES.get(condition, '')}" if condition else ""
    delivery_text = f"\n🚚 {DELIVERY_TYPES.get(delivery, '')}" if delivery else ""
    
    city_hashtag = get_city_hashtag(city) if city else ""
    subcategory_hashtag = get_subcategory_hashtag(subcategory) if subcategory else ""
    
    media_info = []
    if photos_count > 0:
        media_info.append(f"📸 {photos_count} фото")
    if has_video:
        media_info.append("🎥 видео")
    media_text = " | ".join(media_info) if media_info else "Без медиа"
    
    return f"""📢 <b>Превью объявления</b>

{city_hashtag} {subcategory_hashtag}

📍 {region_name}, {city_name}
📂 {category_name} → {subcategory_name}
💼 {deal_type_name}{condition_text}

<b>{title}</b>

{description[:300]}{"..." if len(description) > 300 else ""}

💰 {price}{delivery_text}
{media_text}

<b>Всё верно?</b>"""


# ========== ПУБЛИКАЦИЯ ==========
@router.callback_query(F.data == "confirm_publish")
async def confirm_ad(callback: CallbackQuery, state: FSMContext):
    """Подтверждение и публикация объявления"""
    logger.info(f"[AD_CREATION] confirm_ad")
    
    data = await state.get_data()
    
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except:
        pass
    
    try:
        await callback.answer("⏳ Публикуем...")
    except:
        pass
    
    try:
        bot_info = await callback.message.bot.get_me()
        
        # Создаём объявление в БД
        async with get_db_session() as session:
            price_str = data.get('price', 'Договорная')
            price_value = None
            if price_str != 'Договорная':
                try:
                    price_value = float(price_str.replace(' ₽', '').replace(' ', ''))
                except:
                    pass
            
            ad = Ad(
                id=uuid.uuid4(),
                user_id=callback.from_user.id,
                title=data.get('title', ''),
                description=data.get('description', ''),
                price=price_value,
                region=data.get('region'),
                city=data.get('city'),
                category=data.get('category'),
                ad_type=data.get('deal_type'),
                photos=data.get('photos', []),
                video=data.get('video'),
                status=AdStatus.ACTIVE.value,
                created_at=datetime.utcnow(),
                channel_message_ids={},  # Будет заполнено после публикации
                premium_features={
                    'subcategory': data.get('subcategory'),
                    'condition': data.get('condition'),
                    'delivery': data.get('delivery'),
                    'price_text': data.get('price')
                }
            )
            session.add(ad)
            await session.commit()
            await session.refresh(ad)
            
            ad_id = ad.id
        
        # Публикация в каналы и получение message_ids
        channel_message_ids = await publish_to_channel(callback.message.bot, bot_info, ad, data)
        
        # Обновляем объявление с ссылками на каналы
        if channel_message_ids:
            async with get_db_session() as session:
                from sqlalchemy import update
                stmt = update(Ad).where(Ad.id == ad_id).values(channel_message_ids=channel_message_ids)
                await session.execute(stmt)
                await session.commit()
        
        await callback.message.answer(f"✅ <b>Объявление опубликовано!</b>\n\nID: <code>{ad_id}</code>")
        
    except Exception as e:
        logger.error(f"Ошибка создания объявления: {e}", exc_info=True)
        await callback.message.answer("❌ Ошибка создания. Попробуйте позже.")
    
    await state.clear()


@router.callback_query(F.data == "cancel_ad")
async def cancel_ad(callback: CallbackQuery, state: FSMContext):
    """Отмена создания объявления"""
    logger.info(f"[AD_CREATION] cancel_ad")
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except:
        pass
    await state.clear()
    await callback.message.answer("❌ Создание отменено.")
    await callback.answer()


@router.callback_query(F.data == "edit_ad")
async def edit_ad_preview(callback: CallbackQuery, state: FSMContext):
    """Редактирование превью"""
    logger.info(f"[AD_CREATION] edit_ad_preview")
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except:
        pass
    await callback.message.answer("✏️ Редактирование в разработке.\nСоздайте объявление заново.")
    await callback.answer()


async def publish_to_channel(bot, bot_info, ad, data) -> dict:
    """
    Публикация объявления в канал.
    Возвращает словарь {channel_username: message_id} для сохранения в БД.
    """
    logger.info(f"[AD_CREATION] publish_to_channel, ad_id={ad.id}")
    
    region = data.get('region', '')
    city = data.get('city', '')
    category = data.get('category', '')
    subcategory = data.get('subcategory', '')
    
    channel_config = CHANNELS_CONFIG.get(region, {})
    category_channel = channel_config.get('categories', {}).get(category)
    main_channel = channel_config.get('main')
    
    if not category_channel and not main_channel:
        logger.warning(f"Каналы не настроены для региона {region}")
        return {}
    
    user_id = ad.user_id
    deal_type_name = DEAL_TYPES.get(data.get('deal_type'), '')
    condition = data.get('condition')
    condition_text = f" / {CONDITION_TYPES.get(condition, '')}" if condition else ""
    title = data.get('title', '')
    description = data.get('description', '')
    delivery = data.get('delivery')
    delivery_text = f" | {DELIVERY_TYPES.get(delivery, '')}" if delivery else ""
    city_hashtag = get_city_hashtag(city) if city else ""
    subcategory_hashtag = get_subcategory_hashtag(subcategory) if subcategory else ""
    
    text = f"""{city_hashtag} {subcategory_hashtag}

{deal_type_name}{condition_text}

<b>{title}</b>

{description}

💰 {data.get('price', 'Не указана')}{delivery_text}

━━━━━━━━━━━━━━━
📢 <a href="https://t.me/{bot_info.username}">Разместить объявление</a>
😎 <a href="tg://user?id={user_id}">Написать продавцу</a>
👾 <a href="https://t.me/{bot_info.username}?start=profile_{user_id}">Профиль продавца</a>"""

    photos = data.get('photos', [])
    video = data.get('video')
    
    channels = []
    if category_channel:
        channels.append(category_channel)
    if main_channel:
        channels.append(main_channel)
    
    # Словарь для сохранения message_id
    channel_message_ids = {}
    
    for channel in channels:
        try:
            logger.info(f"Публикация в канал: {channel}")
            
            sent_message = None
            
            if photos or video:
                media_group = []
                
                for i, photo in enumerate(photos[:9]):
                    if i == 0:
                        media_group.append(InputMediaPhoto(media=photo, caption=text))
                    else:
                        media_group.append(InputMediaPhoto(media=photo))
                
                if video:
                    if not media_group:
                        media_group.append(InputMediaVideo(media=video, caption=text))
                    else:
                        media_group.append(InputMediaVideo(media=video))
                
                if len(media_group) == 1:
                    if photos:
                        sent_message = await bot.send_photo(chat_id=channel, photo=photos[0], caption=text)
                    else:
                        sent_message = await bot.send_video(chat_id=channel, video=video, caption=text)
                else:
                    # media_group возвращает список сообщений, берём первое
                    sent_messages = await bot.send_media_group(chat_id=channel, media=media_group)
                    if sent_messages:
                        sent_message = sent_messages[0]
            else:
                sent_message = await bot.send_message(chat_id=channel, text=text)
            
            # Сохраняем message_id
            if sent_message:
                channel_message_ids[channel] = sent_message.message_id
                logger.info(f"Опубликовано в {channel}, message_id={sent_message.message_id}")
            
        except Exception as e:
            logger.error(f"Ошибка публикации в {channel}: {e}")
            # Пробуем отправить только текст
            try:
                await asyncio.sleep(0.5)
                sent_message = await bot.send_message(chat_id=channel, text=text + "\n\n⚠️ Медиа временно недоступны")
                if sent_message:
                    channel_message_ids[channel] = sent_message.message_id
            except Exception as e2:
                logger.error(f"Повторная ошибка: {e2}")
    
    return channel_message_ids


@router.callback_query(F.data == "cancel")
async def cancel_creation(callback: CallbackQuery, state: FSMContext):
    """Отмена создания"""
    logger.info(f"[AD_CREATION] cancel_creation")
    await state.clear()
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except:
        pass
    await callback.message.answer("❌ Создание отменено.")
    await callback.answer()
