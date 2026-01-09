# bot/handlers/ad_creation.py
"""Обработчики создания объявлений - НОВОЕ: добавлен выбор города"""

import logging
from datetime import datetime
import uuid
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InputMediaPhoto, InputMediaVideo
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
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
router = Router()

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

async def send_with_retry(coro, max_retries=3, delay=1):
    import asyncio
    last_error = None
    for attempt in range(max_retries):
        try:
            return await coro
        except TelegramNetworkError as e:
            last_error = e
            if attempt < max_retries - 1:
                logger.warning(f"Сетевая ошибка, попытка {attempt + 1}/{max_retries}: {e}")
                await asyncio.sleep(delay * (attempt + 1))
    raise last_error

# ========== НАЧАЛО ==========
@router.callback_query(F.data == "new_ad")
async def start_creation_callback(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    await state.update_data(history_messages=[])
    await ask_region(callback.message, state)

@router.message(F.text.in_(["Создать объявление", "📝 Подать объявление", "/create"]))
async def start_creation(message: Message, state: FSMContext):
    await state.clear()
    await state.update_data(history_messages=[])
    await ask_region(message, state)

# ========== РЕГИОН ==========
async def ask_region(message: Message, state: FSMContext):
    await state.set_state(AdCreation.region)
    from bot.keyboards.inline import get_regions_keyboard
    msg = await message.answer("📍 <b>Шаг 1: Регион</b>\n\nВыберите регион:", reply_markup=get_regions_keyboard())
    data = await state.get_data()
    history = data.get('history_messages', [])
    history.append(msg.message_id)
    await state.update_data(history_messages=history)

@router.callback_query(AdCreation.region, F.data.startswith("region_"))
async def process_region(callback: CallbackQuery, state: FSMContext):
    region = callback.data.replace("region_", "")
    await state.update_data(region=region)
    try: await callback.message.edit_reply_markup(reply_markup=None)
    except: pass
    region_name = REGIONS.get(region, region)
    msg = await callback.message.answer(f"✅ <b>Регион:</b> {region_name}")
    data = await state.get_data()
    history = data.get('history_messages', [])
    history.append(msg.message_id)
    await state.update_data(history_messages=history)
    await ask_city(callback.message, state, region)
    await callback.answer()

# ========== ГОРОД ==========
async def ask_city(message: Message, state: FSMContext, region: str):
    await state.set_state(AdCreation.city)
    from bot.keyboards.inline import get_cities_keyboard
    msg = await message.answer("🏙 <b>Шаг 2: Город</b>\n\nВыберите город:", reply_markup=get_cities_keyboard(region))
    data = await state.get_data()
    history = data.get('history_messages', [])
    history.append(msg.message_id)
    await state.update_data(history_messages=history)

@router.callback_query(AdCreation.city, F.data.startswith("city_"))
async def process_city(callback: CallbackQuery, state: FSMContext):
    city = callback.data.replace("city_", "")
    await state.update_data(city=city)
    try: await callback.message.edit_reply_markup(reply_markup=None)
    except: pass
    data = await state.get_data()
    region = data.get('region')
    city_name = CITIES.get(region, {}).get(city, city)
    msg = await callback.message.answer(f"✅ <b>Город:</b> {city_name}")
    history = data.get('history_messages', [])
    history.append(msg.message_id)
    await state.update_data(history_messages=history)
    await ask_category(callback.message, state)
    await callback.answer()

@router.callback_query(AdCreation.city, F.data == "back_to_region")
async def back_to_region(callback: CallbackQuery, state: FSMContext):
    try: await callback.message.edit_reply_markup(reply_markup=None)
    except: pass
    await ask_region(callback.message, state)
    await callback.answer()

# ========== КАТЕГОРИЯ ==========
async def ask_category(message: Message, state: FSMContext):
    await state.set_state(AdCreation.category)
    from bot.keyboards.inline import get_categories_keyboard
    msg = await message.answer("📂 <b>Шаг 3: Категория</b>\n\nВыберите категорию:", reply_markup=get_categories_keyboard())
    data = await state.get_data()
    history = data.get('history_messages', [])
    history.append(msg.message_id)
    await state.update_data(history_messages=history)

@router.callback_query(AdCreation.category, F.data.startswith("category_"))
async def process_category(callback: CallbackQuery, state: FSMContext):
    category = callback.data.replace("category_", "")
    await state.update_data(category=category)
    try: await callback.message.edit_reply_markup(reply_markup=None)
    except: pass
    category_name = CATEGORIES.get(category, category)
    msg = await callback.message.answer(f"✅ <b>Категория:</b> {category_name}")
    data = await state.get_data()
    history = data.get('history_messages', [])
    history.append(msg.message_id)
    await state.update_data(history_messages=history)
    await ask_subcategory(callback.message, state, category)
    await callback.answer()

@router.callback_query(AdCreation.category, F.data == "back_to_city")
async def back_to_city(callback: CallbackQuery, state: FSMContext):
    try: await callback.message.edit_reply_markup(reply_markup=None)
    except: pass
    data = await state.get_data()
    region = data.get('region')
    await ask_city(callback.message, state, region)
    await callback.answer()

# ========== РУБРИКА ==========
async def ask_subcategory(message: Message, state: FSMContext, category: str):
    await state.set_state(AdCreation.subcategory)
    from bot.keyboards.inline import get_subcategories_keyboard
    msg = await message.answer("📑 <b>Шаг 4: Рубрика</b>\n\nВыберите рубрику:", reply_markup=get_subcategories_keyboard(category))
    data = await state.get_data()
    history = data.get('history_messages', [])
    history.append(msg.message_id)
    await state.update_data(history_messages=history)

@router.callback_query(AdCreation.subcategory, F.data.startswith("subcategory_"))
async def process_subcategory(callback: CallbackQuery, state: FSMContext):
    subcategory = callback.data.replace("subcategory_", "")
    await state.update_data(subcategory=subcategory)
    try: await callback.message.edit_reply_markup(reply_markup=None)
    except: pass
    data = await state.get_data()
    category = data.get('category')
    subcategory_name = SUBCATEGORIES.get(category, {}).get(subcategory, subcategory)
    msg = await callback.message.answer(f"✅ <b>Рубрика:</b> {subcategory_name}")
    history = data.get('history_messages', [])
    history.append(msg.message_id)
    await state.update_data(history_messages=history)
    await ask_deal_type(callback.message, state)
    await callback.answer()

@router.callback_query(AdCreation.subcategory, F.data == "back_to_category")
async def back_to_category(callback: CallbackQuery, state: FSMContext):
    try: await callback.message.edit_reply_markup(reply_markup=None)
    except: pass
    await ask_category(callback.message, state)
    await callback.answer()

# ========== ТИП СДЕЛКИ ==========
async def ask_deal_type(message: Message, state: FSMContext):
    await state.set_state(AdCreation.deal_type)
    from bot.keyboards.inline import get_deal_types_keyboard
    msg = await message.answer("💼 <b>Шаг 5: Тип сделки</b>\n\nЧто вы хотите сделать?", reply_markup=get_deal_types_keyboard())
    data = await state.get_data()
    history = data.get('history_messages', [])
    history.append(msg.message_id)
    await state.update_data(history_messages=history)

@router.callback_query(AdCreation.deal_type, F.data.startswith("deal_"))
async def process_deal_type(callback: CallbackQuery, state: FSMContext):
    deal_type = callback.data.replace("deal_", "")
    await state.update_data(deal_type=deal_type)
    try: await callback.message.edit_reply_markup(reply_markup=None)
    except: pass
    deal_type_name = DEAL_TYPES.get(deal_type, deal_type)
    msg = await callback.message.answer(f"✅ <b>Тип:</b> {deal_type_name}")
    data = await state.get_data()
    history = data.get('history_messages', [])
    history.append(msg.message_id)
    await state.update_data(history_messages=history)
    await ask_title(callback.message, state)
    await callback.answer()

@router.callback_query(AdCreation.deal_type, F.data == "back_to_subcategory")
async def back_to_subcategory(callback: CallbackQuery, state: FSMContext):
    try: await callback.message.edit_reply_markup(reply_markup=None)
    except: pass
    data = await state.get_data()
    category = data.get('category')
    await ask_subcategory(callback.message, state, category)
    await callback.answer()

# ========== ЗАГОЛОВОК ==========
async def ask_title(message: Message, state: FSMContext):
    await state.set_state(AdCreation.title)
    msg = await message.answer("📝 <b>Шаг 6: Заголовок</b>\n\nВведите заголовок (до 100 символов):")
    data = await state.get_data()
    history = data.get('history_messages', [])
    history.append(msg.message_id)
    await state.update_data(history_messages=history)

@router.message(AdCreation.title)
async def process_title(message: Message, state: FSMContext):
    title = message.text.strip()[:100]
    await state.update_data(title=title)
    msg = await message.answer(f"✅ <b>Заголовок:</b> {title}")
    data = await state.get_data()
    history = data.get('history_messages', [])
    history.append(msg.message_id)
    await state.update_data(history_messages=history)
    await ask_description(message, state)

# ========== ОПИСАНИЕ ==========
async def ask_description(message: Message, state: FSMContext):
    await state.set_state(AdCreation.description)
    msg = await message.answer("📄 <b>Шаг 7: Описание</b>\n\nВведите описание (до 1000 символов):")
    data = await state.get_data()
    history = data.get('history_messages', [])
    history.append(msg.message_id)
    await state.update_data(history_messages=history)

@router.message(AdCreation.description)
async def process_description(message: Message, state: FSMContext):
    description = message.text.strip()[:1000]
    await state.update_data(description=description)
    display_desc = description[:50] + "..." if len(description) > 50 else description
    msg = await message.answer(f"✅ <b>Описание:</b> {display_desc}")
    data = await state.get_data()
    history = data.get('history_messages', [])
    history.append(msg.message_id)
    await state.update_data(history_messages=history)
    deal_type = data.get('deal_type')
    if deal_type in DEAL_TYPES_WITH_CONDITION:
        await ask_condition(message, state)
    else:
        await ask_photos(message, state)

# ========== СОСТОЯНИЕ ==========
async def ask_condition(message: Message, state: FSMContext):
    await state.set_state(AdCreation.condition)
    from bot.keyboards.inline import get_condition_keyboard
    msg = await message.answer("📦 <b>Шаг 8: Состояние</b>\n\nВыберите состояние:", reply_markup=get_condition_keyboard())
    data = await state.get_data()
    history = data.get('history_messages', [])
    history.append(msg.message_id)
    await state.update_data(history_messages=history)

@router.callback_query(AdCreation.condition, F.data.startswith("condition_"))
async def process_condition(callback: CallbackQuery, state: FSMContext):
    condition = callback.data.replace("condition_", "")
    await state.update_data(condition=condition)
    try: await callback.message.edit_reply_markup(reply_markup=None)
    except: pass
    condition_name = CONDITION_TYPES.get(condition, condition)
    msg = await callback.message.answer(f"✅ <b>Состояние:</b> {condition_name}")
    data = await state.get_data()
    history = data.get('history_messages', [])
    history.append(msg.message_id)
    await state.update_data(history_messages=history)
    await ask_photos(callback.message, state)
    await callback.answer()

# ========== ФОТО ==========
async def ask_photos(message: Message, state: FSMContext):
    await state.set_state(AdCreation.photos)
    await state.update_data(photos=[], photo_prompt_msg_id=None)
    from bot.keyboards.inline import get_photo_skip_keyboard
    msg = await message.answer("📸 <b>Шаг 9: Фото</b>\n\nОтправьте фото (до 10 шт):", reply_markup=get_photo_skip_keyboard())
    data = await state.get_data()
    history = data.get('history_messages', [])
    history.append(msg.message_id)
    await state.update_data(history_messages=history, photo_prompt_msg_id=msg.message_id)

@router.message(AdCreation.photos, F.photo)
async def process_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    photos = data.get('photos', [])
    photo_id = message.photo[-1].file_id
    if photo_id not in photos and len(photos) < 10:
        photos.append(photo_id)
        await state.update_data(photos=photos)
    photo_prompt_msg_id = data.get('photo_prompt_msg_id')
    if photo_prompt_msg_id:
        try:
            await message.bot.delete_message(message.chat.id, photo_prompt_msg_id)
            await state.update_data(photo_prompt_msg_id=None)
        except: pass
    from bot.keyboards.inline import get_photo_done_keyboard
    msg = await message.answer(f"📸 Загружено {len(photos)}/10 фото", reply_markup=get_photo_done_keyboard())
    history = data.get('history_messages', [])
    history.append(msg.message_id)
    await state.update_data(history_messages=history)

@router.callback_query(AdCreation.photos, F.data == "photos_skip")
async def skip_photos(callback: CallbackQuery, state: FSMContext):
    try: await callback.message.edit_reply_markup(reply_markup=None)
    except: pass
    await ask_price(callback.message, state)
    await callback.answer()

@router.callback_query(AdCreation.photos, F.data == "photos_done")
async def photos_done(callback: CallbackQuery, state: FSMContext):
    try: await callback.message.edit_reply_markup(reply_markup=None)
    except: pass
    data = await state.get_data()
    photos_count = len(data.get('photos', []))
    msg = await callback.message.answer(f"✅ <b>Фото:</b> {photos_count} шт.")
    history = data.get('history_messages', [])
    history.append(msg.message_id)
    await state.update_data(history_messages=history)
    await ask_price(callback.message, state)
    await callback.answer()

# ========== ЦЕНА ==========
async def ask_price(message: Message, state: FSMContext):
    await state.set_state(AdCreation.price)
    from bot.keyboards.inline import get_price_keyboard
    msg = await message.answer("💰 <b>Шаг 10: Цена</b>\n\nВведите цену (число):", reply_markup=get_price_keyboard())
    data = await state.get_data()
    history = data.get('history_messages', [])
    history.append(msg.message_id)
    await state.update_data(history_messages=history)

@router.message(AdCreation.price)
async def process_price(message: Message, state: FSMContext):
    price_text = message.text.strip().replace(" ", "").replace(",", ".")
    try:
        price = float(price_text)
        price_display = f"{int(price):,} ₽".replace(",", " ")
    except ValueError:
        await message.answer("❌ Введите число. Например: 15000")
        return
    await state.update_data(price=price_display)
    msg = await message.answer(f"✅ <b>Цена:</b> {price_display}")
    data = await state.get_data()
    history = data.get('history_messages', [])
    history.append(msg.message_id)
    await state.update_data(history_messages=history)
    category = data.get('category')
    if category in CATEGORIES_WITH_DELIVERY:
        await ask_delivery(message, state)
    else:
        await show_preview(message, state)

@router.callback_query(AdCreation.price, F.data == "price_negotiable")
async def price_negotiable(callback: CallbackQuery, state: FSMContext):
    try: await callback.message.edit_reply_markup(reply_markup=None)
    except: pass
    await state.update_data(price="Договорная")
    msg = await callback.message.answer("✅ <b>Цена:</b> Договорная")
    data = await state.get_data()
    history = data.get('history_messages', [])
    history.append(msg.message_id)
    await state.update_data(history_messages=history)
    category = data.get('category')
    if category in CATEGORIES_WITH_DELIVERY:
        await ask_delivery(callback.message, state)
    else:
        await show_preview(callback.message, state)
    await callback.answer()

# ========== ДОСТАВКА ==========
async def ask_delivery(message: Message, state: FSMContext):
    await state.set_state(AdCreation.delivery)
    from bot.keyboards.inline import get_delivery_keyboard
    msg = await message.answer("🚚 <b>Шаг 11: Доставка</b>\n\nВыберите доставку:", reply_markup=get_delivery_keyboard())
    data = await state.get_data()
    history = data.get('history_messages', [])
    history.append(msg.message_id)
    await state.update_data(history_messages=history)

@router.callback_query(AdCreation.delivery, F.data.startswith("delivery_"))
async def process_delivery(callback: CallbackQuery, state: FSMContext):
    delivery = callback.data.replace("delivery_", "")
    await state.update_data(delivery=delivery)
    try: await callback.message.edit_reply_markup(reply_markup=None)
    except: pass
    delivery_name = DELIVERY_TYPES.get(delivery, delivery)
    msg = await callback.message.answer(f"✅ <b>Доставка:</b> {delivery_name}")
    data = await state.get_data()
    history = data.get('history_messages', [])
    history.append(msg.message_id)
    await state.update_data(history_messages=history)
    await show_preview(callback.message, state)
    await callback.answer()

# ========== ПРЕВЬЮ ==========
async def show_preview(message: Message, state: FSMContext):
    logger.info("Показ превью")
    data = await state.get_data()
    await state.set_state(AdCreation.confirm)
    preview_text = format_ad_preview(data)
    if len(preview_text) > 1024:
        preview_text = preview_text[:1020] + "..."
    from bot.keyboards.inline import get_confirm_with_edit_keyboard
    photos = data.get('photos', [])
    logger.info(f"Превью: {len(photos)} фото")
    try:
        if photos:
            if len(photos) == 1:
                await send_with_retry(message.answer_photo(photo=photos[0], caption=preview_text, reply_markup=get_confirm_with_edit_keyboard()))
            else:
                media_group = [InputMediaPhoto(media=photos[0], caption=preview_text)]
                for photo in photos[1:10]:
                    media_group.append(InputMediaPhoto(media=photo))
                await send_with_retry(message.answer_media_group(media=media_group))
                await message.answer("👆 <b>Ваше объявление</b>", reply_markup=get_confirm_with_edit_keyboard())
        else:
            await message.answer(preview_text, reply_markup=get_confirm_with_edit_keyboard())
        logger.info("Превью отправлено")
    except Exception as e:
        logger.error(f"Ошибка превью: {e}")
        await message.answer(preview_text, reply_markup=get_confirm_with_edit_keyboard())

def format_ad_preview(data: dict) -> str:
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
    
    region_name = REGIONS.get(region, region)
    city_name = CITIES.get(region, {}).get(city, city)
    category_name = CATEGORIES.get(category, category)
    subcategory_name = SUBCATEGORIES.get(category, {}).get(subcategory, subcategory)
    deal_type_name = DEAL_TYPES.get(deal_type, '')
    condition_text = f" / {CONDITION_TYPES.get(condition, '')}" if condition else ""
    delivery_text = f"\n🚚 {DELIVERY_TYPES.get(delivery, '')}" if delivery else ""
    
    city_hashtag = get_city_hashtag(city) if city else ""
    subcategory_hashtag = get_subcategory_hashtag(subcategory) if subcategory else ""
    title_text = f"<b>{title}</b>\n\n" if title else ""
    description_text = f"{description[:300]}...\n\n" if len(description) > 300 else f"{description}\n\n" if description else ""
    
    return f"""📢 <b>Превью объявления</b>

{city_hashtag} {subcategory_hashtag}

📍 {region_name}, {city_name}
📂 {category_name} → {subcategory_name}
💼 {deal_type_name}{condition_text}

{title_text}{description_text}💰 {price}{delivery_text}
📸 {photos_count} фото

<b>Всё верно?</b>"""

# ========== ПУБЛИКАЦИЯ ==========
@router.callback_query(AdCreation.confirm, F.data == "confirm_publish")
async def confirm_ad(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    try: await callback.message.edit_reply_markup(reply_markup=None)
    except: pass
    try: await callback.answer("⏳ Публикуем...")
    except: pass
    try:
        bot_info = await callback.message.bot.get_me()
        async with get_db_session() as session:
            price_str = data.get('price', 'Договорная')
            price_value = None if price_str == 'Договорная' else float(price_str.replace(' ₽', '').replace(' ', ''))
            ad = Ad(id=uuid.uuid4(), user_id=callback.from_user.id, title=data.get('title', ''),
                description=data.get('description', ''), price=price_value, region=data.get('region'),
                city=data.get('city'), category=data.get('category'), ad_type=data.get('deal_type'),
                photos=data.get('photos', []), video=data.get('video'), status=AdStatus.ACTIVE.value,
                created_at=datetime.utcnow(), premium_features={'subcategory': data.get('subcategory'),
                'condition': data.get('condition'), 'delivery': data.get('delivery'), 'price_text': data.get('price')})
            session.add(ad)
            await session.commit()
        await callback.message.answer(f"✅ <b>Объявление создано!</b>\n\nID: <code>{ad.id}</code>")
        await publish_to_channel(callback.message.bot, bot_info, ad, data)
    except Exception as e:
        logger.error(f"Ошибка: {e}", exc_info=True)
        await callback.message.answer("❌ Ошибка создания. Попробуйте позже.")
    await state.clear()

@router.callback_query(AdCreation.confirm, F.data == "cancel_ad")
async def cancel_ad(callback: CallbackQuery, state: FSMContext):
    try: await callback.message.edit_reply_markup(reply_markup=None)
    except: pass
    await state.clear()
    await callback.message.answer("❌ Создание отменено.")
    await callback.answer()

@router.callback_query(AdCreation.confirm, F.data == "edit_ad")
async def edit_ad_preview(callback: CallbackQuery, state: FSMContext):
    try: await callback.message.edit_reply_markup(reply_markup=None)
    except: pass
    await callback.message.answer("✏️ Редактирование в разработке.\nСоздайте объявление заново.")
    await callback.answer()

async def publish_to_channel(bot, bot_info, ad, data):
    region = data.get('region', '')
    city = data.get('city', '')
    category = data.get('category', '')
    subcategory = data.get('subcategory', '')
    channel_config = CHANNELS_CONFIG.get(region, {})
    category_channel = channel_config.get('categories', {}).get(category)
    main_channel = channel_config.get('main')
    if not category_channel and not main_channel:
        logger.warning(f"Каналы не настроены для {region}")
        return
    user_id = ad.user_id
    deal_type_name = DEAL_TYPES.get(data.get('deal_type'), '')
    condition = data.get('condition')
    condition_text = f" / {CONDITION_TYPES.get(condition, '')}" if condition else ""
    title = data.get('title', '')
    title_text = f"<b>{title}</b>\n\n" if title else ""
    description = data.get('description', '')
    description_text = f"{description}\n\n" if description else ""
    delivery = data.get('delivery')
    delivery_text = f" | {DELIVERY_TYPES.get(delivery, '')}" if delivery else ""
    city_hashtag = get_city_hashtag(city) if city else ""
    subcategory_hashtag = get_subcategory_hashtag(subcategory) if subcategory else ""
    text = f"""{city_hashtag} {subcategory_hashtag}

{deal_type_name}{condition_text}

{title_text}{description_text}💰 {data.get('price', 'Не указана')}{delivery_text}"""
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="📢 Разместить объявление", url=f"https://t.me/{bot_info.username}")
    keyboard.button(text="😎 Написать продавцу", url=f"tg://user?id={user_id}")
    keyboard.adjust(1)
    reply_markup = keyboard.as_markup()
    photos = data.get('photos', [])
    channels = []
    if category_channel: channels.append(('категорию', category_channel))
    if main_channel: channels.append(('главный', main_channel))
    for name, channel in channels:
        try:
            logger.info(f"Публикация в {name}: {channel}")
            if photos:
                if len(photos) == 1:
                    await send_with_retry(bot.send_photo(chat_id=channel, photo=photos[0], caption=text, reply_markup=reply_markup))
                else:
                    media_group = [InputMediaPhoto(media=photos[0], caption=text)]
                    for photo in photos[1:10]:
                        media_group.append(InputMediaPhoto(media=photo))
                    await send_with_retry(bot.send_media_group(chat_id=channel, media=media_group))
                    await bot.send_message(chat_id=channel, text="👆 Подробнее", reply_markup=reply_markup)
            else:
                await send_with_retry(bot.send_message(chat_id=channel, text=text, reply_markup=reply_markup))
            logger.info(f"Опубликовано в {name}")
        except Exception as e:
            logger.error(f"Ошибка публикации в {channel}: {e}")

@router.callback_query(F.data == "cancel")
async def cancel_creation(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    try: await callback.message.edit_reply_markup(reply_markup=None)
    except: pass
    await callback.message.answer("❌ Создание отменено.")
    await callback.answer()
