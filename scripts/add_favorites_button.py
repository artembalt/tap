#!/usr/bin/env python3
"""
Скрипт для добавления кнопки "В избранное" к старым объявлениям продавца.

Обновляет текст/caption сообщений в каналах, добавляя ссылку на избранное.
"""

import asyncio
import logging
import sys
import os

# Добавляем корень проекта в путь
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from bot.config import settings
from bot.database.models import Ad, AdStatus
from shared.regions_config import (
    REGIONS, CATEGORIES, SUBCATEGORIES,
    get_city_hashtag, get_subcategory_hashtag
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def format_ad_text(ad: Ad, bot_username: str) -> str:
    """Формирует текст объявления с кнопкой избранного"""
    # Хэштеги
    hashtags = []

    if ad.subcategory:
        subcategory_hashtag = get_subcategory_hashtag(ad.subcategory)
        hashtags.append(subcategory_hashtag)

    if ad.category and ad.region:
        category_name = CATEGORIES.get(ad.category, ad.category)
        region_name = REGIONS.get(ad.region, ad.region)
        cat_clean = category_name.split()[-1] if ' ' in category_name else category_name
        reg_clean = region_name.replace(' ', '_').replace('-', '_')
        combined_hashtag = f"#{cat_clean}_{reg_clean}"
        hashtags.append(combined_hashtag)

    if ad.city:
        city_hashtag = get_city_hashtag(ad.city)
        hashtags.append(city_hashtag)

    hashtags_text = " ".join(hashtags) if hashtags else ""

    # Форматируем цену
    if ad.price:
        price_text = f"{int(ad.price):,}".replace(",", " ") + f" {ad.currency or 'RUB'}"
    else:
        price_text = "Не указана"

    # Полный текст объявления
    text = f"""<b>{ad.title}</b>

{ad.description}

💰 {price_text}

{hashtags_text}

━━━━━━━━━━━━━━━
😎 <a href="tg://user?id={ad.user_id}">Написать продавцу</a>
👾 <a href="https://t.me/{bot_username}?start=profile_{ad.user_id}">Профиль продавца</a>
⭐ <a href="https://t.me/{bot_username}?start=fav_{ad.id}">В избранное</a>
📢 <a href="https://t.me/{bot_username}">Разместить объявление</a>"""

    return text


async def update_channel_messages(seller_id: int, dry_run: bool = False):
    """
    Обновляет сообщения в каналах для объявлений продавца.

    Args:
        seller_id: ID продавца в Telegram
        dry_run: Если True, только показывает что будет сделано, без изменений
    """
    # Создаем подключение к БД
    engine = create_async_engine(settings.database_url, echo=False)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # Создаем бота
    bot = Bot(token=settings.BOT_TOKEN)
    bot_info = await bot.get_me()
    bot_username = bot_info.username

    logger.info(f"Бот: @{bot_username}")
    logger.info(f"Продавец ID: {seller_id}")
    logger.info(f"Режим: {'DRY RUN (без изменений)' if dry_run else 'РЕАЛЬНОЕ ОБНОВЛЕНИЕ'}")

    try:
        async with async_session() as session:
            # Получаем объявления продавца
            stmt = select(Ad).where(
                Ad.user_id == seller_id,
                Ad.status == AdStatus.ACTIVE.value,
                Ad.channel_message_ids != None,
                Ad.channel_message_ids != {}
            ).order_by(Ad.created_at.desc())

            result = await session.execute(stmt)
            ads = result.scalars().all()

            logger.info(f"Найдено объявлений с публикацией в каналах: {len(ads)}")

            updated = 0
            skipped = 0
            errors = 0

            for ad in ads:
                logger.info(f"\n--- Объявление: {ad.title[:50]}... (ID: {ad.id})")
                logger.info(f"    Каналы: {ad.channel_message_ids}")

                # Формируем новый текст
                new_text = format_ad_text(ad, bot_username)

                # Обновляем в каждом канале
                for channel, msg_id in ad.channel_message_ids.items():
                    try:
                        if dry_run:
                            logger.info(f"    [DRY RUN] Канал {channel}, msg_id={msg_id}")
                            continue

                        # Пробуем обновить caption (для фото/видео)
                        if ad.photos or ad.video:
                            await bot.edit_message_caption(
                                chat_id=channel,
                                message_id=msg_id,
                                caption=new_text,
                                parse_mode="HTML"
                            )
                            logger.info(f"    ✅ Обновлен caption в {channel}")
                        else:
                            # Для текстовых сообщений
                            await bot.edit_message_text(
                                chat_id=channel,
                                message_id=msg_id,
                                text=new_text,
                                parse_mode="HTML",
                                disable_web_page_preview=True
                            )
                            logger.info(f"    ✅ Обновлен текст в {channel}")

                        updated += 1

                        # Задержка чтобы не превысить лимиты API
                        await asyncio.sleep(1)

                    except TelegramAPIError as e:
                        error_msg = str(e).lower()
                        if "message is not modified" in error_msg:
                            logger.info(f"    ⏭ Канал {channel}: текст уже актуален")
                            skipped += 1
                        elif "message to edit not found" in error_msg:
                            logger.warning(f"    ⚠️ Канал {channel}: сообщение не найдено (удалено?)")
                            errors += 1
                        elif "message can't be edited" in error_msg:
                            logger.warning(f"    ⚠️ Канал {channel}: сообщение нельзя редактировать")
                            errors += 1
                        elif "flood control" in error_msg or "retry after" in error_msg:
                            # Извлекаем время ожидания из сообщения
                            import re
                            match = re.search(r'retry after (\d+)', error_msg)
                            wait_time = int(match.group(1)) if match else 35
                            logger.warning(f"    ⏳ Flood control, жду {wait_time} сек...")
                            await asyncio.sleep(wait_time + 1)
                            # Повторяем попытку
                            try:
                                if ad.photos or ad.video:
                                    await bot.edit_message_caption(
                                        chat_id=channel, message_id=msg_id,
                                        caption=new_text, parse_mode="HTML"
                                    )
                                else:
                                    await bot.edit_message_text(
                                        chat_id=channel, message_id=msg_id,
                                        text=new_text, parse_mode="HTML",
                                        disable_web_page_preview=True
                                    )
                                logger.info(f"    ✅ Обновлен после ожидания в {channel}")
                                updated += 1
                            except Exception as retry_e:
                                logger.error(f"    ❌ Повторная ошибка {channel}: {retry_e}")
                                errors += 1
                        else:
                            logger.error(f"    ❌ Канал {channel}: {e}")
                            errors += 1
                    except Exception as e:
                        logger.error(f"    ❌ Канал {channel}: неожиданная ошибка: {e}")
                        errors += 1

            logger.info(f"\n{'='*50}")
            logger.info(f"ИТОГО:")
            logger.info(f"  Обновлено: {updated}")
            logger.info(f"  Пропущено (уже актуальны): {skipped}")
            logger.info(f"  Ошибок: {errors}")

    finally:
        await bot.session.close()
        await engine.dispose()


async def main():
    """Точка входа"""
    if len(sys.argv) < 2:
        print("Использование: python add_favorites_button.py <seller_id> [--dry-run]")
        print("  seller_id: ID продавца в Telegram")
        print("  --dry-run: только показать что будет сделано, без изменений")
        sys.exit(1)

    try:
        seller_id = int(sys.argv[1])
    except ValueError:
        print(f"Ошибка: '{sys.argv[1]}' не является числом")
        sys.exit(1)

    dry_run = "--dry-run" in sys.argv

    await update_channel_messages(seller_id, dry_run=dry_run)


if __name__ == "__main__":
    asyncio.run(main())
