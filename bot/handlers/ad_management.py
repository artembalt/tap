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
            for channel, msg_id in ad.channel_message_ids.items():
                try:
                    if ad.photos or ad.video:
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
ADS_PER_PAGE = 50


class EditAdStates(StatesGroup):
    """Состояния для редактирования объявления"""
    waiting_for_new_title = State()
    waiting_for_new_description = State()
    waiting_for_new_price = State()


def get_my_ads_keyboard(offset: int, total: int) -> InlineKeyboardMarkup:
    """Клавиатура для пагинации объявлений"""
    buttons = []

    # Навигация по страницам
    nav_row = []

    # Кнопка "Назад" на предыдущую страницу
    if offset > 0:
        prev_offset = max(0, offset - ADS_PER_PAGE)
        nav_row.append(InlineKeyboardButton(
            text="◀️ Назад",
            callback_data=f"my_ads_page_{prev_offset}"
        ))

    # Кнопка "Далее" если есть ещё объявления
    if offset + ADS_PER_PAGE < total:
        nav_row.append(InlineKeyboardButton(
            text="Далее ▶️",
            callback_data=f"my_ads_page_{offset + ADS_PER_PAGE}"
        ))

    if nav_row:
        buttons.append(nav_row)

    # Кнопка в главное меню
    buttons.append([
        InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_menu")
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

    bot_username = settings.BOT_USERNAME

    for i, ad in enumerate(ads, start_num):
        status_emoji = {
            "active": "✅",
            "pending": "⏳",
            "archived": "📦",
            "rejected": "❌"
        }.get(ad.status, "❓")

        # Формируем цену
        if ad.price:
            price_text = f"{int(ad.price):,}".replace(",", " ")
        else:
            pf = ad.premium_features or {}
            price_text = pf.get('price_text', 'Договорная')

        # Получаем ссылку на объявление в канале
        channel_link = get_channel_link(ad)

        title_display = ad.title[:40] + "..." if len(ad.title) > 40 else ad.title

        # Заголовок
        if channel_link:
            text += f"{i}. {status_emoji} <a href=\"{channel_link}\">{title_display}</a>\n"
        else:
            text += f"{i}. {status_emoji} {title_display}\n"

        # Цена
        text += f"   ₽ {price_text}\n"

        # Ссылки на действия (deep links)
        edit_link = f"https://t.me/{bot_username}?start=edit_{ad.id}"
        delete_link = f"https://t.me/{bot_username}?start=del_{ad.id}"

        text += f"   <a href=\"{edit_link}\">✏️ Изменить</a>  <a href=\"{delete_link}\">🗑 Удалить</a>\n\n"

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


@router.message(EditAdStates.waiting_for_new_title)
async def process_new_title(message: Message, state: FSMContext):
    """Обработка нового заголовка"""
    new_title = message.text.strip()

    if len(new_title) < 5 or len(new_title) > 100:
        await message.answer("❌ Заголовок должен быть от 5 до 100 символов. Попробуйте ещё раз:")
        return

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

        await state.clear()
        await message.answer(
            f"✅ Заголовок обновлён!\n\nНовый заголовок: «{new_title}»",
            reply_markup=get_back_keyboard()
        )

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

        await state.clear()
        await message.answer(
            f"✅ Описание обновлено!",
            reply_markup=get_back_keyboard()
        )

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

        await state.clear()
        price_display = f"{int(new_price):,}".replace(",", " ") + " ₽"
        await message.answer(
            f"✅ Цена обновлена!\n\nНовая цена: {price_display}",
            reply_markup=get_back_keyboard()
        )

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

            await state.clear()
            await message.answer(
                f"✅ Цена обновлена!\n\nНовая цена: {price_text}",
                reply_markup=get_back_keyboard()
            )

        except Exception as e:
            logger.error(f"Ошибка обновления цены: {e}")
            await state.clear()
            await message.answer("❌ Ошибка сохранения. Попробуйте позже.", reply_markup=get_back_keyboard())
