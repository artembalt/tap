# bot/handlers/ad_creation.py
"""ИСПРАВЛЕННАЯ ВЕРСИЯ - хэштеги, профиль продавца, оптимизация фото"""

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


async def send_with_retry(message: Message, text: str, reply_markup=None, max_retries: int = 5):
    """Отправка сообщения с retry для обхода cold start"""
    for attempt in range(max_retries):
        try:
            return await message.answer(text, reply_markup=reply_markup)
        except TelegramNetworkError as e:
            if attempt < max_retries - 1:
                logger.warning(f"Сетевая ошибка (попытка {attempt+1}), повтор: {e}")
                await asyncio.sleep(0.2)
            else:
                logger.error(f"Не удалось отправить сообщение: {e}")
                raise
from shared.regions_config import (
    REGIONS, CITIES, CATEGORIES, SUBCATEGORIES, DEAL_TYPES,
    CONDITION_TYPES, DELIVERY_TYPES, CATEGORIES_WITH_DELIVERY,
    DEAL_TYPES_WITH_CONDITION, CHANNELS_CONFIG,
    get_city_hashtag, get_subcategory_hashtag
)

logger = logging.getLogger(__name__)
router = Router(name='ad_creation')

logger.info("ad_creation.router создан")


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
    logger.info(f"[NEW_AD] callback new_ad, user={callback.from_user.id}")
    await callback.answer()
    await state.clear()
    await ask_region(callback.message, state)


@router.message(F.text.in_(["Создать объявление", "📝 Подать объявление", "/create"]))
async def start_creation(message: Message, state: FSMContext):
    logger.info(f"[NEW_AD] message, user={message.from_user.id}")
    await state.clear()
    await ask_region(message, state)


# ========== РЕГИОН ==========
async def ask_region(message: Message, state: FSMContext):
    logger.info("[REGION] ask_region вызван")
    await state.set_state(AdCreation.region)
    
    current = await state.get_state()
    logger.info(f"[REGION] state установлен: {current}")
    
    from bot.keyboards.inline import get_regions_keyboard
    await message.answer(
        "📍 <b>Шаг 1: Регион</b>\n\nВыберите регион:", 
        reply_markup=get_regions_keyboard()
    )
    logger.info("[REGION] сообщение отправлено")


@router.callback_query(F.data.startswith("region_"))
async def process_region(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора региона"""
    logger.info(f"[REGION] process_region: data={callback.data}, user={callback.from_user.id}")
    
    region = callback.data.replace("region_", "")
    await state.update_data(region=region)
    
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception as e:
        logger.warning(f"[REGION] edit_reply_markup: {e}")
    
    region_name = REGIONS.get(region, region)
    await callback.message.answer(f"✅ <b>Регион:</b> {region_name}")
    
    await ask_city(callback.message, state, region)
    await callback.answer()


# ========== ГОРОД ==========
async def ask_city(message: Message, state: FSMContext, region: str):
    logger.info(f"[CITY] ask_city, region={region}")
    await state.set_state(AdCreation.city)
    
    from bot.keyboards.inline import get_cities_keyboard
    await message.answer(
        "🏙 <b>Шаг 2: Город</b>\n\nВыберите город:", 
        reply_markup=get_cities_keyboard(region)
    )


@router.callback_query(F.data.startswith("city_"))
async def process_city(callback: CallbackQuery, state: FSMContext):
    logger.info(f"[CITY] process_city: {callback.data}")
    
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
    logger.info("[BACK] back_to_region")
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except:
        pass
    await ask_region(callback.message, state)
    await callback.answer()


# ========== КАТЕГОРИЯ ==========
async def ask_category(message: Message, state: FSMContext):
    logger.info("[CATEGORY] ask_category")
    await state.set_state(AdCreation.category)
    
    from bot.keyboards.inline import get_categories_keyboard
    await message.answer(
        "📂 <b>Шаг 3: Категория</b>\n\nВыберите категорию:", 
        reply_markup=get_categories_keyboard()
    )


@router.callback_query(F.data.startswith("category_"))
async def process_category(callback: CallbackQuery, state: FSMContext):
    logger.info(f"[CATEGORY] process_category: {callback.data}")
    
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
    logger.info("[BACK] back_to_city")
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
    logger.info(f"[SUBCATEGORY] ask_subcategory, category={category}")
    await state.set_state(AdCreation.subcategory)
    
    from bot.keyboards.inline import get_subcategories_keyboard
    await message.answer(
        "📑 <b>Шаг 4: Рубрика</b>\n\nВыберите рубрику:", 
        reply_markup=get_subcategories_keyboard(category)
    )


@router.callback_query(F.data.startswith("subcategory_"))
async def process_subcategory(callback: CallbackQuery, state: FSMContext):
    logger.info(f"[SUBCATEGORY] process_subcategory: {callback.data}")
    
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
    logger.info("[BACK] back_to_category")
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except:
        pass
    await ask_category(callback.message, state)
    await callback.answer()


# ========== ТИП СДЕЛКИ ==========
async def ask_deal_type(message: Message, state: FSMContext):
    logger.info("[DEAL] ask_deal_type")
    await state.set_state(AdCreation.deal_type)
    
    from bot.keyboards.inline import get_deal_types_keyboard
    await message.answer(
        "💼 <b>Шаг 5: Тип сделки</b>\n\nЧто вы хотите сделать?", 
        reply_markup=get_deal_types_keyboard()
    )


@router.callback_query(F.data.startswith("deal_"))
async def process_deal_type(callback: CallbackQuery, state: FSMContext):
    logger.info(f"[DEAL] process_deal_type: {callback.data}")
    
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
    logger.info("[BACK] back_to_subcategory")
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
    logger.info("[TITLE] ask_title")
    await state.set_state(AdCreation.title)
    await message.answer("📝 <b>Шаг 6: Заголовок</b>\n\nВведите заголовок (до 100 символов):")


@router.message(AdCreation.title)
async def process_title(message: Message, state: FSMContext):
    logger.info(f"[TITLE] process_title: {message.text[:30] if message.text else 'None'}")
    
    if not message.text:
        await message.answer("❌ Введите текст")
        return
    
    title = message.text.strip()[:100]
    await state.update_data(title=title)
    await message.answer(f"✅ <b>Заголовок:</b> {title}")
    await ask_description(message, state)


# ========== ОПИСАНИЕ ==========
async def ask_description(message: Message, state: FSMContext):
    logger.info("[DESC] ask_description")
    await state.set_state(AdCreation.description)
    await message.answer("📄 <b>Шаг 7: Описание</b>\n\nВведите описание (до 1000 символов):")


@router.message(AdCreation.description)
async def process_description(message: Message, state: FSMContext):
    logger.info("[DESC] process_description")
    
    if not message.text:
        await message.answer("❌ Введите текст")
        return
    
    description = message.text.strip()[:1000]
    await state.update_data(description=description)
    
    display = description[:50] + "..." if len(description) > 50 else description
    await message.answer(f"✅ <b>Описание:</b> {display}")
    
    data = await state.get_data()
    deal_type = data.get('deal_type')
    
    if deal_type in DEAL_TYPES_WITH_CONDITION:
        await ask_condition(message, state)
    else:
        await ask_photos(message, state)


# ========== СОСТОЯНИЕ ==========
async def ask_condition(message: Message, state: FSMContext):
    logger.info("[CONDITION] ask_condition")
    await state.set_state(AdCreation.condition)
    
    from bot.keyboards.inline import get_condition_keyboard
    await message.answer(
        "📦 <b>Шаг 8: Состояние</b>\n\nВыберите состояние:", 
        reply_markup=get_condition_keyboard()
    )


@router.callback_query(F.data.startswith("condition_"))
async def process_condition(callback: CallbackQuery, state: FSMContext):
    logger.info(f"[CONDITION] process_condition: {callback.data}")
    
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


# ========== ФОТО (ИСПРАВЛЕНО - без лишних сообщений) ==========
async def ask_photos(message: Message, state: FSMContext):
    logger.info("[PHOTOS] ask_photos")
    await state.set_state(AdCreation.photos)
    await state.update_data(photos=[], photo_msg_id=None)
    
    from bot.keyboards.inline import get_photo_skip_keyboard
    msg = await message.answer(
        "📸 <b>Шаг 9: Фото</b>\n\n"
        "Отправьте фото (до 10 шт) или нажмите <b>Пропустить</b>.\n"
        "Загружено: 0/10",
        reply_markup=get_photo_skip_keyboard()
    )
    # Сохраняем ID сообщения для обновления
    await state.update_data(photo_msg_id=msg.message_id)


@router.message(AdCreation.photos, F.photo)
async def process_photo(message: Message, state: FSMContext):
    """ИСПРАВЛЕНО: обновляем одно сообщение вместо отправки новых"""
    data = await state.get_data()
    photos = data.get("photos", [])
    photo_msg_id = data.get("photo_msg_id")
    
    if len(photos) >= 10:
        return
    
    photo_id = message.photo[-1].file_id
    if photo_id not in photos:
        photos.append(photo_id)
        await state.update_data(photos=photos)
    
    count = len(photos)
    
    # Обновляем существующее сообщение вместо отправки нового
    from bot.keyboards.inline import get_photo_done_keyboard
    try:
        if photo_msg_id:
            await message.bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=photo_msg_id,
                text=f"📸 <b>Шаг 9: Фото</b>\n\n"
                     f"✅ Загружено: {count}/10 фото\n\n"
                     f"Отправьте ещё или нажмите <b>Далее</b>.",
                reply_markup=get_photo_done_keyboard()
            )
    except Exception as e:
        logger.warning(f"[PHOTOS] Не удалось обновить сообщение: {e}")
        # Fallback - отправляем новое сообщение только если не удалось обновить
        msg = await message.answer(
            f"✅ Загружено {count}/10 фото. Нажмите <b>Далее</b>.",
            reply_markup=get_photo_done_keyboard()
        )
        await state.update_data(photo_msg_id=msg.message_id)


@router.callback_query(F.data == "photos_skip")
async def skip_photos(callback: CallbackQuery, state: FSMContext):
    logger.info("[PHOTOS] skip")
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except:
        pass
    await callback.message.answer("✅ <b>Фото:</b> пропущено")
    await ask_video(callback.message, state)
    await callback.answer()


@router.callback_query(F.data == "photos_done")
async def photos_done(callback: CallbackQuery, state: FSMContext):
    logger.info("[PHOTOS] done")
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except:
        pass
    
    data = await state.get_data()
    count = len(data.get('photos', []))
    await callback.message.answer(f"✅ <b>Фото:</b> {count} шт.")
    
    await ask_video(callback.message, state)
    await callback.answer()


# ========== ВИДЕО ==========
async def ask_video(message: Message, state: FSMContext):
    logger.info("[VIDEO] ask_video")
    await state.set_state(AdCreation.video)
    
    from bot.keyboards.inline import get_video_keyboard
    await message.answer(
        "🎬 <b>Шаг 10: Видео</b>\n\nОтправьте видео или нажмите <b>Пропустить</b>.",
        reply_markup=get_video_keyboard()
    )


@router.message(AdCreation.video, F.video)
async def process_video(message: Message, state: FSMContext):
    logger.info("[VIDEO] video received")
    await state.update_data(video=message.video.file_id)
    await message.answer("✅ <b>Видео:</b> загружено")
    await ask_price(message, state)


@router.callback_query(F.data == "video_skip")
async def skip_video(callback: CallbackQuery, state: FSMContext):
    logger.info("[VIDEO] skip")
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except:
        pass
    await ask_price(callback.message, state)
    await callback.answer()


# ========== ЦЕНА ==========
async def ask_price(message: Message, state: FSMContext):
    logger.info("[PRICE] ask_price")
    await state.set_state(AdCreation.price)
    
    from bot.keyboards.inline import get_price_keyboard
    await message.answer(
        "💰 <b>Шаг 11: Цена</b>\n\nВведите цену:", 
        reply_markup=get_price_keyboard()
    )


@router.message(AdCreation.price)
async def process_price(message: Message, state: FSMContext):
    logger.info("[PRICE] process_price")
    
    if not message.text:
        await message.answer("❌ Введите число")
        return
    
    try:
        price = float(message.text.strip().replace(" ", "").replace(",", "."))
        price_display = f"{int(price):,} ₽".replace(",", " ")
    except ValueError:
        await message.answer("❌ Введите число")
        return
    
    await state.update_data(price=price_display)
    await message.answer(f"✅ <b>Цена:</b> {price_display}")
    
    data = await state.get_data()
    if data.get('category') in CATEGORIES_WITH_DELIVERY:
        await ask_delivery(message, state)
    else:
        await show_preview(message, state)


@router.callback_query(F.data == "price_negotiable")
async def price_negotiable(callback: CallbackQuery, state: FSMContext):
    logger.info("[PRICE] negotiable")
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except:
        pass
    
    await state.update_data(price="Договорная")
    await callback.message.answer("✅ <b>Цена:</b> Договорная")
    
    data = await state.get_data()
    if data.get('category') in CATEGORIES_WITH_DELIVERY:
        await ask_delivery(callback.message, state)
    else:
        await show_preview(callback.message, state)
    await callback.answer()


# ========== ДОСТАВКА ==========
async def ask_delivery(message: Message, state: FSMContext):
    logger.info("[DELIVERY] ask_delivery")
    await state.set_state(AdCreation.delivery)
    
    from bot.keyboards.inline import get_delivery_keyboard
    await message.answer(
        "🚚 <b>Шаг 12: Доставка</b>\n\nВыберите:", 
        reply_markup=get_delivery_keyboard()
    )


@router.callback_query(F.data.startswith("delivery_"))
async def process_delivery(callback: CallbackQuery, state: FSMContext):
    logger.info(f"[DELIVERY] {callback.data}")
    
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
    logger.info("[PREVIEW] show_preview")
    data = await state.get_data()
    await state.set_state(AdCreation.confirm)

    description = data.get('description') or ''

    text = f"""📢 <b>Превью</b>

📍 {REGIONS.get(data.get('region', ''), '')}
📂 {CATEGORIES.get(data.get('category', ''), '')}
💼 {DEAL_TYPES.get(data.get('deal_type', ''), '')}

<b>{data.get('title', '')}</b>

{description[:200]}{'...' if len(description) > 200 else ''}

💰 {data.get('price', 'Не указана')}
📸 {len(data.get('photos', []))} фото

<b>Опубликовать?</b>"""

    from bot.keyboards.inline import get_confirm_with_edit_keyboard
    from aiogram.exceptions import TelegramNetworkError

    # Retry отправки сообщения (до 5 попыток с коротким интервалом)
    for attempt in range(5):
        try:
            await message.answer(text, reply_markup=get_confirm_with_edit_keyboard())
            return
        except TelegramNetworkError as e:
            if attempt < 4:
                logger.warning(f"[PREVIEW] Сетевая ошибка (попытка {attempt+1}), повтор: {e}")
                await asyncio.sleep(0.2)
            else:
                logger.error(f"[PREVIEW] Не удалось отправить превью: {e}")
                await message.answer("⚠️ Ошибка сети. Попробуйте ещё раз.")


# ========== ПУБЛИКАЦИЯ ==========
@router.callback_query(F.data == "confirm_publish")
async def confirm_ad(callback: CallbackQuery, state: FSMContext):
    logger.info("[PUBLISH] confirm_ad")
    
    data = await state.get_data()
    
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except:
        pass
    
    await callback.answer("⏳ Публикуем...")
    
    try:
        bot_info = await callback.message.bot.get_me()
        
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
                channel_message_ids={},
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
        
        # Публикация в каналы
        channel_ids = await publish_to_channel(callback.message.bot, bot_info, ad, data)
        
        if channel_ids:
            async with get_db_session() as session:
                from sqlalchemy import update
                stmt = update(Ad).where(Ad.id == ad_id).values(channel_message_ids=channel_ids)
                await session.execute(stmt)
                await session.commit()
        
        await callback.message.answer(f"✅ <b>Опубликовано!</b>\n\nID: <code>{ad_id}</code>")
        
    except Exception as e:
        logger.error(f"[PUBLISH] Ошибка: {e}", exc_info=True)
        await callback.message.answer("❌ Ошибка. Попробуйте позже.")
    
    await state.clear()


@router.callback_query(F.data == "cancel_ad")
async def cancel_ad(callback: CallbackQuery, state: FSMContext):
    logger.info("[CANCEL] cancel_ad")
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except:
        pass
    await state.clear()
    await callback.message.answer("❌ Отменено.")
    await callback.answer()


@router.callback_query(F.data == "edit_ad")
async def edit_ad_preview(callback: CallbackQuery, state: FSMContext):
    logger.info("[EDIT] edit_ad")
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except:
        pass
    await callback.message.answer("✏️ Редактирование в разработке.")
    await callback.answer()


# ========== ПУБЛИКАЦИЯ В КАНАЛ (ИСПРАВЛЕНО) ==========
async def publish_to_channel(bot, bot_info, ad, data) -> dict:
    """
    Публикация в канал - ИСПРАВЛЕННАЯ ВЕРСИЯ
    
    Исправления:
    1. Добавлены хэштеги города и категории
    2. Добавлена ссылка на профиль продавца
    """
    logger.info(f"[CHANNEL] publish, ad_id={ad.id}")
    
    region = data.get('region', '')
    category = data.get('category', '')
    city = data.get('city', '')
    subcategory = data.get('subcategory', '')
    
    channel_config = CHANNELS_CONFIG.get(region, {})
    category_channel = channel_config.get('categories', {}).get(category)
    main_channel = channel_config.get('main')
    
    if not category_channel and not main_channel:
        logger.warning(f"[CHANNEL] каналы не настроены для {region}")
        return {}
    
    # ===== ИСПРАВЛЕНИЕ 1: Формируем хэштеги =====
    hashtags = []
    
    # Хэштег рубрики (подкатегории)
    if subcategory:
        subcategory_hashtag = get_subcategory_hashtag(subcategory)
        hashtags.append(subcategory_hashtag)
    
    # Хэштег категории + региона (например #Авто_Калининград)
    if category and region:
        category_name = CATEGORIES.get(category, category)
        region_name = REGIONS.get(region, region)
        # Убираем эмодзи и пробелы для хэштега
        cat_clean = category_name.split()[-1] if ' ' in category_name else category_name
        reg_clean = region_name.replace(' ', '_').replace('-', '_')
        combined_hashtag = f"#{cat_clean}_{reg_clean}"
        hashtags.append(combined_hashtag)
    
    # Хэштег города
    if city:
        city_hashtag = get_city_hashtag(city)
        hashtags.append(city_hashtag)
    
    hashtags_text = " ".join(hashtags) if hashtags else ""
    
    # ===== ИСПРАВЛЕНИЕ 2: Текст объявления с ссылкой на профиль =====
    text = f"""<b>{data.get('title', '')}</b>

{data.get('description', '')}

💰 {data.get('price', 'Не указана')}

{hashtags_text}

━━━━━━━━━━━━━━━
😎 <a href="tg://user?id={ad.user_id}">Написать продавцу</a>
👾 <a href="https://t.me/{bot_info.username}?start=profile_{ad.user_id}">Профиль продавца</a>
📢 <a href="https://t.me/{bot_info.username}">Разместить объявление</a>"""

    photos = data.get('photos', [])
    video = data.get('video')
    channel_ids = {}
    
    channels = []
    if category_channel:
        channels.append(category_channel)
    if main_channel:
        channels.append(main_channel)
    
    for channel in channels:
        try:
            if photos:
                if len(photos) == 1:
                    msg = await bot.send_photo(chat_id=channel, photo=photos[0], caption=text)
                else:
                    media = [InputMediaPhoto(media=photos[0], caption=text)]
                    for p in photos[1:10]:
                        media.append(InputMediaPhoto(media=p))
                    msgs = await bot.send_media_group(chat_id=channel, media=media)
                    msg = msgs[0] if msgs else None
            elif video:
                msg = await bot.send_video(chat_id=channel, video=video, caption=text)
            else:
                msg = await bot.send_message(chat_id=channel, text=text, disable_web_page_preview=True)
            
            if msg:
                channel_ids[channel] = msg.message_id
                logger.info(f"[CHANNEL] опубликовано в {channel}, msg_id={msg.message_id}")
                
        except Exception as e:
            logger.error(f"[CHANNEL] ошибка {channel}: {e}")
    
    return channel_ids


@router.callback_query(F.data == "cancel")
async def cancel_creation(callback: CallbackQuery, state: FSMContext):
    logger.info("[CANCEL] cancel")
    await state.clear()
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except:
        pass
    await callback.message.answer("❌ Отменено.")
    await callback.answer()
