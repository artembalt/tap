# bot/services/ad_lifecycle.py
"""
Сервис управления жизненным циклом объявлений.

Функции:
- Уведомления об истечении срока (за 2 дня, 1 день, 1 час)
- Продление объявления (кнопка "Продлить")
- Снятие с публикации (кнопка "Снять" или игнор)
- Переопубликация неактивных объявлений
- Автоподнятие объявлений
- Перемещение неактивных в удалённые через 30 дней
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple
from uuid import UUID

from aiogram import Bot
from aiogram.types import InputMediaPhoto, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from sqlalchemy import select, update, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config.pricing import AD_LIFECYCLE_CONFIG, get_account_limits
from bot.database.models import Ad, User, ArchivedAd, AdStatus
from shared.regions_config import CHANNELS_CONFIG, REGIONS, CATEGORIES, RegionConfig

logger = logging.getLogger(__name__)


class AdLifecycleService:
    """Сервис управления жизненным циклом объявлений"""

    def __init__(self, bot: Bot, session: AsyncSession):
        self.bot = bot
        self.session = session

    # =========================================================================
    # ПРОДЛЕНИЕ ОБЪЯВЛЕНИЯ
    # =========================================================================

    async def extend_ad(self, ad: Ad) -> Tuple[bool, str]:
        """
        Продлить объявление на 30 дней.

        При продлении:
        1. Удаляем старый пост из канала
        2. Публикуем заново (в начало ленты)
        3. Обновляем expires_at на +30 дней
        4. Сбрасываем notifications_sent

        Returns:
            (success, message)
        """
        logger.info(f"[LIFECYCLE] extend_ad: ad_id={ad.id}")

        if ad.status != AdStatus.ACTIVE.value:
            return False, "Объявление не активно"

        # Получаем конфигурацию региона
        region_config = RegionConfig.get_region(ad.region)
        if not region_config or not region_config.is_configured():
            return False, "Каналы для региона не настроены"

        try:
            # 1. Удаляем старые посты из каналов
            await self._delete_from_channels(ad)

            # 2. Публикуем заново
            channel_ids = await self._publish_to_channels(ad, region_config)

            if not channel_ids:
                return False, "Не удалось опубликовать в каналы"

            # 3. Обновляем объявление
            extend_days = AD_LIFECYCLE_CONFIG["extend"]["duration_days"]
            ad.channel_message_ids = channel_ids
            ad.published_at = datetime.utcnow()
            ad.expires_at = datetime.utcnow() + timedelta(days=extend_days)
            ad.last_extended_at = datetime.utcnow()
            ad.notifications_sent = {}  # Сбрасываем уведомления

            await self.session.commit()

            logger.info(f"[LIFECYCLE] Объявление {ad.id} продлено до {ad.expires_at}")
            return True, "Объявление продлено"

        except Exception as e:
            logger.error(f"[LIFECYCLE] Ошибка extend_ad: {e}")
            return False, f"Ошибка: {str(e)}"

    # =========================================================================
    # СНЯТИЕ С ПУБЛИКАЦИИ
    # =========================================================================

    async def move_to_archive(self, ad: Ad) -> bool:
        """
        Снять объявление с публикации.

        Вызывается когда:
        - Срок публикации истёк и пользователь не продлил
        - Пользователь нажал "Снять"

        1. Удаляет из каналов
        2. Обновляет статус на INACTIVE

        Данные объявления остаются в БД, медиа - на серверах Telegram.
        """
        logger.info(f"[LIFECYCLE] move_to_archive: ad_id={ad.id}")

        try:
            # 1. Удаляем из каналов
            await self._delete_from_channels(ad)

            # 2. Меняем статус на INACTIVE
            ad.status = AdStatus.INACTIVE.value
            ad.channel_message_ids = {}
            ad.archived_to_channel_at = datetime.utcnow()
            ad.notifications_sent = {}

            logger.info(f"[LIFECYCLE] Объявление {ad.id} снято с публикации")
            return True

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
            return True
        except TelegramBadRequest as e:
            if "message to delete not found" not in str(e) and "message can't be deleted" not in str(e):
                logger.warning(f"[LIFECYCLE] Ошибка удаления {chat_id}/{message_id}: {e}")
            return False
        except Exception as e:
            logger.warning(f"[LIFECYCLE] Ошибка удаления сообщения: {e}")
            return False


    # =========================================================================
    # ПЕРЕОПУБЛИКАЦИЯ НЕАКТИВНЫХ ОБЪЯВЛЕНИЙ
    # =========================================================================

    async def republish_from_archive(
        self,
        ad: Ad,
        user: User
    ) -> Tuple[bool, str, Optional[Dict[str, List[int]]]]:
        """
        Переопубликовать неактивное объявление.

        Данные берутся из БД, медиа по file_id с серверов Telegram.
        """
        logger.info(f"[LIFECYCLE] republish_from_archive: ad_id={ad.id}")

        if ad.status not in [AdStatus.INACTIVE.value, AdStatus.DELETED.value]:
            return False, "Объявление не подходит для переопубликации", None

        region_config = RegionConfig.get_region(ad.region)
        if not region_config or not region_config.is_configured():
            return False, "Каналы для региона не настроены", None

        try:
            # 1. Публикуем в каналы
            channel_ids = await self._publish_to_channels(ad, region_config)

            if not channel_ids:
                return False, "Не удалось опубликовать в каналы", None

            # 2. Обновляем объявление
            account_limits = get_account_limits(user.account_type or "free")
            duration_days = account_limits.get("ad_duration_days", 30)

            ad.status = AdStatus.ACTIVE.value
            ad.channel_message_ids = channel_ids
            ad.archived_to_channel_at = None
            ad.published_at = datetime.utcnow()
            ad.expires_at = datetime.utcnow() + timedelta(days=duration_days)
            ad.republish_count = (ad.republish_count or 0) + 1
            ad.last_republished_at = datetime.utcnow()
            ad.notifications_sent = {}

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

        bot_info = await self.bot.get_me()
        channel_ids = await publish_to_channel(self.bot, bot_info, ad, data)
        return channel_ids

    # =========================================================================
    # ПОДНЯТИЕ ОБЪЯВЛЕНИЯ (BOOST)
    # =========================================================================

    async def boost_ad(self, ad: Ad) -> Tuple[bool, str]:
        """
        Поднять объявление в начало ленты.

        Удаляет старый пост и публикует заново.
        """
        logger.info(f"[LIFECYCLE] boost_ad: ad_id={ad.id}")

        if ad.status != AdStatus.ACTIVE.value:
            return False, "Объявление не активно"

        region_config = RegionConfig.get_region(ad.region)
        if not region_config or not region_config.is_configured():
            return False, "Каналы для региона не настроены"

        try:
            # 1. Удаляем старые посты
            await self._delete_from_channels(ad)

            # 2. Публикуем заново
            channel_ids = await self._publish_to_channels(ad, region_config)

            if not channel_ids:
                return False, "Не удалось опубликовать в каналы"

            # 3. Обновляем объявление
            ad.channel_message_ids = channel_ids
            ad.published_at = datetime.utcnow()

            # Если есть автоподнятие - уменьшаем счётчик и ставим следующую дату
            if ad.boost_remaining and ad.boost_remaining > 0:
                ad.boost_remaining -= 1
                if ad.boost_remaining > 0 and ad.boost_service:
                    from bot.config.pricing import PAID_SERVICES
                    service = PAID_SERVICES.get(ad.boost_service, {})
                    interval_days = service.get("interval_days", 6)
                    ad.next_boost_at = datetime.utcnow() + timedelta(days=interval_days)
                else:
                    ad.boost_service = None
                    ad.next_boost_at = None

            await self.session.commit()

            logger.info(f"[LIFECYCLE] Объявление {ad.id} поднято")
            return True, "Объявление поднято"

        except Exception as e:
            logger.error(f"[LIFECYCLE] Ошибка boost_ad: {e}")
            return False, f"Ошибка: {str(e)}"

    # =========================================================================
    # УВЕДОМЛЕНИЯ
    # =========================================================================

    async def get_ads_for_notification(self, days_before: int) -> List[Ad]:
        """
        Получить объявления для уведомления за N дней до истечения.

        days_before=2: объявления истекающие через 2-3 дня (уведомление на 28-й день)
        days_before=1: объявления истекающие через 1-2 дня (уведомление на 29-й день)
        """
        config = AD_LIFECYCLE_CONFIG["notifications"]
        if not config.get("enabled", True):
            return []

        now = datetime.utcnow()

        # Ищем объявления в конкретном окне времени
        # Например, days_before=2: expires_at между now+2d и now+3d
        window_start = now + timedelta(days=days_before)
        window_end = now + timedelta(days=days_before + 1)

        stmt = select(Ad).where(
            and_(
                Ad.status == AdStatus.ACTIVE.value,
                Ad.expires_at != None,
                Ad.expires_at > window_start,
                Ad.expires_at <= window_end
            )
        )

        result = await self.session.execute(stmt)
        ads = result.scalars().all()

        # Фильтруем по отправленным уведомлениям
        notification_key = f"day_{days_before}"
        return [ad for ad in ads if not (ad.notifications_sent or {}).get(notification_key)]

    async def get_ads_for_final_notification(self) -> List[Ad]:
        """
        Получить объявления для финального уведомления (за 1 час до удаления).
        """
        config = AD_LIFECYCLE_CONFIG["notifications"]
        hours_before = config.get("final_warn_hours", 1)

        now = datetime.utcnow()
        target_time = now + timedelta(hours=hours_before)

        stmt = select(Ad).where(
            and_(
                Ad.status == AdStatus.ACTIVE.value,
                Ad.expires_at != None,
                Ad.expires_at > now,
                Ad.expires_at <= target_time
            )
        )

        result = await self.session.execute(stmt)
        ads = result.scalars().all()

        notification_key = "hour_1"
        return [ad for ad in ads if not (ad.notifications_sent or {}).get(notification_key)]

    async def send_expiry_notification(
        self,
        ad: Ad,
        user: User,
        days_left: int,
        is_final: bool = False
    ) -> bool:
        """
        Отправить уведомление об истечении срока с кнопками.
        """
        try:
            # Формируем ссылку на объявление
            channel_ids = ad.channel_message_ids or {}
            ad_link = None
            for channel, msg_ids in channel_ids.items():
                first_msg_id = msg_ids[0] if isinstance(msg_ids, list) else msg_ids
                if channel.startswith("@"):
                    ad_link = f"https://t.me/{channel[1:]}/{first_msg_id}"
                    break

            # Текст уведомления
            if is_final:
                time_left = "менее 1 часа"
                urgency = "🚨"
            elif days_left == 1:
                time_left = "1 день"
                urgency = "⚠️"
            else:
                time_left = f"{days_left} дня"
                urgency = "⏰"

            title_link = f'<a href="{ad_link}">{ad.title}</a>' if ad_link else ad.title

            text = (
                f"{urgency} <b>Объявление скоро будет снято!</b>\n\n"
                f"📋 {title_link}\n"
                f"⏳ Осталось: {time_left}\n\n"
                f"После истечения срока объявление будет удалено из канала.\n"
                f"Комментарии пользователей к объявлению будут удалены.\n\n"
                f"Объявление можно будет переопубликовать в разделе «Мои объявления»."
            )

            # Кнопки
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Продлить", callback_data=f"extend_ad:{ad.id}"),
                    InlineKeyboardButton(text="❌ Снять", callback_data=f"archive_ad:{ad.id}")
                ]
            ])

            await self.bot.send_message(
                chat_id=user.telegram_id,
                text=text,
                reply_markup=keyboard,
                parse_mode='HTML',
                disable_web_page_preview=True
            )

            # Помечаем уведомление как отправленное
            notifications = ad.notifications_sent or {}
            if is_final:
                notifications["hour_1"] = True
            else:
                notifications[f"day_{days_left}"] = True
            ad.notifications_sent = notifications

            return True

        except TelegramForbiddenError:
            logger.warning(f"[LIFECYCLE] Пользователь {user.telegram_id} заблокировал бота")
            return False
        except Exception as e:
            logger.error(f"[LIFECYCLE] Ошибка отправки уведомления: {e}")
            return False

    # =========================================================================
    # ОБРАБОТКА ИСТЁКШИХ ОБЪЯВЛЕНИЙ
    # =========================================================================

    async def process_expired_ads(self) -> int:
        """
        Обработать объявления с истёкшим сроком публикации.
        """
        now = datetime.utcnow()

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
    # АВТОПОДНЯТИЕ
    # =========================================================================

    async def process_auto_boosts(self) -> int:
        """
        Обработать автоподнятия объявлений.
        """
        now = datetime.utcnow()

        stmt = select(Ad).where(
            and_(
                Ad.status == AdStatus.ACTIVE.value,
                Ad.boost_remaining > 0,
                Ad.next_boost_at != None,
                Ad.next_boost_at <= now
            )
        ).limit(50)

        result = await self.session.execute(stmt)
        ads = result.scalars().all()

        boosted_count = 0
        for ad in ads:
            success, _ = await self.boost_ad(ad)
            if success:
                boosted_count += 1

        if boosted_count > 0:
            await self.session.commit()

        logger.info(f"[LIFECYCLE] Автоподнято: {boosted_count}")
        return boosted_count

    # =========================================================================
    # ПЕРЕМЕЩЕНИЕ НЕАКТИВНЫХ В УДАЛЁННЫЕ (30 ДНЕЙ)
    # =========================================================================

    async def move_inactive_to_deleted(self) -> int:
        """
        Переместить неактивные объявления старше 30 дней в удалённые.

        Неактивные объявления хранятся 30 дней, потом автоматически
        перемещаются в статус DELETED.
        """
        retention_days = 30
        batch_size = 100

        cutoff_date = datetime.utcnow() - timedelta(days=retention_days)

        stmt = select(Ad).where(
            and_(
                Ad.status == AdStatus.INACTIVE.value,
                Ad.archived_to_channel_at != None,
                Ad.archived_to_channel_at < cutoff_date
            )
        ).limit(batch_size)

        result = await self.session.execute(stmt)
        ads = result.scalars().all()

        moved_count = 0
        for ad in ads:
            try:
                ad.status = AdStatus.DELETED.value
                ad.deleted_at = datetime.utcnow()
                moved_count += 1

                logger.info(f"[LIFECYCLE] Объявление {ad.id} перемещено в удалённые (30 дней неактивности)")

            except Exception as e:
                logger.error(f"[LIFECYCLE] Ошибка перемещения {ad.id}: {e}")
                continue

        if moved_count > 0:
            await self.session.commit()

        logger.info(f"[LIFECYCLE] Перемещено в удалённые: {moved_count}")
        return moved_count

    # =========================================================================
    # ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
    # =========================================================================

    def is_republish_free(self, ad: Ad) -> bool:
        """Проверить, бесплатна ли переопубликация"""
        config = AD_LIFECYCLE_CONFIG["republish"]
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


async def get_lifecycle_service(bot: Bot, session: AsyncSession) -> AdLifecycleService:
    """Фабрика для создания сервиса"""
    return AdLifecycleService(bot, session)
