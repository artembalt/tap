# bot/handlers/ad_creation.py
"""ИСПРАВЛЕННАЯ ВЕРСИЯ - хэштеги, профиль продавца, оптимизация фото"""

import logging
import asyncio
from datetime import datetime
import uuid
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InputMediaPhoto, InputMediaVideo, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramNetworkError, TelegramAPIError

from bot.database.connection import get_db_session
from bot.database.models import Ad, AdStatus, User
from bot.utils.content_filter import (
    validate_content, validate_content_with_llm, get_rejection_message
)
from bot.services.vision_ocr import recognize_text_on_image, get_vision_ocr_service
from bot.utils.limits import can_create_ad, get_user_limits, get_ad_duration_days
from shared.regions_config import (
    REGIONS, CITIES, CATEGORIES, SUBCATEGORIES, DEAL_TYPES,
    CONDITION_TYPES, DELIVERY_TYPES, CATEGORIES_WITH_DELIVERY,
    DEAL_TYPES_WITH_CONDITION, CHANNELS_CONFIG,
    get_city_hashtag, get_subcategory_hashtag
)

logger = logging.getLogger(__name__)


async def safe_clear_keyboard(callback: CallbackQuery) -> None:
    """Безопасно удаляет клавиатуру у сообщения"""
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except TelegramAPIError as e:
        logger.debug(f"Не удалось убрать клавиатуру: {e}")


async def send_with_retry(message: Message, text: str, reply_markup=None, max_retries: int = 2):
    """Отправка сообщения с retry"""
    for attempt in range(max_retries):
        try:
            return await message.answer(text, reply_markup=reply_markup)
        except TelegramNetworkError as e:
            if attempt < max_retries - 1:
                logger.warning(f"Сетевая ошибка (попытка {attempt+1}), повтор: {e}")
                await asyncio.sleep(1)
            else:
                logger.error(f"Не удалось отправить сообщение: {e}")
                raise


async def check_photos_for_forbidden_text(
    bot: Bot,
    photo_ids: list,
    category: str = None,
    subcategory: str = None
) -> tuple[bool, str]:
    """
    Проверяет фото на наличие запрещённого текста через OCR.

    Returns:
        (is_ok, error_message) - True если всё хорошо, иначе False и сообщение об ошибке
    """
    if not photo_ids:
        return True, ""

    # Проверяем, настроен ли OCR
    ocr_service = get_vision_ocr_service()
    if not ocr_service:
        logger.debug("[OCR] Сервис не настроен, пропускаем проверку фото")
        return True, ""

    logger.info(f"[OCR] Проверяю {len(photo_ids)} фото на запрещённый текст")

    for i, photo_id in enumerate(photo_ids):
        try:
            # Скачиваем фото
            file = await bot.get_file(photo_id)
            file_data = await bot.download_file(file.file_path)
            image_bytes = file_data.read()

            # Определяем формат
            mime_type = "JPEG"
            if file.file_path and file.file_path.endswith(".png"):
                mime_type = "PNG"

            # Распознаём текст
            ocr_result = await recognize_text_on_image(image_bytes, mime_type)

            if not ocr_result.success:
                logger.warning(f"[OCR] Ошибка распознавания фото {i+1}: {ocr_result.error}")
                continue  # При ошибке пропускаем фото, не блокируем

            if not ocr_result.text or len(ocr_result.text.strip()) < 3:
                continue  # Нет текста на фото

            recognized_text = ocr_result.text.strip()
            logger.info(f"[OCR] Фото {i+1}: распознано {len(recognized_text)} символов")

            # Проверяем текст через rule-based фильтр
            is_valid, rejection_reason = validate_content(
                recognized_text,
                content_type="photo_text",
                category=category,
                subcategory=subcategory
            )

            if not is_valid:
                logger.warning(f"[OCR] Фото {i+1} содержит запрещённый текст: {rejection_reason}")
                return False, f"На фото {i+1} обнаружен запрещённый контент:\n{rejection_reason}"

        except Exception as e:
            logger.error(f"[OCR] Ошибка при проверке фото {i+1}: {e}")
            continue  # При ошибке пропускаем, не блокируем

    logger.info("[OCR] Все фото прошли проверку")
    return True, ""


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
    description_ai_pending = State()  # Ожидание после AI-улучшения
    condition = State()
    photos = State()
    video = State()
    price = State()
    delivery = State()
    link_count = State()   # Выбор количества ссылок (1-4)
    link_title = State()   # Название текущей ссылки
    link_url = State()     # URL текущей ссылки
    confirm = State()


# ========== НАЧАЛО ==========
@router.callback_query(F.data == "new_ad")
async def start_creation_callback(callback: CallbackQuery, state: FSMContext):
    logger.info(f"[NEW_AD] callback new_ad, user={callback.from_user.id}")
    await callback.answer()

    # Проверка лимита объявлений
    async with get_db_session() as session:
        user = await session.get(User, callback.from_user.id)
        if user:
            can_create, reason = await can_create_ad(user, session)
            if not can_create:
                from bot.keyboards.billing import get_billing_menu_keyboard
                await callback.message.answer(
                    f"❌ {reason}\n\n"
                    "Вы можете оформить подписку для увеличения лимита:",
                    reply_markup=get_billing_menu_keyboard()
                )
                return

    await state.clear()
    await ask_region(callback.message, state)


@router.message(F.text.in_(["Создать объявление", "📝 Подать объявление", "/create", "/new_ad"]))
async def start_creation(message: Message, state: FSMContext):
    logger.info(f"[NEW_AD] message, user={message.from_user.id}")

    # Проверка лимита объявлений
    async with get_db_session() as session:
        user = await session.get(User, message.from_user.id)
        if user:
            can_create, reason = await can_create_ad(user, session)
            if not can_create:
                from bot.keyboards.billing import get_billing_menu_keyboard
                await message.answer(
                    f"❌ {reason}\n\n"
                    "Вы можете оформить подписку для увеличения лимита:",
                    reply_markup=get_billing_menu_keyboard()
                )
                return

    await state.clear()
    await ask_region(message, state)


# ========== РЕГИОН ==========
async def ask_region(message: Message, state: FSMContext):
    logger.info("[REGION] ask_region вызван")
    await state.set_state(AdCreation.region)

    current = await state.get_state()
    logger.info(f"[REGION] state установлен: {current}")

    from bot.keyboards.inline import get_regions_keyboard
    await send_with_retry(
        message,
        "📍 <b>Шаг 1: Регион</b>\n\nВыберите регион:",
        reply_markup=get_regions_keyboard()
    )
    logger.info("[REGION] сообщение отправлено")


@router.callback_query(F.data.startswith("region_"))
async def process_region(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора региона"""
    logger.info(f"[REGION] process_region: data={callback.data}, user={callback.from_user.id}")

    region = callback.data.replace("region_", "")

    # Валидация: проверяем что регион существует
    if region not in REGIONS:
        logger.warning(f"[REGION] Неизвестный регион: {region}")
        await callback.answer("❌ Неизвестный регион", show_alert=True)
        return

    await state.update_data(region=region)
    await safe_clear_keyboard(callback)

    region_name = REGIONS.get(region)
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

    # Валидация: проверяем что город существует в этом регионе
    if region not in CITIES or city not in CITIES.get(region, {}):
        logger.warning(f"[CITY] Неизвестный город: {city} в регионе {region}")
        await callback.answer("❌ Неизвестный город", show_alert=True)
        return

    await state.update_data(city=city)
    await safe_clear_keyboard(callback)

    city_name = CITIES[region][city]
    await callback.message.answer(f"✅ <b>Город:</b> {city_name}")

    await ask_category(callback.message, state)
    await callback.answer()


@router.callback_query(F.data == "back_to_region")
async def back_to_region(callback: CallbackQuery, state: FSMContext):
    logger.info("[BACK] back_to_region")
    await safe_clear_keyboard(callback)
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

    # Валидация: проверяем что категория существует
    if category not in CATEGORIES:
        logger.warning(f"[CATEGORY] Неизвестная категория: {category}")
        await callback.answer("❌ Неизвестная категория", show_alert=True)
        return

    await state.update_data(category=category)
    await safe_clear_keyboard(callback)

    category_name = CATEGORIES[category]
    await callback.message.answer(f"✅ <b>Категория:</b> {category_name}")

    await ask_subcategory(callback.message, state, category)
    await callback.answer()


@router.callback_query(F.data == "back_to_city")
async def back_to_city(callback: CallbackQuery, state: FSMContext):
    logger.info("[BACK] back_to_city")
    await safe_clear_keyboard(callback)
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

    # Валидация: проверяем что рубрика существует в этой категории
    if category not in SUBCATEGORIES or subcategory not in SUBCATEGORIES.get(category, {}):
        logger.warning(f"[SUBCATEGORY] Неизвестная рубрика: {subcategory} в категории {category}")
        await callback.answer("❌ Неизвестная рубрика", show_alert=True)
        return

    await state.update_data(subcategory=subcategory)
    await safe_clear_keyboard(callback)

    subcategory_name = SUBCATEGORIES[category][subcategory]
    await callback.message.answer(f"✅ <b>Рубрика:</b> {subcategory_name}")

    await ask_deal_type(callback.message, state)
    await callback.answer()


@router.callback_query(F.data == "back_to_category")
async def back_to_category(callback: CallbackQuery, state: FSMContext):
    logger.info("[BACK] back_to_category")
    await safe_clear_keyboard(callback)
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

    # Валидация: проверяем что тип сделки существует
    if deal_type not in DEAL_TYPES:
        logger.warning(f"[DEAL] Неизвестный тип сделки: {deal_type}")
        await callback.answer("❌ Неизвестный тип сделки", show_alert=True)
        return

    await state.update_data(deal_type=deal_type)
    await safe_clear_keyboard(callback)

    deal_type_name = DEAL_TYPES[deal_type]
    await callback.message.answer(f"✅ <b>Тип:</b> {deal_type_name}")

    await ask_title(callback.message, state)
    await callback.answer()


@router.callback_query(F.data == "back_to_subcategory")
async def back_to_subcategory(callback: CallbackQuery, state: FSMContext):
    logger.info("[BACK] back_to_subcategory")
    await safe_clear_keyboard(callback)
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

    # Быстрая rule-based проверка (бесплатно)
    filter_result = validate_content(title)
    if not filter_result.is_valid:
        await message.answer(get_rejection_message(filter_result))
        return

    # LLM-проверка (показываем индикатор)
    checking_msg = await message.answer("🔍 <i>Проверяю текст...</i>")
    try:
        data = await state.get_data()
        ad_category = data.get('category')
        ad_subcategory = data.get('subcategory')  # Рубрика для контекста

        llm_result = await validate_content_with_llm(title, ad_category, ad_subcategory)
        if not llm_result.is_valid:
            await checking_msg.delete()
            await message.answer(get_rejection_message(llm_result))
            return
        await checking_msg.delete()
    except Exception as e:
        logger.error(f"[TITLE] LLM error: {e}")
        await checking_msg.delete()
        # Fail-open: продолжаем, если LLM недоступен

    await state.update_data(title=title)
    await message.answer(f"✅ <b>Заголовок:</b> {title}")
    await ask_description(message, state)


# ========== ОПИСАНИЕ ==========
async def ask_description(message: Message, state: FSMContext):
    logger.info("[DESC] ask_description")
    await state.set_state(AdCreation.description)
    await message.answer(
        "📄 <b>Шаг 7: Описание</b>\n\n"
        "Введите описание (до 1000 символов).\n\n"
        "💡 <i>После ввода вы сможете улучшить описание с помощью ИИ.</i>"
    )


@router.message(AdCreation.description)
async def process_description(message: Message, state: FSMContext):
    logger.info("[DESC] process_description")

    if not message.text:
        await message.answer("❌ Введите текст")
        return

    description = message.text.strip()[:1000]

    # Быстрая rule-based проверка (бесплатно)
    filter_result = validate_content(description)
    if not filter_result.is_valid:
        await message.answer(get_rejection_message(filter_result))
        return

    # LLM-проверка описания (показываем индикатор)
    checking_msg = await message.answer("🔍 <i>Проверяю описание...</i>")
    try:
        # Проверяем заголовок + описание вместе для лучшего контекста
        data = await state.get_data()
        title = data.get('title', '')
        ad_category = data.get('category')
        ad_subcategory = data.get('subcategory')  # Рубрика для контекста
        full_text = f"{title}\n\n{description}"

        llm_result = await validate_content_with_llm(full_text, ad_category, ad_subcategory)
        if not llm_result.is_valid:
            await checking_msg.delete()
            await message.answer(get_rejection_message(llm_result))
            return
        await checking_msg.delete()
    except Exception as e:
        logger.error(f"[DESC] LLM error: {e}")
        await checking_msg.delete()
        # Fail-open: продолжаем, если LLM недоступен

    # Сохраняем в pending для возможности улучшения
    await state.update_data(pending_description=description)
    await state.set_state(AdCreation.description_ai_pending)

    from bot.keyboards.inline import get_description_confirm_keyboard
    await message.answer(
        f"📝 <b>Ваше описание:</b>\n\n"
        f"<code>{description}</code>\n\n"
        f"Выберите действие:",
        reply_markup=get_description_confirm_keyboard()
    )


async def _go_to_next_after_description(message: Message, state: FSMContext):
    """Переход на следующий шаг после описания"""
    data = await state.get_data()
    deal_type = data.get('deal_type')

    if deal_type in DEAL_TYPES_WITH_CONDITION:
        await ask_condition(message, state)
    else:
        await ask_photos(message, state)


# ========== AI-УЛУЧШЕНИЕ ОПИСАНИЯ ==========
@router.callback_query(F.data == "ai_improve_description")
async def ai_improve_description_callback(callback: CallbackQuery, state: FSMContext):
    """Улучшение описания с помощью ИИ"""
    logger.info(f"[AI_DESC] ai_improve_description, user={callback.from_user.id}")
    await callback.answer()

    data = await state.get_data()
    current_desc = data.get('pending_description') or data.get('description')

    if not current_desc:
        await callback.message.answer(
            "❌ Сначала введите описание, затем нажмите кнопку для улучшения."
        )
        return

    # Показываем индикатор загрузки
    processing_msg = await callback.message.answer("🔄 <i>Улучшаю описание с помощью ИИ...</i>")

    try:
        from bot.services.ai_description import improve_description
        result = await improve_description(
            original_text=current_desc,
            title=data.get('title'),
            category=data.get('category'),
            subcategory=data.get('subcategory'),
        )

        await processing_msg.delete()

        if not result.success:
            await callback.message.answer(f"❌ {result.error}")
            return

        # Сохраняем улучшенное описание как pending
        await state.update_data(pending_description=result.improved_text)
        await state.set_state(AdCreation.description_ai_pending)

        from bot.keyboards.inline import get_ai_description_result_keyboard
        await callback.message.answer(
            f"✨ <b>Улучшенное описание:</b>\n\n"
            f"<code>{result.improved_text}</code>\n\n"
            f"👆 <i>Нажмите на текст, чтобы скопировать и отредактировать.</i>",
            reply_markup=get_ai_description_result_keyboard()
        )

    except Exception as e:
        logger.error(f"[AI_DESC] Ошибка: {e}")
        await processing_msg.delete()
        await callback.message.answer("❌ Произошла ошибка, попробуйте позже.")


@router.callback_query(F.data == "desc_confirm_next")
async def desc_confirm_next_callback(callback: CallbackQuery, state: FSMContext):
    """Подтвердить описание и перейти дальше"""
    logger.info(f"[DESC] desc_confirm_next, user={callback.from_user.id}")
    await callback.answer()

    data = await state.get_data()
    description = data.get('pending_description')

    if not description:
        await callback.message.answer("❌ Описание не найдено.")
        return

    # Сохраняем как основное описание
    await state.update_data(description=description, pending_description=None)

    display = description[:50] + "..." if len(description) > 50 else description
    await callback.message.answer(f"✅ <b>Описание:</b> {display}")

    await _go_to_next_after_description(callback.message, state)


@router.callback_query(F.data == "ai_desc_use")
async def ai_desc_use_callback(callback: CallbackQuery, state: FSMContext):
    """Использовать улучшенное описание"""
    logger.info(f"[AI_DESC] ai_desc_use, user={callback.from_user.id}")
    await callback.answer()

    data = await state.get_data()
    improved_desc = data.get('pending_description')

    if not improved_desc:
        await callback.message.answer("❌ Описание не найдено.")
        return

    # Сохраняем как основное описание
    await state.update_data(description=improved_desc, pending_description=None)

    display = improved_desc[:50] + "..." if len(improved_desc) > 50 else improved_desc
    await callback.message.answer(f"✅ <b>Описание сохранено:</b> {display}")

    await _go_to_next_after_description(callback.message, state)


@router.message(AdCreation.description_ai_pending)
async def process_description_ai_pending(message: Message, state: FSMContext):
    """Обработка нового текста после AI-улучшения (пользователь отредактировал)"""
    logger.info("[AI_DESC] process_description_ai_pending - пользователь ввёл новый текст")

    if not message.text:
        await message.answer("❌ Введите текст описания")
        return

    description = message.text.strip()[:1000]

    # Проверка контента
    filter_result = validate_content(description)
    if not filter_result.is_valid:
        await message.answer(get_rejection_message(filter_result))
        return

    # Сохраняем как pending для возможности улучшения
    await state.update_data(pending_description=description)

    from bot.keyboards.inline import get_ai_description_result_keyboard
    await message.answer(
        f"📝 <b>Ваше описание:</b>\n\n"
        f"<code>{description}</code>\n\n"
        f"Выберите действие:",
        reply_markup=get_ai_description_result_keyboard()
    )


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
    
    await safe_clear_keyboard(callback)
    
    condition_name = CONDITION_TYPES.get(condition, condition)
    await callback.message.answer(f"✅ <b>Состояние:</b> {condition_name}")
    
    await ask_photos(callback.message, state)
    await callback.answer()


# ========== ФОТО ==========
async def ask_photos(message: Message, state: FSMContext):
    logger.info("[PHOTOS] ask_photos")
    await state.set_state(AdCreation.photos)
    await state.update_data(photos=[], photo_batch_id=0)

    from bot.keyboards.inline import get_photo_skip_keyboard
    await message.answer(
        "📸 <b>Шаг 9: Фото</b>\n\n"
        "Отправьте фото (до 10 шт) или нажмите <b>Пропустить</b>.\n\n"
        "💡 <i>Если хотите добавить видео — загрузите не более 9 фото.\n"
        "При 10 фото видео заменит последнее фото.</i>",
        reply_markup=get_photo_skip_keyboard()
    )


@router.message(AdCreation.photos, F.photo)
async def process_photo(message: Message, state: FSMContext):
    """Обработка фото - новое сообщение после каждой загрузки"""
    import time
    from bot.keyboards.inline import get_photo_done_keyboard

    data = await state.get_data()
    photos = data.get("photos", [])

    # Проверяем лимит
    if len(photos) >= 10:
        await message.answer("⚠️ Достигнут лимит 10 фото. Нажмите <b>Далее</b> для продолжения.",
                           reply_markup=get_photo_done_keyboard())
        return

    # Проверяем дубликат
    photo_id = message.photo[-1].file_id
    is_duplicate = photo_id in photos

    if not is_duplicate:
        photos.append(photo_id)

    # Генерируем batch_id для группировки media group
    batch_id = time.time()
    await state.update_data(photos=photos, photo_batch_id=batch_id, last_was_duplicate=is_duplicate)

    # Задержка для сбора всех фото из media group
    await asyncio.sleep(0.5)

    # Проверяем, что за это время не пришло новых фото
    fresh_data = await state.get_data()
    if fresh_data.get("photo_batch_id") != batch_id:
        return

    # Получаем актуальные данные
    photos = fresh_data.get("photos", [])
    count = len(photos)

    # Формируем сообщение
    if fresh_data.get("last_was_duplicate"):
        text = f"⚠️ Некоторые фото уже были загружены ранее.\n\n"
    else:
        text = ""

    text += f"✅ <b>Загружено: {count}/10 фото</b>\n\n"

    if count < 10:
        text += "Отправьте ещё фото или нажмите <b>Далее</b>."
        if count == 9:
            text += "\n\n💡 <i>Осталось 1 место. Если загрузите ещё фото — видео будет недоступно.</i>"
    else:
        text += "🔸 Достигнут лимит. Нажмите <b>Далее</b>.\n"
        text += "<i>Видео заменит последнее фото, если захотите его добавить.</i>"

    await message.answer(text, reply_markup=get_photo_done_keyboard())


@router.message(AdCreation.photos, F.video)
async def reject_video_in_photos(message: Message, state: FSMContext):
    """Отклонение видео при загрузке фото"""
    from bot.keyboards.inline import get_photo_done_keyboard
    await message.answer(
        "⚠️ На этом шаге можно загружать только <b>фото</b>.\n"
        "Видео можно будет добавить на следующем шаге.\n\n"
        "Отправьте фото или нажмите <b>Далее</b>.",
        reply_markup=get_photo_done_keyboard()
    )


@router.callback_query(F.data == "photos_skip")
async def skip_photos(callback: CallbackQuery, state: FSMContext):
    logger.info("[PHOTOS] skip")
    await safe_clear_keyboard(callback)
    await callback.message.answer("✅ <b>Фото:</b> пропущено")
    await ask_video(callback.message, state)
    await callback.answer()


@router.callback_query(F.data == "photos_done")
async def photos_done(callback: CallbackQuery, state: FSMContext):
    logger.info("[PHOTOS] done")
    await safe_clear_keyboard(callback)
    
    data = await state.get_data()
    count = len(data.get('photos', []))
    await callback.message.answer(f"✅ <b>Фото:</b> {count} шт.")
    
    await ask_video(callback.message, state)
    await callback.answer()


# ========== ВИДЕО ==========
async def ask_video(message: Message, state: FSMContext):
    logger.info("[VIDEO] ask_video")
    await state.set_state(AdCreation.video)

    data = await state.get_data()
    photos_count = len(data.get('photos', []))

    from bot.keyboards.inline import get_video_keyboard

    if photos_count >= 10:
        text = ("🎬 <b>Шаг 10: Видео</b>\n\n"
                "⚠️ У вас загружено 10 фото. Если добавите видео — <b>последнее фото будет удалено</b>.\n\n"
                "Отправьте видео или нажмите <b>Пропустить</b>.")
    else:
        text = "🎬 <b>Шаг 10: Видео</b>\n\nОтправьте видео или нажмите <b>Пропустить</b>."

    await message.answer(text, reply_markup=get_video_keyboard())


@router.message(AdCreation.video, F.video)
async def process_video(message: Message, state: FSMContext):
    logger.info("[VIDEO] video received")

    data = await state.get_data()
    photos = data.get('photos', [])

    # Если 10 фото — удаляем последнее
    if len(photos) >= 10:
        photos = photos[:9]
        await state.update_data(photos=photos, video=message.video.file_id)
        await message.answer("✅ <b>Видео:</b> загружено\n<i>Последнее фото удалено (лимит 9 фото + 1 видео)</i>")
    else:
        await state.update_data(video=message.video.file_id)
        await message.answer("✅ <b>Видео:</b> загружено")

    await ask_price(message, state)


@router.callback_query(F.data == "video_skip")
async def skip_video(callback: CallbackQuery, state: FSMContext):
    logger.info("[VIDEO] skip")
    await safe_clear_keyboard(callback)
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
    except ValueError:
        await message.answer("❌ Введите число")
        return

    # Валидация цены
    if price < 0:
        await message.answer("❌ Цена не может быть отрицательной")
        return

    price_display = f"{int(price):,} ₽".replace(",", " ")

    # Сохраняем цену и показываем подтверждение
    await state.update_data(price=price_display)

    from bot.keyboards.inline import get_price_confirm_keyboard
    await message.answer(
        f"💰 <b>Цена:</b> {price_display}\n\nВсё верно?",
        reply_markup=get_price_confirm_keyboard(price_display)
    )


@router.callback_query(F.data == "price_confirm")
async def price_confirm(callback: CallbackQuery, state: FSMContext):
    """Подтверждение цены - переход к превью"""
    logger.info("[PRICE] confirm")
    await safe_clear_keyboard(callback)

    data = await state.get_data()
    await callback.message.answer(f"✅ <b>Цена:</b> {data.get('price')}")

    if data.get('category') in CATEGORIES_WITH_DELIVERY:
        await ask_delivery(callback.message, state)
    else:
        await ask_link_count(callback.message, state)
    await callback.answer()


@router.callback_query(F.data == "price_change")
async def price_change(callback: CallbackQuery, state: FSMContext):
    """Изменить цену - вернуться к вводу"""
    logger.info("[PRICE] change")
    await safe_clear_keyboard(callback)

    await callback.message.answer("💰 Введите новую цену:")
    await callback.answer()


@router.callback_query(F.data == "price_negotiable")
async def price_negotiable(callback: CallbackQuery, state: FSMContext):
    """Договорная цена при первом запросе"""
    logger.info("[PRICE] negotiable")
    await safe_clear_keyboard(callback)

    await state.update_data(price="Договорная")
    await callback.message.answer("✅ <b>Цена:</b> Договорная")

    data = await state.get_data()
    if data.get('category') in CATEGORIES_WITH_DELIVERY:
        await ask_delivery(callback.message, state)
    else:
        await ask_link_count(callback.message, state)
    await callback.answer()


@router.callback_query(F.data == "price_negotiable_confirm")
async def price_negotiable_confirm(callback: CallbackQuery, state: FSMContext):
    """Договорная цена при подтверждении"""
    logger.info("[PRICE] negotiable from confirm")
    await safe_clear_keyboard(callback)

    await state.update_data(price="Договорная")
    await callback.message.answer("✅ <b>Цена:</b> Договорная")

    data = await state.get_data()
    if data.get('category') in CATEGORIES_WITH_DELIVERY:
        await ask_delivery(callback.message, state)
    else:
        await ask_link_count(callback.message, state)
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
    
    await safe_clear_keyboard(callback)
    
    delivery_name = DELIVERY_TYPES.get(delivery, delivery)
    await callback.message.answer(f"✅ <b>Доставка:</b> {delivery_name}")

    await ask_link_count(callback.message, state)
    await callback.answer()


# ========== ВНЕШНИЕ ССЫЛКИ ==========
async def ask_link_count(message: Message, state: FSMContext):
    """Шаг 14: Спрашиваем сколько ссылок добавить"""
    logger.info("[LINK] ask_link_count")
    await state.set_state(AdCreation.link_count)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="1", callback_data="link_count_1"),
            InlineKeyboardButton(text="2", callback_data="link_count_2"),
            InlineKeyboardButton(text="3", callback_data="link_count_3"),
            InlineKeyboardButton(text="4", callback_data="link_count_4"),
        ],
        [InlineKeyboardButton(text="⏭ Пропустить", callback_data="link_skip")]
    ])

    await message.answer(
        "🔗 <b>Шаг 14: Внешние ссылки</b> (опционально)\n\n"
        "Сколько ссылок вы хотите добавить к объявлению?\n\n"
        "Ссылки могут вести на:\n"
        "• Геопозицию\n"
        "• Ваш сайт или Авито\n"
        "• Telegram-канал\n"
        "• Любой другой ресурс",
        reply_markup=keyboard
    )


@router.callback_query(F.data.startswith("link_count_"))
async def process_link_count(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора количества ссылок"""
    count = int(callback.data.split("_")[-1])
    logger.info(f"[LINK] count selected: {count}")

    await safe_clear_keyboard(callback)
    await state.update_data(
        link_count=count,
        current_link_index=0,
        links=[]
    )

    await ask_link_title(callback.message, state)
    await callback.answer()


@router.callback_query(F.data == "link_skip")
async def skip_link(callback: CallbackQuery, state: FSMContext):
    """Пропуск добавления ссылок"""
    logger.info("[LINK] skip")
    await safe_clear_keyboard(callback)
    await state.update_data(links=[])
    await show_preview(callback.message, state)
    await callback.answer()


async def ask_link_title(message: Message, state: FSMContext):
    """Запрос названия ссылки"""
    data = await state.get_data()
    current_index = data.get('current_link_index', 0)
    total_count = data.get('link_count', 1)

    logger.info(f"[LINK] ask_link_title ({current_index + 1}/{total_count})")
    await state.set_state(AdCreation.link_title)

    await message.answer(
        f"🔗 <b>Ссылка {current_index + 1} из {total_count}</b>\n\n"
        "Введите <b>название ссылки</b>, например:\n"
        "• Геопозиция\n"
        "• Моё объявление на Авито\n"
        "• Мой сайт"
    )


@router.message(AdCreation.link_title)
async def process_link_title(message: Message, state: FSMContext):
    """Обработка названия ссылки"""
    logger.info(f"[LINK] title: {message.text[:30] if message.text else 'None'}")

    if not message.text:
        await message.answer("❌ Введите название ссылки")
        return

    link_title = message.text.strip()

    # Проверка длины (максимум 30 символов)
    if len(link_title) > 30:
        await message.answer(
            f"❌ Название слишком длинное ({len(link_title)} симв.)\n\n"
            "Максимум 30 символов. Сократите название."
        )
        return

    # LLM проверка с контекстом что это заголовок ссылки (мягкая модерация)
    data = await state.get_data()
    llm_result = await validate_content_with_llm(
        link_title,
        data.get('category', ''),
        data.get('subcategory', ''),
        content_type="link_title"
    )

    if not llm_result.is_valid:
        await message.answer("❌ Название содержит недопустимые слова. Введите другое.")
        return

    # Сохраняем временно название текущей ссылки
    await state.update_data(current_link_title=link_title)
    await message.answer(f"✅ <b>Название:</b> {link_title}")
    await ask_link_url(message, state)


async def ask_link_url(message: Message, state: FSMContext):
    """Запрос URL ссылки"""
    data = await state.get_data()
    current_index = data.get('current_link_index', 0)
    total_count = data.get('link_count', 1)

    logger.info(f"[LINK] ask_link_url ({current_index + 1}/{total_count})")
    await state.set_state(AdCreation.link_url)

    await message.answer(
        f"🔗 Теперь введите <b>ссылку</b> (URL) для «{data.get('current_link_title', 'Ссылка')}»:\n\n"
        "Например:\n"
        "• https://yandex.ru/maps/...\n"
        "• avito.ru/...\n"
        "• t.me/channel_name\n"
        "• @channel_name"
    )


@router.message(AdCreation.link_url)
async def process_link_url(message: Message, state: FSMContext):
    """Обработка URL ссылки"""
    logger.info(f"[LINK] url: {message.text[:50] if message.text else 'None'}")

    if not message.text:
        await message.answer("❌ Введите ссылку")
        return

    import re
    url = message.text.strip()

    # Обработка Telegram ссылок (@username)
    if url.startswith('@'):
        username = url[1:]  # убираем @
        if re.match(r'^[a-zA-Z][a-zA-Z0-9_]{3,30}$', username):
            url = f"https://t.me/{username}"
        else:
            await message.answer(
                "❌ Неверный формат Telegram ссылки.\n\n"
                "Имя канала/пользователя должно содержать 4-31 символ (буквы, цифры, _)"
            )
            return
    # Обработка Telegram ссылок (t.me/... или telegram.me/...)
    elif url.startswith(('t.me/', 'telegram.me/')):
        url = f"https://{url}"
    # Автодобавление https:// если нет протокола
    elif not url.startswith(('http://', 'https://')):
        # Проверяем что это похоже на домен (минимум x.xx)
        if re.match(r'^[a-zA-Z0-9][a-zA-Z0-9.-]*\.[a-zA-Z]{2,}', url):
            url = f"https://{url}"
        else:
            await message.answer(
                "❌ Неверный формат ссылки.\n\n"
                "Введите корректную ссылку, например:\n"
                "• example.com\n"
                "• t.me/channel\n"
                "• @channel_name"
            )
            return

    # Финальная валидация URL
    url_pattern = r'^https?://[^\s<>"{}|\\^`\[\]]+$'
    if not re.match(url_pattern, url):
        await message.answer("❌ Неверный формат ссылки.")
        return

    if len(url) > 500:
        await message.answer("❌ Ссылка слишком длинная (максимум 500 символов)")
        return

    # Проверка ссылки на запрещённый контент через LLM
    data = await state.get_data()
    link_title = data.get('current_link_title', 'Ссылка')

    llm_result = await validate_content_with_llm(
        f"Ссылка с названием '{link_title}' ведёт на: {url}",
        data.get('category', ''),
        data.get('subcategory', ''),
        content_type="link_url"
    )

    if not llm_result.is_valid:
        await message.answer(get_rejection_message(llm_result))
        return

    # Добавляем ссылку в массив
    links = data.get('links', [])
    links.append({'title': link_title, 'url': url})

    current_index = data.get('current_link_index', 0) + 1
    total_count = data.get('link_count', 1)

    await state.update_data(
        links=links,
        current_link_index=current_index,
        current_link_title=None  # очищаем временное название
    )

    await message.answer(f"✅ <b>Ссылка добавлена:</b> <a href=\"{url}\">{link_title}</a>")

    # Если ещё не все ссылки введены - продолжаем
    if current_index < total_count:
        await ask_link_title(message, state)
    else:
        # Все ссылки введены - переходим к превью
        await show_preview(message, state)


# ========== ПРЕВЬЮ ==========
async def show_preview(message: Message, state: FSMContext):
    logger.info("[PREVIEW] show_preview")

    # Показываем сообщение о подготовке превью
    await message.answer("⏳ Подготавливаю превью объявления...")

    data = await state.get_data()
    await state.set_state(AdCreation.confirm)

    description = data.get('description') or ''

    # Формируем блок ссылок если есть
    link_block = ""
    links = data.get('links', [])
    if links:
        link_lines = [f"🔗 <a href=\"{link['url']}\">{link['title']}</a>" for link in links]
        link_block = "\n" + "\n".join(link_lines)

    text = f"""📢 <b>Превью</b>

📍 {REGIONS.get(data.get('region', ''), '')}
📂 {CATEGORIES.get(data.get('category', ''), '')}
💼 {DEAL_TYPES.get(data.get('deal_type', ''), '')}

<b>{data.get('title', '')}</b>

{description[:200]}{'...' if len(description) > 200 else ''}

💰 {data.get('price', 'Не указана')}{link_block}
📸 {len(data.get('photos', []))} фото

<b>Опубликовать?</b>"""

    from bot.keyboards.inline import get_confirm_with_edit_keyboard

    try:
        await message.answer(text, reply_markup=get_confirm_with_edit_keyboard())
    except TelegramNetworkError as e:
        logger.error(f"[PREVIEW] Сетевая ошибка: {e}")
        await message.answer("⚠️ Ошибка сети. Попробуйте ещё раз.")


# ========== ПУБЛИКАЦИЯ ==========
@router.callback_query(F.data == "confirm_publish")
async def confirm_ad(callback: CallbackQuery, state: FSMContext):
    logger.info("[PUBLISH] confirm_ad")

    data = await state.get_data()

    await safe_clear_keyboard(callback)

    await callback.answer()

    # Показываем спиннер
    spinner_msg = await callback.message.answer("⏳ <b>Проверяю объявление...</b>\n\nПожалуйста, подождите")

    # Проверяем фото на запрещённый текст через OCR
    photos = data.get('photos', [])
    if photos:
        photos_ok, photos_error = await check_photos_for_forbidden_text(
            bot=callback.message.bot,
            photo_ids=photos,
            category=data.get('category'),
            subcategory=data.get('subcategory')
        )
        if not photos_ok:
            await spinner_msg.edit_text(
                f"❌ <b>Объявление отклонено</b>\n\n{photos_error}\n\n"
                "Пожалуйста, замените фото и попробуйте снова."
            )
            # Возвращаем в состояние редактирования
            await state.set_state(AdCreation.confirm)
            from bot.keyboards.inline import get_confirm_with_edit_keyboard
            await callback.message.answer(
                "Вы можете отредактировать объявление:",
                reply_markup=get_confirm_with_edit_keyboard()
            )
            return

    # Обновляем спиннер
    await spinner_msg.edit_text("⏳ <b>Публикую объявление...</b>\n\nПожалуйста, подождите")

    try:
        bot_info = await callback.message.bot.get_me()

        async with get_db_session() as session:
            price_str = data.get('price', 'Договорная')
            price_value = None
            if price_str != 'Договорная':
                try:
                    price_value = float(price_str.replace(' ₽', '').replace(' ', ''))
                except (ValueError, AttributeError):
                    logger.warning(f"Не удалось распарсить цену: {price_str}")
            
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
                links=data.get('links', []),
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

        # Формируем сообщение с категорией и ссылками
        category = data.get('category', '')
        category_name = CATEGORIES.get(category, category)
        region = data.get('region', '')

        # Получаем конфигурацию каналов
        channel_config = CHANNELS_CONFIG.get(region, {})
        category_channel = channel_config.get('categories', {}).get(category, '')
        main_channel = channel_config.get('main', '')

        result_text = f"✅ <b>Опубликовано!</b>\n\n"
        result_text += f"🆔 ID: <code>{ad_id}</code>\n"

        # Ссылка на канал категории
        if category_channel and category_channel in channel_ids:
            msg_ids = channel_ids[category_channel]
            msg_id = msg_ids[0] if isinstance(msg_ids, list) else msg_ids
            channel_username = category_channel.replace("@", "")
            ad_link = f"https://t.me/{channel_username}/{msg_id}"
            result_text += f"📂 Категория: <a href=\"{ad_link}\">{category_name}</a>\n"
        else:
            result_text += f"📂 Категория: {category_name}\n"

        # Ссылка на общий канал
        if main_channel and main_channel in channel_ids:
            msg_ids = channel_ids[main_channel]
            msg_id = msg_ids[0] if isinstance(msg_ids, list) else msg_ids
            channel_username = main_channel.replace("@", "")
            ad_link = f"https://t.me/{channel_username}/{msg_id}"
            result_text += f"📢 Общий канал: <a href=\"{ad_link}\">{main_channel}</a>"

        # Заменяем спиннер на результат
        try:
            await spinner_msg.edit_text(result_text, disable_web_page_preview=True)
        except TelegramAPIError:
            await callback.message.answer(result_text, disable_web_page_preview=True)

    except Exception as e:
        logger.error(f"[PUBLISH] Ошибка: {e}", exc_info=True)
        # Заменяем спиннер на ошибку
        try:
            await spinner_msg.edit_text("❌ Ошибка публикации. Попробуйте позже.")
        except TelegramAPIError:
            await callback.message.answer("❌ Ошибка. Попробуйте позже.")

    await state.clear()


@router.callback_query(F.data == "cancel_ad")
async def cancel_ad(callback: CallbackQuery, state: FSMContext):
    logger.info("[CANCEL] cancel_ad")
    await safe_clear_keyboard(callback)
    await state.clear()
    await callback.message.answer("❌ Отменено.")
    await callback.answer()


@router.callback_query(F.data == "edit_ad")
async def edit_ad_preview(callback: CallbackQuery, state: FSMContext):
    logger.info("[EDIT] edit_ad")
    await safe_clear_keyboard(callback)
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

    # ===== Формируем блок внешних ссылок =====
    external_link = ""
    links = data.get('links', [])
    if links:
        link_lines = [f"🔗 <a href=\"{link['url']}\">{link['title']}</a>" for link in links]
        external_link = "\n" + "\n".join(link_lines)

    # ===== Текст объявления с ссылками =====
    text = f"""<b>{data.get('title', '')}</b>

{data.get('description', '')}

💰 {data.get('price', 'Не указана')}{external_link}

{hashtags_text}

━━━━━━━━━━━━━━━
😎 <a href="tg://user?id={ad.user_id}">Написать продавцу</a>
👾 <a href="https://t.me/{bot_info.username}?start=profile_{ad.user_id}">Профиль продавца</a>
⭐ <a href="https://t.me/{bot_info.username}?start=fav_{ad.id}">В избранное</a>
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
        # Retry для каждого канала (2 попытки)
        for attempt in range(2):
            try:
                if photos:
                    if len(photos) == 1:
                        msg = await bot.send_photo(chat_id=channel, photo=photos[0], caption=text)
                        channel_ids[channel] = [msg.message_id]
                        logger.info(f"[CHANNEL] опубликовано в {channel}, msg_id={msg.message_id}")
                    else:
                        media = [InputMediaPhoto(media=photos[0], caption=text)]
                        for p in photos[1:10]:
                            media.append(InputMediaPhoto(media=p))
                        msgs = await bot.send_media_group(chat_id=channel, media=media)
                        if msgs:
                            # Сохраняем ВСЕ message_id из media_group
                            msg_ids = [m.message_id for m in msgs]
                            channel_ids[channel] = msg_ids
                            logger.info(f"[CHANNEL] опубликовано в {channel}, msg_ids={msg_ids}")
                elif video:
                    msg = await bot.send_video(chat_id=channel, video=video, caption=text)
                    channel_ids[channel] = [msg.message_id]
                    logger.info(f"[CHANNEL] опубликовано в {channel}, msg_id={msg.message_id}")
                else:
                    msg = await bot.send_message(chat_id=channel, text=text, disable_web_page_preview=True)
                    channel_ids[channel] = [msg.message_id]
                    logger.info(f"[CHANNEL] опубликовано в {channel}, msg_id={msg.message_id}")
                break  # Успех

            except TelegramNetworkError as e:
                if attempt < 1:
                    logger.warning(f"[CHANNEL] {channel} ошибка (попытка {attempt+1}), повтор: {e}")
                    await asyncio.sleep(0.5)
                else:
                    logger.error(f"[CHANNEL] ошибка {channel}: {e}")
            except Exception as e:
                logger.error(f"[CHANNEL] ошибка {channel}: {e}")
                break

    return channel_ids


@router.callback_query(F.data == "cancel")
async def cancel_creation(callback: CallbackQuery, state: FSMContext):
    logger.info("[CANCEL] cancel")
    await state.clear()
    await safe_clear_keyboard(callback)
    await callback.message.answer("❌ Отменено.")
    await callback.answer()


# ========== FALLBACK-ОБРАБОТЧИКИ ==========
# Обрабатывают текст в состояниях, где ожидается нажатие кнопки

@router.message(AdCreation.region)
async def fallback_region(message: Message, state: FSMContext):
    """Пользователь ввёл текст вместо выбора региона"""
    logger.info(f"[FALLBACK] region, text={message.text}, user={message.from_user.id}")
    await message.answer("👆 Пожалуйста, выберите регион из списка выше")


@router.message(AdCreation.city)
async def fallback_city(message: Message, state: FSMContext):
    """Пользователь ввёл текст вместо выбора города"""
    logger.info(f"[FALLBACK] city, text={message.text}, user={message.from_user.id}")
    await message.answer("👆 Пожалуйста, выберите город из списка выше")


@router.message(AdCreation.category)
async def fallback_category(message: Message, state: FSMContext):
    """Пользователь ввёл текст вместо выбора категории"""
    logger.info(f"[FALLBACK] category, text={message.text}, user={message.from_user.id}")
    await message.answer("👆 Пожалуйста, выберите категорию из списка выше")


@router.message(AdCreation.subcategory)
async def fallback_subcategory(message: Message, state: FSMContext):
    """Пользователь ввёл текст вместо выбора рубрики"""
    logger.info(f"[FALLBACK] subcategory, text={message.text}, user={message.from_user.id}")
    await message.answer("👆 Пожалуйста, выберите рубрику из списка выше")


@router.message(AdCreation.deal_type)
async def fallback_deal_type(message: Message, state: FSMContext):
    """Пользователь ввёл текст вместо выбора типа сделки"""
    logger.info(f"[FALLBACK] deal_type, text={message.text}, user={message.from_user.id}")
    await message.answer("👆 Пожалуйста, выберите тип сделки из списка выше")


@router.message(AdCreation.condition)
async def fallback_condition(message: Message, state: FSMContext):
    """Пользователь ввёл текст вместо выбора состояния"""
    logger.info(f"[FALLBACK] condition, text={message.text}, user={message.from_user.id}")
    await message.answer("👆 Пожалуйста, выберите состояние из списка выше")


@router.message(AdCreation.delivery)
async def fallback_delivery(message: Message, state: FSMContext):
    """Пользователь ввёл текст вместо выбора доставки"""
    logger.info(f"[FALLBACK] delivery, text={message.text}, user={message.from_user.id}")
    await message.answer("👆 Пожалуйста, выберите способ доставки из списка выше")


@router.message(AdCreation.confirm)
async def fallback_confirm(message: Message, state: FSMContext):
    """Пользователь ввёл текст вместо подтверждения"""
    logger.info(f"[FALLBACK] confirm, text={message.text}, user={message.from_user.id}")
    await message.answer("👆 Пожалуйста, нажмите кнопку для подтверждения или отмены")


@router.message(AdCreation.photos, F.text)
async def fallback_photos(message: Message, state: FSMContext):
    """Пользователь ввёл текст вместо отправки фото"""
    logger.info(f"[FALLBACK] photos, text={message.text}, user={message.from_user.id}")
    await message.answer("📸 Отправьте фото или нажмите кнопку ниже")


@router.message(AdCreation.video, F.text)
async def fallback_video(message: Message, state: FSMContext):
    """Пользователь ввёл текст вместо отправки видео"""
    logger.info(f"[FALLBACK] video, text={message.text}, user={message.from_user.id}")
    await message.answer("🎬 Отправьте видео или нажмите кнопку ниже")
