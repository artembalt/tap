# bot/handlers/ad_management.py
"""Обработчик управления объявлениями - с пагинацией по 50"""

import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramAPIError

from aiogram import Bot

from bot.database.queries import AdQueries
from bot.keyboards.inline import get_back_keyboard
from bot.config import settings
from bot.utils.content_filter import (
    validate_content, validate_content_with_llm, get_rejection_message
)
from shared.regions_config import REGIONS, CATEGORIES, CHANNELS_CONFIG, get_city_hashtag, get_subcategory_hashtag

router = Router(name='ad_management')
logger = logging.getLogger(__name__)


async def update_ad_in_channels(ad_id: str, bot: Bot) -> tuple[int, int]:
    """
    Обновить объявление во всех каналах где оно опубликовано.

    Returns:
        (updated_count, error_count)
    """
    from bot.database.connection import get_db_session
    from bot.database.models import Ad
    from sqlalchemy import select
    import uuid

    try:
        async with get_db_session() as session:
            result = await session.execute(
                select(Ad).where(Ad.id == uuid.UUID(ad_id))
            )
            ad = result.scalar_one_or_none()

            if not ad or not ad.channel_message_ids:
                return 0, 0

            # Получаем username бота
            bot_info = await bot.get_me()
            bot_username = bot_info.username

            # Формируем хэштеги
            hashtags = []
            if ad.subcategory:
                hashtags.append(get_subcategory_hashtag(ad.subcategory))
            if ad.category and ad.region:
                category_name = CATEGORIES.get(ad.category, ad.category)
                region_name = REGIONS.get(ad.region, ad.region)
                cat_clean = category_name.split()[-1] if ' ' in category_name else category_name
                reg_clean = region_name.replace(' ', '_').replace('-', '_')
                hashtags.append(f"#{cat_clean}_{reg_clean}")
            if ad.city:
                hashtags.append(get_city_hashtag(ad.city))

            hashtags_text = " ".join(hashtags) if hashtags else ""

            # Формируем цену
            if ad.price:
                price_text = f"{int(ad.price):,}".replace(",", " ") + f" {ad.currency or 'RUB'}"
            else:
                pf = ad.premium_features or {}
                price_text = pf.get('price_text', 'Не указана')

            # Формируем текст объявления
            new_text = f"""<b>{ad.title}</b>

{ad.description}

💰 {price_text}

{hashtags_text}

━━━━━━━━━━━━━━━
😎 <a href="tg://user?id={ad.user_id}">Написать продавцу</a>
👾 <a href="https://t.me/{bot_username}?start=profile_{ad.user_id}">Профиль продавца</a>
⭐ <a href="https://t.me/{bot_username}?start=fav_{ad.id}">В избранное</a>
📢 <a href="https://t.me/{bot_username}">Разместить объявление</a>"""

            updated = 0
            errors = 0

            # Обновляем в каждом канале
            for channel, msg_ids in ad.channel_message_ids.items():
                # Поддержка старого формата (int) и нового (list)
                if isinstance(msg_ids, list):
                    msg_id = msg_ids[0] if msg_ids else None
                else:
                    msg_id = msg_ids

                if not msg_id:
                    continue

                try:
                    if ad.photos or ad.video:
                        # Для media_group редактируем только первое сообщение (с caption)
                        await bot.edit_message_caption(
                            chat_id=channel,
                            message_id=msg_id,
                            caption=new_text,
                            parse_mode="HTML"
                        )
                    else:
                        await bot.edit_message_text(
                            chat_id=channel,
                            message_id=msg_id,
                            text=new_text,
                            parse_mode="HTML",
                            disable_web_page_preview=True
                        )
                    updated += 1
                    logger.info(f"[EDIT] Обновлено в канале {channel}")
                except TelegramAPIError as e:
                    error_msg = str(e).lower()
                    if "message is not modified" in error_msg:
                        updated += 1  # Текст уже актуален
                    else:
                        logger.error(f"[EDIT] Ошибка обновления в {channel}: {e}")
                        errors += 1
                except Exception as e:
                    logger.error(f"[EDIT] Неожиданная ошибка в {channel}: {e}")
                    errors += 1

            return updated, errors

    except Exception as e:
        logger.error(f"[EDIT] Ошибка обновления в каналах: {e}")
        return 0, 1

# Количество объявлений на странице
ADS_PER_PAGE = 25


class EditAdStates(StatesGroup):
    """Состояния для редактирования объявления"""
    waiting_for_new_title = State()
    waiting_for_new_description = State()
    waiting_for_new_price = State()
    waiting_for_new_media = State()  # Для замены фото/видео


def get_my_ads_keyboard(offset: int, total: int, status: str = None) -> InlineKeyboardMarkup:
    """Клавиатура для пагинации объявлений с фильтром по статусу"""
    buttons = []

    # Навигация по страницам
    nav_row = []

    # Формат callback_data: my_ads_page_{status}_{offset}
    status_part = f"{status}_" if status else ""

    # Кнопка "Назад" на предыдущую страницу
    if offset > 0:
        prev_offset = max(0, offset - ADS_PER_PAGE)
        nav_row.append(InlineKeyboardButton(
            text="◀️ Назад",
            callback_data=f"my_ads_page_{status_part}{prev_offset}"
        ))

    # Кнопка "Далее" если есть ещё объявления
    if offset + ADS_PER_PAGE < total:
        nav_row.append(InlineKeyboardButton(
            text="Далее ▶️",
            callback_data=f"my_ads_page_{status_part}{offset + ADS_PER_PAGE}"
        ))

    if nav_row:
        buttons.append(nav_row)

    # Кнопка возврата к категориям
    buttons.append([
        InlineKeyboardButton(text="📋 К категориям", callback_data="my_ads")
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


# =============================================================================
# ПРОСМОТР СПИСКА СВОИХ ОБЪЯВЛЕНИЙ
# =============================================================================

# Маппинг статусов для меню
ADS_CATEGORIES = {
    "active": {"name": "Активные", "emoji": "✅", "status": "active"},
    "inactive": {"name": "Неактивные", "emoji": "💤", "status": "inactive"},
    "pending": {"name": "На модерации", "emoji": "⏳", "status": "pending"},
    "deleted": {"name": "Удалённые", "emoji": "🗑", "status": "deleted"},
}


@router.message(Command("my_ads"))
@router.message(F.text == "📋 Мои объявления")
async def my_ads(message: Message):
    """Показать меню категорий объявлений"""
    logger.info(f"my_ads вызван, user={message.from_user.id}")
    await show_ads_categories_menu(message, message.from_user.id)


@router.callback_query(F.data == "my_ads")
async def callback_my_ads(callback: CallbackQuery):
    """Показать меню категорий объявлений (через callback)"""
    logger.info(f"callback_my_ads вызван, user={callback.from_user.id}")
    await show_ads_categories_menu(callback.message, callback.from_user.id, edit=True)
    await callback.answer()


@router.callback_query(F.data.startswith("my_ads_cat_"))
async def callback_my_ads_category(callback: CallbackQuery):
    """Показать объявления выбранной категории"""
    category = callback.data.replace("my_ads_cat_", "")
    logger.info(f"my_ads_category вызван, user={callback.from_user.id}, category={category}")

    if category not in ADS_CATEGORIES:
        await callback.answer("❌ Неизвестная категория")
        return

    status = ADS_CATEGORIES[category]["status"]
    await show_user_ads(callback.message, callback.from_user.id, offset=0, status=status, edit=True)
    await callback.answer()


@router.callback_query(F.data.startswith("my_ads_page_"))
async def callback_my_ads_page(callback: CallbackQuery):
    """Показать следующую страницу объявлений"""
    # Формат: my_ads_page_{status}_{offset}
    parts = callback.data.replace("my_ads_page_", "").split("_")
    if len(parts) == 2:
        status, offset = parts[0], int(parts[1])
    else:
        status, offset = None, int(parts[0])

    logger.info(f"my_ads_page вызван, user={callback.from_user.id}, status={status}, offset={offset}")
    await show_user_ads(callback.message, callback.from_user.id, offset=offset, status=status, edit=True)
    await callback.answer()


async def show_ads_categories_menu(message: Message, user_id: int, edit: bool = False):
    """Показать меню категорий объявлений с количеством"""
    try:
        counts = await AdQueries.get_user_ads_counts_by_status(user_id)
    except Exception as e:
        logger.error(f"Ошибка получения счётчиков: {e}")
        counts = {"active": 0, "inactive": 0, "pending": 0, "deleted": 0}

    total = sum(counts.values())

    text = (
        f"📋 <b>Мои объявления</b>\n\n"
        f"Всего: {total}\n\n"
        f"Выберите категорию:"
    )

    # Формируем кнопки с количеством
    buttons = []
    for key, cat in ADS_CATEGORIES.items():
        count = counts.get(cat["status"], 0)
        btn_text = f"{cat['emoji']} {cat['name']} ({count})"
        buttons.append([InlineKeyboardButton(text=btn_text, callback_data=f"my_ads_cat_{key}")])

    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")])

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    if edit:
        try:
            await message.edit_text(text, reply_markup=keyboard)
        except TelegramAPIError:
            await message.answer(text, reply_markup=keyboard)
    else:
        await message.answer(text, reply_markup=keyboard)


async def show_user_ads(
    message: Message,
    user_id: int,
    offset: int = 0,
    status: str = None,
    edit: bool = False
):
    """
    Показать объявления пользователя с пагинацией по 50.

    Args:
        status: Фильтр по статусу (active, inactive, pending, deleted)
    """
    try:
        # Получаем общее количество объявлений
        total_count = await AdQueries.get_user_ads_count(user_id, status=status)

        # Получаем объявления для текущей страницы
        ads = await AdQueries.get_user_ads(user_id, status=status, limit=ADS_PER_PAGE, offset=offset)
    except Exception as e:
        logger.error(f"Ошибка получения объявлений: {e}")
        text = "❌ Ошибка загрузки объявлений. Попробуйте позже."
        back_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📋 К категориям", callback_data="my_ads")]
        ])
        if edit:
            try:
                await message.edit_text(text, reply_markup=back_kb)
            except TelegramAPIError:
                await message.answer(text, reply_markup=back_kb)
        else:
            await message.answer(text, reply_markup=back_kb)
        return

    # Получаем название категории
    category_info = ADS_CATEGORIES.get(status, {})
    category_name = category_info.get("name", "Объявления")
    category_emoji = category_info.get("emoji", "📋")

    if not ads and offset == 0:
        text = (
            f"{category_emoji} <b>{category_name}</b>\n\n"
            f"В этой категории пока нет объявлений."
        )

        back_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📋 К категориям", callback_data="my_ads")]
        ])

        if edit:
            if message.photo:
                await message.delete()
                await message.answer(text, reply_markup=back_kb)
            else:
                try:
                    await message.edit_text(text, reply_markup=back_kb)
                except TelegramAPIError:
                    await message.answer(text, reply_markup=back_kb)
        else:
            await message.answer(text, reply_markup=back_kb)
        return

    # Формируем заголовок с информацией о пагинации
    start_num = offset + 1
    end_num = offset + len(ads)

    if total_count > ADS_PER_PAGE:
        text = f"{category_emoji} <b>{category_name}</b> ({start_num}-{end_num} из {total_count})\n\n"
    else:
        text = f"{category_emoji} <b>{category_name}</b> ({total_count})\n\n"

    bot_username = settings.BOT_USERNAME

    for i, ad in enumerate(ads, start_num):
        status_emoji = {
            "active": "✅",
            "pending": "⏳",
            "inactive": "💤",  # Неактивное (срок истёк)
            "archived": "📦",
            "rejected": "❌",
            "deleted": "🗑",
            "banned": "🚫"
        }.get(ad.status, "❓")

        # Формируем цену
        if ad.price:
            price_text = f"{int(ad.price):,}".replace(",", " ")
        else:
            pf = ad.premium_features or {}
            price_text = pf.get('price_text', 'Договорная')

        title_display = ad.title[:40] + "..." if len(ad.title) > 40 else ad.title

        # Ссылки на действия (deep links)
        edit_link = f"https://t.me/{bot_username}?start=edit_{ad.id}"
        delete_link = f"https://t.me/{bot_username}?start=del_{ad.id}"
        republish_link = f"https://t.me/{bot_username}?start=republish_{ad.id}"
        remove_link = f"https://t.me/{bot_username}?start=remove_{ad.id}"
        view_link = f"https://t.me/{bot_username}?start=view_{ad.id}"

        # Заголовок - зависит от статуса
        if ad.status == "active":
            # Активные: ссылка на канал
            channel_link = get_channel_link(ad)
            if channel_link:
                text += f"{i}. {status_emoji} <a href=\"{channel_link}\">{title_display}</a>\n"
            else:
                text += f"{i}. {status_emoji} {title_display}\n"
        elif ad.status in ["inactive", "pending", "deleted"]:
            # Неактивные, На модерации, Удалённые: ссылка на просмотр в боте
            text += f"{i}. {status_emoji} <a href=\"{view_link}\">{title_display}</a>\n"
        else:
            text += f"{i}. {status_emoji} {title_display}\n"

        # Цена
        text += f"   ₽ {price_text}\n"

        # Разные кнопки в зависимости от статуса
        if ad.status == "active":
            # Активные: Изменить, Удалить
            text += f"   <a href=\"{edit_link}\">✏️ Изменить</a>  <a href=\"{delete_link}\">🗑 Удалить</a>\n\n"
        elif ad.status == "inactive":
            # Неактивные: Изменить, Удалить
            text += f"   <a href=\"{edit_link}\">✏️ Изменить</a>  <a href=\"{delete_link}\">🗑 Удалить</a>\n\n"
        elif ad.status == "pending":
            # На модерации: Изменить, Опубликовать
            text += f"   <a href=\"{edit_link}\">✏️ Изменить</a>  <a href=\"{republish_link}\">🔄 Опубликовать</a>\n\n"
        elif ad.status == "deleted":
            # Удалённые: Опубликовать, Удалить
            text += f"   <a href=\"{republish_link}\">🔄 Опубликовать</a>  <a href=\"{remove_link}\">🗑 Удалить</a>\n\n"
        else:
            # Прочие: Изменить, Удалить
            text += f"   <a href=\"{edit_link}\">✏️ Изменить</a>  <a href=\"{delete_link}\">🗑 Удалить</a>\n\n"

    # Клавиатура с пагинацией
    keyboard = get_my_ads_keyboard(offset, total_count, status=status)

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
    Получить ссылку на объявление в канале рубрики (категории).
    Формат: https://t.me/channel_username/message_id

    Приоритет: канал категории > первый доступный канал
    """
    channel_message_ids = ad.channel_message_ids or {}

    if not channel_message_ids:
        return None

    def extract_msg_id(msg_ids):
        """Извлечь первый message_id (поддержка старого и нового формата)"""
        if isinstance(msg_ids, list):
            return msg_ids[0] if msg_ids else None
        return msg_ids

    # Сначала пытаемся найти канал категории
    region_config = CHANNELS_CONFIG.get(ad.region, {})
    category_channels = region_config.get("categories", {})
    category_channel = category_channels.get(ad.category, "")

    if category_channel and category_channel in channel_message_ids:
        msg_id = extract_msg_id(channel_message_ids[category_channel])
        if msg_id:
            channel_clean = category_channel.lstrip('@')
            return f"https://t.me/{channel_clean}/{msg_id}"

    # Если канал категории не найден - берём первый доступный
    for channel_username, msg_ids in channel_message_ids.items():
        if channel_username and msg_ids:
            message_id = extract_msg_id(msg_ids)
            if message_id:
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


# =============================================================================
# РЕДАКТИРОВАНИЕ ОБЪЯВЛЕНИЯ
# =============================================================================

from bot.database.connection import get_db_session
from bot.database.models import Ad


@router.callback_query(F.data.startswith("edit_title_"))
async def start_edit_title(callback: CallbackQuery, state: FSMContext):
    """Начать редактирование заголовка"""
    ad_id = callback.data.replace("edit_title_", "")

    # Сохраняем ad_id в состоянии
    await state.update_data(edit_ad_id=ad_id)
    await state.set_state(EditAdStates.waiting_for_new_title)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="my_ads")]
    ])

    await callback.message.edit_text(
        "✏️ <b>Введите новый заголовок:</b>\n\n"
        "(от 5 до 100 символов)",
        reply_markup=keyboard
    )
    await callback.answer()


@router.callback_query(F.data.startswith("edit_desc_"))
async def start_edit_description(callback: CallbackQuery, state: FSMContext):
    """Начать редактирование описания"""
    ad_id = callback.data.replace("edit_desc_", "")

    await state.update_data(edit_ad_id=ad_id)
    await state.set_state(EditAdStates.waiting_for_new_description)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="my_ads")]
    ])

    await callback.message.edit_text(
        "📝 <b>Введите новое описание:</b>\n\n"
        "(от 10 до 2000 символов)",
        reply_markup=keyboard
    )
    await callback.answer()


@router.callback_query(F.data.startswith("edit_price_"))
async def start_edit_price(callback: CallbackQuery, state: FSMContext):
    """Начать редактирование цены"""
    ad_id = callback.data.replace("edit_price_", "")

    await state.update_data(edit_ad_id=ad_id)
    await state.set_state(EditAdStates.waiting_for_new_price)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="my_ads")]
    ])

    await callback.message.edit_text(
        "💰 <b>Введите новую цену:</b>\n\n"
        "Введите число (например: 15000) или текст (например: Договорная)",
        reply_markup=keyboard
    )
    await callback.answer()


@router.callback_query(F.data.startswith("edit_media_"))
async def start_edit_media(callback: CallbackQuery, state: FSMContext):
    """Начать замену фото/видео"""
    ad_id = callback.data.replace("edit_media_", "")

    await state.update_data(edit_ad_id=ad_id, new_photos=[], new_video=None)
    await state.set_state(EditAdStates.waiting_for_new_media)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Сохранить медиа", callback_data=f"save_media_{ad_id}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="my_ads")]
    ])

    await callback.message.answer(
        "📷 <b>Замена фото/видео</b>\n\n"
        "Отправьте новые фото (до 10 шт.) или одно видео.\n\n"
        "⚠️ Старые медиа будут заменены новыми.\n\n"
        "После загрузки всех медиа нажмите «✅ Сохранить медиа»",
        reply_markup=keyboard
    )
    await callback.answer()


@router.message(EditAdStates.waiting_for_new_media, F.photo)
async def process_new_photo(message: Message, state: FSMContext):
    """Обработка нового фото"""
    data = await state.get_data()
    photos = data.get("new_photos", [])

    if len(photos) >= 10:
        await message.answer("⚠️ Максимум 10 фото. Нажмите «✅ Сохранить медиа» для сохранения.")
        return

    # Берём фото максимального размера
    photo_id = message.photo[-1].file_id
    photos.append(photo_id)
    await state.update_data(new_photos=photos, new_video=None)

    ad_id = data.get("edit_ad_id")
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Сохранить медиа", callback_data=f"save_media_{ad_id}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="my_ads")]
    ])

    await message.answer(
        f"✅ Фото добавлено ({len(photos)}/10)\n\n"
        f"Отправьте ещё фото или нажмите «✅ Сохранить медиа»",
        reply_markup=keyboard
    )


@router.message(EditAdStates.waiting_for_new_media, F.video)
async def process_new_video(message: Message, state: FSMContext):
    """Обработка нового видео"""
    video_id = message.video.file_id
    await state.update_data(new_video=video_id, new_photos=[])

    data = await state.get_data()
    ad_id = data.get("edit_ad_id")

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Сохранить медиа", callback_data=f"save_media_{ad_id}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="my_ads")]
    ])

    await message.answer(
        "✅ Видео добавлено\n\n"
        "Нажмите «✅ Сохранить медиа» для сохранения",
        reply_markup=keyboard
    )


@router.callback_query(F.data.startswith("save_media_"))
async def save_new_media(callback: CallbackQuery, state: FSMContext):
    """Сохранить новые медиа"""
    ad_id = callback.data.replace("save_media_", "")
    user_id = callback.from_user.id

    data = await state.get_data()
    new_photos = data.get("new_photos", [])
    new_video = data.get("new_video")

    if not new_photos and not new_video:
        await callback.answer("❌ Сначала отправьте фото или видео", show_alert=True)
        return

    try:
        async with get_db_session() as session:
            from sqlalchemy import update
            import uuid

            # Обновляем медиа в БД
            values = {}
            if new_photos:
                values["photos"] = new_photos
                values["video"] = None
            elif new_video:
                values["video"] = new_video
                values["photos"] = []

            stmt = update(Ad).where(Ad.id == uuid.UUID(ad_id)).values(**values)
            await session.execute(stmt)
            await session.commit()

        await state.clear()

        media_type = "фото" if new_photos else "видео"
        count = len(new_photos) if new_photos else 1

        await callback.answer(f"✅ Медиа обновлены ({count} {media_type})", show_alert=False)
        await callback.message.edit_text(
            f"✅ <b>Медиа обновлены!</b>\n\n"
            f"Загружено: {count} {media_type}\n\n"
            f"⚠️ Изменения применены в базе данных.\n"
            f"Для обновления в каналах переопубликуйте объявление.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📋 К объявлениям", callback_data="my_ads")]
            ])
        )

    except Exception as e:
        logger.error(f"Ошибка сохранения медиа: {e}")
        await state.clear()
        await callback.answer("❌ Ошибка сохранения", show_alert=True)


@router.message(EditAdStates.waiting_for_new_title)
async def process_new_title(message: Message, state: FSMContext):
    """Обработка нового заголовка"""
    new_title = message.text.strip()

    if len(new_title) < 5 or len(new_title) > 100:
        await message.answer("❌ Заголовок должен быть от 5 до 100 символов. Попробуйте ещё раз:")
        return

    # Быстрая rule-based проверка
    filter_result = validate_content(new_title)
    if not filter_result.is_valid:
        await message.answer(get_rejection_message(filter_result))
        return

    # LLM-проверка
    checking_msg = await message.answer("🔍 <i>Проверяю текст...</i>")
    try:
        llm_result = await validate_content_with_llm(new_title)
        if not llm_result.is_valid:
            await checking_msg.delete()
            await message.answer(get_rejection_message(llm_result))
            return
        await checking_msg.delete()
    except Exception as e:
        logger.error(f"[EDIT_TITLE] LLM error: {e}")
        await checking_msg.delete()

    data = await state.get_data()
    ad_id = data.get("edit_ad_id")

    if not ad_id:
        await state.clear()
        await message.answer("❌ Ошибка. Попробуйте заново.", reply_markup=get_back_keyboard())
        return

    # Обновляем заголовок в БД
    try:
        async with get_db_session() as session:
            from sqlalchemy import update
            import uuid

            stmt = update(Ad).where(Ad.id == uuid.UUID(ad_id)).values(title=new_title)
            await session.execute(stmt)
            await session.commit()

        # Обновляем в каналах
        updated, errors = await update_ad_in_channels(ad_id, message.bot)

        await state.clear()

        result_text = f"✅ Заголовок обновлён!\n\nНовый заголовок: «{new_title}»"
        if updated > 0:
            result_text += f"\n\n📢 Обновлено в {updated} канал(ах)"
        if errors > 0:
            result_text += f"\n⚠️ Ошибок: {errors}"

        await message.answer(result_text, reply_markup=get_back_keyboard())

    except Exception as e:
        logger.error(f"Ошибка обновления заголовка: {e}")
        await state.clear()
        await message.answer("❌ Ошибка сохранения. Попробуйте позже.", reply_markup=get_back_keyboard())


@router.message(EditAdStates.waiting_for_new_description)
async def process_new_description(message: Message, state: FSMContext):
    """Обработка нового описания"""
    new_desc = message.text.strip()

    if len(new_desc) < 10 or len(new_desc) > 2000:
        await message.answer("❌ Описание должно быть от 10 до 2000 символов. Попробуйте ещё раз:")
        return

    # Быстрая rule-based проверка
    filter_result = validate_content(new_desc)
    if not filter_result.is_valid:
        await message.answer(get_rejection_message(filter_result))
        return

    # LLM-проверка
    checking_msg = await message.answer("🔍 <i>Проверяю описание...</i>")
    try:
        llm_result = await validate_content_with_llm(new_desc)
        if not llm_result.is_valid:
            await checking_msg.delete()
            await message.answer(get_rejection_message(llm_result))
            return
        await checking_msg.delete()
    except Exception as e:
        logger.error(f"[EDIT_DESC] LLM error: {e}")
        await checking_msg.delete()

    data = await state.get_data()
    ad_id = data.get("edit_ad_id")

    if not ad_id:
        await state.clear()
        await message.answer("❌ Ошибка. Попробуйте заново.", reply_markup=get_back_keyboard())
        return

    try:
        async with get_db_session() as session:
            from sqlalchemy import update
            import uuid

            stmt = update(Ad).where(Ad.id == uuid.UUID(ad_id)).values(description=new_desc)
            await session.execute(stmt)
            await session.commit()

        # Обновляем в каналах
        updated, errors = await update_ad_in_channels(ad_id, message.bot)

        await state.clear()

        result_text = "✅ Описание обновлено!"
        if updated > 0:
            result_text += f"\n\n📢 Обновлено в {updated} канал(ах)"
        if errors > 0:
            result_text += f"\n⚠️ Ошибок: {errors}"

        await message.answer(result_text, reply_markup=get_back_keyboard())

    except Exception as e:
        logger.error(f"Ошибка обновления описания: {e}")
        await state.clear()
        await message.answer("❌ Ошибка сохранения. Попробуйте позже.", reply_markup=get_back_keyboard())


@router.message(EditAdStates.waiting_for_new_price)
async def process_new_price(message: Message, state: FSMContext):
    """Обработка новой цены"""
    price_text = message.text.strip()

    data = await state.get_data()
    ad_id = data.get("edit_ad_id")

    if not ad_id:
        await state.clear()
        await message.answer("❌ Ошибка. Попробуйте заново.", reply_markup=get_back_keyboard())
        return

    # Пробуем распарсить как число
    try:
        # Убираем пробелы, запятые, символ рубля
        clean_price = price_text.replace(" ", "").replace(",", "").replace("₽", "").replace("р", "").replace("руб", "")
        new_price = float(clean_price)

        async with get_db_session() as session:
            from sqlalchemy import update
            import uuid

            stmt = update(Ad).where(Ad.id == uuid.UUID(ad_id)).values(price=new_price)
            await session.execute(stmt)
            await session.commit()

        # Обновляем в каналах
        updated, errors = await update_ad_in_channels(ad_id, message.bot)

        await state.clear()
        price_display = f"{int(new_price):,}".replace(",", " ") + " ₽"

        result_text = f"✅ Цена обновлена!\n\nНовая цена: {price_display}"
        if updated > 0:
            result_text += f"\n\n📢 Обновлено в {updated} канал(ах)"
        if errors > 0:
            result_text += f"\n⚠️ Ошибок: {errors}"

        await message.answer(result_text, reply_markup=get_back_keyboard())

    except ValueError:
        # Если это не число - сохраняем как текст в premium_features
        try:
            async with get_db_session() as session:
                from sqlalchemy import update, select
                import uuid

                # Получаем текущие premium_features
                result = await session.execute(
                    select(Ad.premium_features).where(Ad.id == uuid.UUID(ad_id))
                )
                current_pf = result.scalar() or {}
                current_pf['price_text'] = price_text

                stmt = update(Ad).where(Ad.id == uuid.UUID(ad_id)).values(
                    price=None,
                    premium_features=current_pf
                )
                await session.execute(stmt)
                await session.commit()

            # Обновляем в каналах
            updated, errors = await update_ad_in_channels(ad_id, message.bot)

            await state.clear()

            result_text = f"✅ Цена обновлена!\n\nНовая цена: {price_text}"
            if updated > 0:
                result_text += f"\n\n📢 Обновлено в {updated} канал(ах)"
            if errors > 0:
                result_text += f"\n⚠️ Ошибок: {errors}"

            await message.answer(result_text, reply_markup=get_back_keyboard())

        except Exception as e:
            logger.error(f"Ошибка обновления цены: {e}")
            await state.clear()
            await message.answer("❌ Ошибка сохранения. Попробуйте позже.", reply_markup=get_back_keyboard())


# =========================================================================
# ОБРАБОТЧИКИ ПРОДЛЕНИЯ И СНЯТИЯ ОБЪЯВЛЕНИЙ
# =========================================================================

@router.callback_query(F.data.startswith("extend_ad:"))
async def callback_extend_ad(callback: CallbackQuery):
    """Продлить объявление (кнопка из уведомления)"""
    ad_id = callback.data.replace("extend_ad:", "")

    await callback.answer("⏳ Продлеваю объявление...")

    try:
        async with get_db_session() as session:
            from bot.services.ad_lifecycle import AdLifecycleService
            from bot.database.models import Ad, AdStatus
            from sqlalchemy import select
            import uuid

            # Получаем объявление
            result = await session.execute(
                select(Ad).where(Ad.id == uuid.UUID(ad_id))
            )
            ad = result.scalar_one_or_none()
            
            if not ad:
                await callback.message.edit_text("❌ Объявление не найдено")
                return
            
            if ad.status != AdStatus.ACTIVE.value:
                await callback.message.edit_text("❌ Объявление уже не активно")
                return
            
            # Продлеваем
            service = AdLifecycleService(callback.bot, session)
            success, message = await service.extend_ad(ad)
            
            if success:
                # Формируем ссылку на новое объявление
                channel_ids = ad.channel_message_ids or {}
                ad_link = None
                for channel, msg_ids in channel_ids.items():
                    first_msg_id = msg_ids[0] if isinstance(msg_ids, list) else msg_ids
                    if channel.startswith("@"):
                        ad_link = f"https://t.me/{channel[1:]}/{first_msg_id}"
                        break
                
                link_text = f'\n\n<a href="{ad_link}">Открыть объявление</a>' if ad_link else ""
                
                await callback.message.edit_text(
                    f"✅ <b>Объявление продлено!</b>\n\n"
                    f"📋 {ad.title}\n"
                    f"⏳ Новый срок: до {ad.expires_at.strftime('%d.%m.%Y')}{link_text}",
                    disable_web_page_preview=True
                )
            else:
                await callback.message.edit_text(f"❌ Ошибка: {message}")
                
    except Exception as e:
        logger.error(f"Ошибка продления: {e}")
        await callback.message.edit_text("❌ Произошла ошибка. Попробуйте позже.")


@router.callback_query(F.data.startswith("archive_ad:"))
async def callback_archive_ad(callback: CallbackQuery):
    """Снять объявление с публикации (кнопка из уведомления)"""
    ad_id = callback.data.replace("archive_ad:", "")

    await callback.answer("⏳ Снимаю объявление...")

    try:
        async with get_db_session() as session:
            from bot.services.ad_lifecycle import AdLifecycleService
            from bot.database.models import Ad, AdStatus
            from sqlalchemy import select
            import uuid

            # Получаем объявление
            result = await session.execute(
                select(Ad).where(Ad.id == uuid.UUID(ad_id))
            )
            ad = result.scalar_one_or_none()
            
            if not ad:
                await callback.message.edit_text("❌ Объявление не найдено")
                return
            
            if ad.status != AdStatus.ACTIVE.value:
                await callback.message.edit_text("❌ Объявление уже не активно")
                return
            
            # Перемещаем в архив
            service = AdLifecycleService(callback.bot, session)
            success = await service.move_to_archive(ad)
            await session.commit()
            
            if success:
                await callback.message.edit_text(
                    f"✅ <b>Объявление снято с публикации</b>\n\n"
                    f"📋 {ad.title}\n\n"
                    f"Вы можете переопубликовать его в разделе «Мои объявления» → «Неактивные»."
                )
            else:
                await callback.message.edit_text("❌ Ошибка снятия объявления")
                
    except Exception as e:
        logger.error(f"Ошибка снятия: {e}")
        await callback.message.edit_text("❌ Произошла ошибка. Попробуйте позже.")


@router.callback_query(F.data.startswith("boost_ad:"))
async def callback_boost_ad(callback: CallbackQuery):
    """Поднять объявление (платная услуга)"""
    ad_id = callback.data.replace("boost_ad:", "")

    await callback.answer("⏳ Поднимаю объявление...")

    try:
        async with get_db_session() as session:
            from bot.services.ad_lifecycle import AdLifecycleService
            from bot.database.models import Ad, AdStatus
            from sqlalchemy import select
            import uuid

            result = await session.execute(
                select(Ad).where(Ad.id == uuid.UUID(ad_id))
            )
            ad = result.scalar_one_or_none()
            
            if not ad:
                await callback.message.edit_text("❌ Объявление не найдено")
                return
            
            if ad.status != AdStatus.ACTIVE.value:
                await callback.message.edit_text("❌ Объявление не активно")
                return
            
            service = AdLifecycleService(callback.bot, session)
            success, message = await service.boost_ad(ad)
            
            if success:
                # Формируем ссылку
                channel_ids = ad.channel_message_ids or {}
                ad_link = None
                for channel, msg_ids in channel_ids.items():
                    first_msg_id = msg_ids[0] if isinstance(msg_ids, list) else msg_ids
                    if channel.startswith("@"):
                        ad_link = f"https://t.me/{channel[1:]}/{first_msg_id}"
                        break
                
                link_text = f'\n\n<a href="{ad_link}">Открыть объявление</a>' if ad_link else ""
                
                await callback.message.edit_text(
                    f"🚀 <b>Объявление поднято!</b>\n\n"
                    f"📋 {ad.title}{link_text}",
                    disable_web_page_preview=True
                )
            else:
                await callback.message.edit_text(f"❌ Ошибка: {message}")
                
    except Exception as e:
        logger.error(f"Ошибка поднятия: {e}")
        await callback.message.edit_text("❌ Произошла ошибка. Попробуйте позже.")
