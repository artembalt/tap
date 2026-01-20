# bot/services/ad_lifecycle.py
"""
Сервис управления жизненным циклом объявлений.

Функции:
- Перемещение в архивный канал (когда срок публикации истёк)
- Переопубликация из архива
- Полная архивация (через 6 месяцев неактивности)
- Уведомления об истечении срока

Использование:
    from bot.services.ad_lifecycle import AdLifecycleService

    service = AdLifecycleService(bot, session)
    await service.move_to_archive(ad)
    await service.republish_from_archive(ad)
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple
from uuid import UUID

from aiogram import Bot
from aiogram.types import InputMediaPhoto
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from sqlalchemy import select, update, and_
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config.pricing import AD_LIFECYCLE_CONFIG, ACCOUNT_TYPES, get_account_limits
from bot.database.models import Ad, User, ArchivedAd, AdStatus
from shared.regions_config import CHANNELS_CONFIG, REGIONS, CATEGORIES, RegionConfig

logger = logging.getLogger(__name__)


class AdLifecycleService:
    """Сервис управления жизненным циклом объявлений"""

    def __init__(self, bot: Bot, session: AsyncSession):
        self.bot = bot
        self.session = session

    # =========================================================================
    # ПЕРЕМЕЩЕНИЕ В АРХИВНЫЙ КАНАЛ
    # =========================================================================

    async def move_to_archive(self, ad: Ad) -> bool:
        """
        Переместить объявление в архивный канал.

        Вызывается когда срок публикации истёк:
        1. Удаляет из родного канала
        2. Публикует в архивный канал
        3. Обновляет статус на INACTIVE

        Args:
            ad: Объявление для перемещения

        Returns:
            True если успешно, False если ошибка
        """
        logger.info(f"[LIFECYCLE] move_to_archive: ad_id={ad.id}")

        # Получаем конфигурацию региона
        region_config = RegionConfig.get_region(ad.region)
        if not region_config:
            logger.error(f"[LIFECYCLE] Регион не найден: {ad.region}")
            return False

        archive_channel = region_config.archive_channel
        if not archive_channel:
            logger.warning(f"[LIFECYCLE] Архивный канал не настроен для {ad.region}")
            # Просто меняем статус без перемещения в архивный канал
            ad.status = AdStatus.INACTIVE.value
            return True

        try:
            # 1. Удаляем из родных каналов
            await self._delete_from_channels(ad)

            # 2. Публикуем в архивный канал
            archive_message_ids = await self._publish_to_archive(ad, archive_channel)

            if archive_message_ids:
                # 3. Обновляем объявление
                ad.status = AdStatus.INACTIVE.value
                ad.archive_message_ids = {archive_channel: archive_message_ids}
                ad.archived_to_channel_at = datetime.utcnow()
                ad.channel_message_ids = {}  # Очищаем старые ID

                logger.info(f"[LIFECYCLE] Объявление {ad.id} перемещено в архив")
                return True
            else:
                logger.error(f"[LIFECYCLE] Не удалось опубликовать в архивный канал")
                return False

        except Exception as e:
            logger.error(f"[LIFECYCLE] Ошибка move_to_archive: {e}")
            return False

    async def _delete_from_channels(self, ad: Ad) -> None:
        """Удалить сообщения объявления из всех каналов"""
        if not ad.channel_message_ids:
            return

        for channel_id, message_ids in ad.channel_message_ids.items():
            if isinstance(message_ids, list):
                for msg_id in message_ids:
                    await self._safe_delete_message(channel_id, msg_id)
            else:
                await self._safe_delete_message(channel_id, message_ids)

    async def _safe_delete_message(self, chat_id: str, message_id: int) -> bool:
        """Безопасное удаление сообщения"""
        try:
            await self.bot.delete_message(chat_id=chat_id, message_id=message_id)
            logger.debug(f"[LIFECYCLE] Удалено сообщение {message_id} из {chat_id}")
            return True
        except TelegramBadRequest as e:
            if "message to delete not found" in str(e):
                logger.debug(f"[LIFECYCLE] Сообщение уже удалено: {message_id}")
            else:
                logger.warning(f"[LIFECYCLE] Ошибка удаления: {e}")
            return False
        except Exception as e:
            logger.warning(f"[LIFECYCLE] Ошибка удаления сообщения: {e}")
            return False

    async def _publish_to_archive(self, ad: Ad, archive_channel: str) -> List[int]:
        """
        Опубликовать объявление в архивный канал.

        Returns:
            Список message_id опубликованных сообщений
        """
        # Формируем текст (упрощённый, для архива)
        text = self._format_archive_text(ad)

        photos = ad.photos or []
        message_ids = []

        try:
            if photos:
                if len(photos) == 1:
                    msg = await self.bot.send_photo(
                        chat_id=archive_channel,
                        photo=photos[0],
                        caption=text
                    )
                    message_ids = [msg.message_id]
                else:
                    # Media group
                    media = [InputMediaPhoto(media=photos[0], caption=text)]
                    for p in photos[1:10]:
                        media.append(InputMediaPhoto(media=p))
                    msgs = await self.bot.send_media_group(chat_id=archive_channel, media=media)
                    message_ids = [m.message_id for m in msgs]
            elif ad.video:
                msg = await self.bot.send_video(
                    chat_id=archive_channel,
                    video=ad.video,
                    caption=text
                )
                message_ids = [msg.message_id]
            else:
                # Только текст
                msg = await self.bot.send_message(
                    chat_id=archive_channel,
                    text=text,
                    disable_web_page_preview=True
                )
                message_ids = [msg.message_id]

            logger.info(f"[LIFECYCLE] Опубликовано в архив {archive_channel}: {message_ids}")
            return message_ids

        except Exception as e:
            logger.error(f"[LIFECYCLE] Ошибка публикации в архив: {e}")
            return []

    def _format_archive_text(self, ad: Ad) -> str:
        """Форматировать текст для архивного канала"""
        region_name = REGIONS.get(ad.region, ad.region)
        category_name = CATEGORIES.get(ad.category, ad.category)

        price_text = ""
        if ad.price:
            price_text = f"\n💰 {ad.price:,.0f} {ad.currency or 'RUB'}"

        return (
            f"📦 <b>АРХИВ</b> | ID: {ad.id}\n"
            f"━━━━━━━━━━━━━━━━━\n"
            f"📍 {region_name} | {category_name}\n"
            f"👤 Владелец: {ad.user_id}\n"
            f"━━━━━━━━━━━━━━━━━\n\n"
            f"<b>{ad.title}</b>{price_text}\n\n"
            f"{ad.description[:500]}{'...' if len(ad.description) > 500 else ''}"
        )

    # =========================================================================
    # ПЕРЕОПУБЛИКАЦИЯ ИЗ АРХИВА
    # =========================================================================

    async def republish_from_archive(
        self,
        ad: Ad,
        user: User
    ) -> Tuple[bool, str, Optional[Dict[str, List[int]]]]:
        """
        Переопубликовать объявление из архива.

        1. Получить фото из архивного канала
        2. Опубликовать в родной канал
        3. Удалить из архивного канала
        4. Обновить статус на ACTIVE

        Args:
            ad: Объявление для переопубликации
            user: Пользователь (для проверки платности)

        Returns:
            (success, message, channel_ids)
        """
        logger.info(f"[LIFECYCLE] republish_from_archive: ad_id={ad.id}")

        if ad.status != AdStatus.INACTIVE.value:
            return False, "Объявление не в архиве", None

        # Проверяем cooldown
        config = AD_LIFECYCLE_CONFIG["republish"]
        if ad.last_republished_at:
            cooldown_hours = config.get("cooldown_hours", 24)
            cooldown_delta = timedelta(hours=cooldown_hours)
            if datetime.utcnow() - ad.last_republished_at < cooldown_delta:
                remaining = (ad.last_republished_at + cooldown_delta) - datetime.utcnow()
                hours = int(remaining.total_seconds() // 3600)
                return False, f"Переопубликация доступна через {hours} ч.", None

        # Получаем конфигурацию региона
        region_config = RegionConfig.get_region(ad.region)
        if not region_config or not region_config.is_configured():
            return False, "Каналы для региона не настроены", None

        try:
            # 1. Публикуем в родные каналы (фото уже есть в ad.photos)
            channel_ids = await self._publish_to_channels(ad, region_config)

            if not channel_ids:
                return False, "Не удалось опубликовать в каналы", None

            # 2. Удаляем из архивного канала
            if ad.archive_message_ids:
                for channel_id, message_ids in ad.archive_message_ids.items():
                    if isinstance(message_ids, list):
                        for msg_id in message_ids:
                            await self._safe_delete_message(channel_id, msg_id)
                    else:
                        await self._safe_delete_message(channel_id, message_ids)

            # 3. Обновляем объявление
            # Получаем срок публикации из типа аккаунта
            account_limits = get_account_limits(user.account_type or "free")
            duration_days = account_limits.get("ad_duration_days", 30)

            ad.status = AdStatus.ACTIVE.value
            ad.channel_message_ids = channel_ids
            ad.archive_message_ids = {}
            ad.archived_to_channel_at = None
            ad.published_at = datetime.utcnow()
            ad.expires_at = datetime.utcnow() + timedelta(days=duration_days)
            ad.republish_count = (ad.republish_count or 0) + 1
            ad.last_republished_at = datetime.utcnow()

            logger.info(f"[LIFECYCLE] Объявление {ad.id} переопубликовано")
            return True, "Объявление опубликовано", channel_ids

        except Exception as e:
            logger.error(f"[LIFECYCLE] Ошибка republish: {e}")
            return False, f"Ошибка: {str(e)}", None

    async def _publish_to_channels(
        self,
        ad: Ad,
        region_config: RegionConfig
    ) -> Dict[str, List[int]]:
        """Опубликовать объявление в каналы региона"""
        from bot.handlers.ad_creation import publish_to_channel

        # Формируем data как при первичной публикации
        data = {
            "region": ad.region,
            "city": ad.city,
            "category": ad.category,
            "subcategory": ad.premium_features.get("subcategory") if ad.premium_features else None,
            "title": ad.title,
            "description": ad.description,
            "price": ad.price,
            "photos": ad.photos or [],
            "video": ad.video,
            "deal_type": ad.ad_type,
            "condition": ad.premium_features.get("condition") if ad.premium_features else None,
            "delivery": ad.premium_features.get("delivery") if ad.premium_features else None,
            "links": ad.links or [],
        }

        # Получаем информацию о боте
        bot_info = await self.bot.get_me()

        # Используем существующую функцию публикации
        channel_ids = await publish_to_channel(self.bot, bot_info, ad, data)
        return channel_ids

    def is_republish_free(self, ad: Ad) -> bool:
        """Проверить, бесплатна ли переопубликация"""
        config = AD_LIFECYCLE_CONFIG["republish"]

        # Первая переопубликация бесплатна?
        if config.get("free_first_time", True):
            if (ad.republish_count or 0) == 0:
                return True

        return False

    def get_republish_price(self) -> Tuple[float, int]:
        """Получить цену переопубликации (rub, stars)"""
        config = AD_LIFECYCLE_CONFIG["republish"]
        return (
            config.get("price_rub", 29.0),
            config.get("price_stars", 15)
        )

    # =========================================================================
    # ПОЛНАЯ АРХИВАЦИЯ (6 МЕСЯЦЕВ)
    # =========================================================================

    async def archive_old_inactive(self) -> int:
        """
        Переместить старые неактивные объявления в таблицу archived_ads.

        Вызывается планировщиком ежедневно.
        Условие: status=INACTIVE и archived_to_channel_at < now() - 6 месяцев

        Returns:
            Количество заархивированных объявлений
        """
        config = AD_LIFECYCLE_CONFIG["archive"]
        retention_days = config.get("inactive_retention_days", 180)
        batch_size = config.get("cleanup_batch_size", 100)

        cutoff_date = datetime.utcnow() - timedelta(days=retention_days)

        # Находим объявления для архивации
        stmt = select(Ad).where(
            and_(
                Ad.status == AdStatus.INACTIVE.value,
                Ad.archived_to_channel_at != None,
                Ad.archived_to_channel_at < cutoff_date
            )
        ).limit(batch_size)

        result = await self.session.execute(stmt)
        ads = result.scalars().all()

        archived_count = 0
        for ad in ads:
            try:
                # 1. Удаляем из архивного канала
                if ad.archive_message_ids:
                    for channel_id, message_ids in ad.archive_message_ids.items():
                        if isinstance(message_ids, list):
                            for msg_id in message_ids:
                                await self._safe_delete_message(channel_id, msg_id)
                        else:
                            await self._safe_delete_message(channel_id, message_ids)

                # 2. Копируем в archived_ads
                archived_ad = ArchivedAd(
                    id=ad.id,
                    user_id=ad.user_id,
                    title=ad.title,
                    description=ad.description,
                    price=ad.price,
                    currency=ad.currency,
                    ad_type=ad.ad_type,
                    region=ad.region,
                    city=ad.city,
                    category=ad.category,
                    subcategory=ad.subcategory,
                    photos=ad.photos,
                    video=ad.video,
                    hashtags=ad.hashtags,
                    views_count=ad.views_count,
                    favorites_count=ad.favorites_count,
                    contacts_count=ad.contacts_count,
                    created_at=ad.created_at,
                    published_at=ad.published_at,
                    deleted_at=ad.deleted_at,
                    archived_at=datetime.utcnow(),
                    archive_reason="inactive_expired"
                )
                self.session.add(archived_ad)

                # 3. Удаляем из основной таблицы
                await self.session.delete(ad)
                archived_count += 1

                logger.info(f"[LIFECYCLE] Объявление {ad.id} полностью заархивировано")

            except Exception as e:
                logger.error(f"[LIFECYCLE] Ошибка архивации {ad.id}: {e}")
                continue

        if archived_count > 0:
            await self.session.commit()

        logger.info(f"[LIFECYCLE] Заархивировано {archived_count} объявлений")
        return archived_count

    # =========================================================================
    # ПРОВЕРКА ИСТЕКШИХ ОБЪЯВЛЕНИЙ
    # =========================================================================

    async def process_expired_ads(self) -> int:
        """
        Обработать объявления с истёкшим сроком публикации.

        Вызывается планировщиком (каждый час или чаще).

        Returns:
            Количество обработанных объявлений
        """
        now = datetime.utcnow()

        # Находим активные объявления с истёкшим сроком
        stmt = select(Ad).where(
            and_(
                Ad.status == AdStatus.ACTIVE.value,
                Ad.expires_at != None,
                Ad.expires_at < now
            )
        ).limit(100)

        result = await self.session.execute(stmt)
        ads = result.scalars().all()

        processed_count = 0
        for ad in ads:
            success = await self.move_to_archive(ad)
            if success:
                processed_count += 1

        if processed_count > 0:
            await self.session.commit()

        logger.info(f"[LIFECYCLE] Обработано истёкших: {processed_count}")
        return processed_count

    # =========================================================================
    # УВЕДОМЛЕНИЯ
    # =========================================================================

    async def get_ads_expiring_soon(self) -> List[Ad]:
        """
        Получить объявления, срок которых истекает скоро.

        Returns:
            Список объявлений для уведомления
        """
        config = AD_LIFECYCLE_CONFIG["notifications"]
        if not config.get("expiry_warn_enabled", True):
            return []

        warn_days = config.get("expiry_warn_days", 1)

        now = datetime.utcnow()
        warn_start = now
        warn_end = now + timedelta(days=warn_days)

        stmt = select(Ad).where(
            and_(
                Ad.status == AdStatus.ACTIVE.value,
                Ad.expires_at != None,
                Ad.expires_at > warn_start,
                Ad.expires_at <= warn_end
            )
        )

        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def send_expiry_notification(self, ad: Ad, user: User) -> bool:
        """Отправить уведомление об истечении срока"""
        try:
            hours_left = int((ad.expires_at - datetime.utcnow()).total_seconds() / 3600)

            text = (
                f"⏰ <b>Объявление скоро истечёт!</b>\n\n"
                f"📋 {ad.title}\n"
                f"⏳ Осталось: {hours_left} ч.\n\n"
                f"После истечения срока объявление будет снято с публикации, "
                f"но сохранится в вашем личном кабинете.\n\n"
                f"Вы сможете переопубликовать его в любое время."
            )

            await self.bot.send_message(
                chat_id=user.telegram_id,
                text=text
            )
            return True

        except TelegramForbiddenError:
            logger.warning(f"[LIFECYCLE] Пользователь {user.telegram_id} заблокировал бота")
            return False
        except Exception as e:
            logger.error(f"[LIFECYCLE] Ошибка отправки уведомления: {e}")
            return False


# =========================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# =========================================================================

async def get_lifecycle_service(bot: Bot, session: AsyncSession) -> AdLifecycleService:
    """Фабрика для создания сервиса"""
    return AdLifecycleService(bot, session)
