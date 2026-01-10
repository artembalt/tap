# bot/database/queries.py
"""Запросы к базе данных - ОПТИМИЗИРОВАННАЯ ВЕРСИЯ"""

import logging
from typing import Optional, List
from datetime import datetime, timedelta
from sqlalchemy import select, update, delete, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.connection import get_db_session
from bot.database.models import User, Ad, AdStatus, Payment, Report, Review

logger = logging.getLogger(__name__)

# =============================================================================
# USER QUERIES
# =============================================================================

class UserQueries:
    """Запросы для работы с пользователями"""
    
    @staticmethod
    async def get_user(telegram_id: int) -> Optional[User]:
        """Получить пользователя по telegram_id"""
        try:
            async with get_db_session() as session:
                return await session.get(User, telegram_id)
        except Exception as e:
            logger.error(f"Error getting user {telegram_id}: {e}")
            return None
    
    @staticmethod
    async def create_user(
        telegram_id: int, 
        username: Optional[str] = None,
        first_name: Optional[str] = None, 
        last_name: Optional[str] = None
    ) -> User:
        """Создать нового пользователя"""
        async with get_db_session() as session:
            user = User(
                telegram_id=telegram_id,
                username=username,
                first_name=first_name,
                last_name=last_name,
                created_at=datetime.utcnow(),
                last_activity=datetime.utcnow()
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            logger.info(f"Created new user: {telegram_id}")
            return user
    
    @staticmethod
    async def get_or_create_user(
        telegram_id: int, 
        username: Optional[str] = None,
        first_name: Optional[str] = None, 
        last_name: Optional[str] = None
    ) -> User:
        """Получить или создать пользователя"""
        user = await UserQueries.get_user(telegram_id)
        if not user:
            user = await UserQueries.create_user(telegram_id, username, first_name, last_name)
        else:
            # Обновляем последнюю активность
            await UserQueries.update_last_activity(telegram_id)
        return user
    
    @staticmethod
    async def update_user(telegram_id: int, **kwargs) -> bool:
        """Обновить данные пользователя"""
        try:
            async with get_db_session() as session:
                stmt = (
                    update(User)
                    .where(User.telegram_id == telegram_id)
                    .values(**kwargs)
                )
                await session.execute(stmt)
                await session.commit()
                return True
        except Exception as e:
            logger.error(f"Error updating user {telegram_id}: {e}")
            return False
    
    @staticmethod
    async def update_last_activity(telegram_id: int):
        """Обновить время последней активности"""
        await UserQueries.update_user(telegram_id, last_activity=datetime.utcnow())
    
    @staticmethod
    async def increment_warnings(telegram_id: int) -> int:
        """Увеличить счетчик предупреждений"""
        try:
            async with get_db_session() as session:
                user = await session.get(User, telegram_id)
                if user:
                    user.warnings_count += 1
                    await session.commit()
                    return user.warnings_count
        except Exception as e:
            logger.error(f"Error incrementing warnings for {telegram_id}: {e}")
        return 0
    
    @staticmethod
    async def ban_user(telegram_id: int, reason: str, until: Optional[datetime] = None):
        """Забанить пользователя"""
        await UserQueries.update_user(
            telegram_id,
            is_banned=True,
            ban_reason=reason,
            banned_until=until
        )
        logger.warning(f"User {telegram_id} banned: {reason}")
    
    @staticmethod
    async def unban_user(telegram_id: int):
        """Разбанить пользователя"""
        await UserQueries.update_user(
            telegram_id,
            is_banned=False,
            ban_reason=None,
            banned_until=None
        )
        logger.info(f"User {telegram_id} unbanned")
    
    @staticmethod
    async def is_user_banned(telegram_id: int) -> bool:
        """Проверить, забанен ли пользователь"""
        user = await UserQueries.get_user(telegram_id)
        if not user or not user.is_banned:
            return False
        
        # Проверяем срок бана
        if user.banned_until and user.banned_until < datetime.utcnow():
            await UserQueries.unban_user(telegram_id)
            return False
        
        return True
    
    @staticmethod
    async def get_user_stats(telegram_id: int) -> dict:
        """Получить статистику пользователя"""
        user = await UserQueries.get_user(telegram_id)
        if not user:
            return {}
        
        return {
            "total_ads": user.total_ads,
            "active_ads": user.active_ads,
            "completed_deals": user.completed_deals,
            "rating": user.rating,
            "reviews_count": user.reviews_count,
            "is_premium": user.is_premium,
            "balance": user.balance
        }

# =============================================================================
# AD QUERIES
# =============================================================================

class AdQueries:
    """Запросы для работы с объявлениями"""
    
    @staticmethod
    async def get_ad(ad_id: str) -> Optional[Ad]:
        """Получить объявление по ID"""
        try:
            async with get_db_session() as session:
                stmt = select(Ad).where(Ad.id == ad_id)
                result = await session.execute(stmt)
                return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error getting ad {ad_id}: {e}")
            return None
    
    @staticmethod
    async def get_user_ads(
        telegram_id: int, 
        status: Optional[str] = None,
        limit: int = 10,  # УМЕНЬШЕНО с 50 до 10!
        offset: int = 0
    ) -> List[Ad]:
        """Получить объявления пользователя с пагинацией"""
        try:
            async with get_db_session() as session:
                stmt = select(Ad).where(Ad.user_id == telegram_id)
                
                if status:
                    stmt = stmt.where(Ad.status == status)
                else:
                    # По умолчанию показываем активные, на модерации и архивные
                    stmt = stmt.where(Ad.status.in_([
                        AdStatus.ACTIVE.value, 
                        AdStatus.PENDING.value,
                        AdStatus.ARCHIVED.value
                    ]))
                
                stmt = stmt.order_by(Ad.created_at.desc()).limit(limit).offset(offset)
                
                result = await session.execute(stmt)
                return list(result.scalars().all())
        except Exception as e:
            logger.error(f"Error getting user ads {telegram_id}: {e}")
            return []
    
    @staticmethod
    async def get_user_ads_count(telegram_id: int) -> int:
        """
        Получить количество объявлений пользователя (быстрый запрос COUNT).
        Используется для пагинации.
        """
        try:
            async with get_db_session() as session:
                stmt = (
                    select(func.count(Ad.id))
                    .where(
                        and_(
                            Ad.user_id == telegram_id,
                            Ad.status.in_([
                                AdStatus.ACTIVE.value, 
                                AdStatus.PENDING.value,
                                AdStatus.ARCHIVED.value
                            ])
                        )
                    )
                )
                result = await session.execute(stmt)
                return result.scalar() or 0
        except Exception as e:
            logger.error(f"Error counting user ads {telegram_id}: {e}")
            return 0
    
    @staticmethod
    async def get_user_ads_count_today(telegram_id: int) -> int:
        """Получить количество объявлений пользователя за сегодня"""
        try:
            async with get_db_session() as session:
                today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
                
                stmt = (
                    select(func.count(Ad.id))
                    .where(
                        and_(
                            Ad.user_id == telegram_id,
                            Ad.created_at >= today_start
                        )
                    )
                )
                
                result = await session.execute(stmt)
                return result.scalar() or 0
        except Exception as e:
            logger.error(f"Error counting today's ads for {telegram_id}: {e}")
            return 0
    
    @staticmethod
    async def create_ad(ad_data: dict) -> Optional[Ad]:
        """Создать объявление"""
        try:
            async with get_db_session() as session:
                ad = Ad(**ad_data)
                session.add(ad)
                await session.commit()
                await session.refresh(ad)
                
                # Увеличиваем счетчик объявлений у пользователя
                await AdQueries._increment_user_ad_count(ad.user_id)
                
                logger.info(f"Created ad {ad.id} for user {ad.user_id}")
                return ad
        except Exception as e:
            logger.error(f"Error creating ad: {e}")
            return None
    
    @staticmethod
    async def update_ad(ad_id: str, **kwargs) -> bool:
        """Обновить объявление"""
        try:
            async with get_db_session() as session:
                stmt = (
                    update(Ad)
                    .where(Ad.id == ad_id)
                    .values(updated_at=datetime.utcnow(), **kwargs)
                )
                await session.execute(stmt)
                await session.commit()
                logger.info(f"Updated ad {ad_id}")
                return True
        except Exception as e:
            logger.error(f"Error updating ad {ad_id}: {e}")
            return False
    
    @staticmethod
    async def delete_ad(ad_id: str) -> bool:
        """Удалить объявление (мягкое удаление)"""
        return await AdQueries.update_ad(ad_id, status=AdStatus.DELETED.value)
    
    @staticmethod
    async def deactivate_ad(ad_id: str) -> bool:
        """Деактивировать объявление (архивировать)"""
        return await AdQueries.update_ad(ad_id, status=AdStatus.ARCHIVED.value)
    
    @staticmethod
    async def activate_ad(ad_id: str) -> bool:
        """Активировать объявление"""
        return await AdQueries.update_ad(ad_id, status=AdStatus.ACTIVE.value)
    
    @staticmethod
    async def search_ads(
        region: Optional[str] = None,
        category: Optional[str] = None,
        query: Optional[str] = None,
        price_min: Optional[float] = None,
        price_max: Optional[float] = None,
        limit: int = 20,
        offset: int = 0
    ) -> List[Ad]:
        """Поиск объявлений с фильтрами"""
        try:
            async with get_db_session() as session:
                stmt = select(Ad).where(Ad.status == AdStatus.ACTIVE.value)
                
                if region:
                    stmt = stmt.where(Ad.region == region)
                
                if category:
                    stmt = stmt.where(Ad.category == category)
                
                if query:
                    # Поиск по заголовку и описанию
                    search_pattern = f"%{query.lower()}%"
                    stmt = stmt.where(
                        or_(
                            func.lower(Ad.title).like(search_pattern),
                            func.lower(Ad.description).like(search_pattern)
                        )
                    )
                
                if price_min is not None:
                    stmt = stmt.where(Ad.price >= price_min)
                
                if price_max is not None:
                    stmt = stmt.where(Ad.price <= price_max)
                
                stmt = stmt.order_by(Ad.created_at.desc()).limit(limit).offset(offset)
                
                result = await session.execute(stmt)
                return list(result.scalars().all())
        except Exception as e:
            logger.error(f"Error searching ads: {e}")
            return []
    
    @staticmethod
    async def increment_views(ad_id: str):
        """Увеличить счетчик просмотров"""
        try:
            async with get_db_session() as session:
                ad = await session.get(Ad, ad_id)
                if ad:
                    ad.views_count += 1
                    await session.commit()
        except Exception as e:
            logger.error(f"Error incrementing views for {ad_id}: {e}")
    
    @staticmethod
    async def increment_contacts(ad_id: str):
        """Увеличить счетчик контактов"""
        try:
            async with get_db_session() as session:
                ad = await session.get(Ad, ad_id)
                if ad:
                    ad.contacts_count += 1
                    await session.commit()
        except Exception as e:
            logger.error(f"Error incrementing contacts for {ad_id}: {e}")
    
    @staticmethod
    async def _increment_user_ad_count(user_id: int):
        """Увеличить счетчик объявлений у пользователя"""
        try:
            async with get_db_session() as session:
                user = await session.get(User, user_id)
                if user:
                    user.total_ads += 1
                    user.active_ads += 1
                    await session.commit()
        except Exception as e:
            logger.error(f"Error incrementing user ad count: {e}")
    
    @staticmethod
    async def _decrement_user_active_ads(user_id: int):
        """Уменьшить счетчик активных объявлений у пользователя"""
        try:
            async with get_db_session() as session:
                user = await session.get(User, user_id)
                if user and user.active_ads > 0:
                    user.active_ads -= 1
                    await session.commit()
        except Exception as e:
            logger.error(f"Error decrementing user active ads: {e}")

# =============================================================================
# FAVORITES QUERIES
# =============================================================================

class FavoritesQueries:
    """Запросы для работы с избранным"""
    
    @staticmethod
    async def add_to_favorites(user_id: int, ad_id: str) -> bool:
        """Добавить объявление в избранное"""
        try:
            async with get_db_session() as session:
                user = await session.get(User, user_id)
                ad = await session.get(Ad, ad_id)
                
                if user and ad:
                    if ad not in user.favorites:
                        user.favorites.append(ad)
                        ad.favorites_count += 1
                        await session.commit()
                        return True
        except Exception as e:
            logger.error(f"Error adding to favorites: {e}")
        return False
    
    @staticmethod
    async def remove_from_favorites(user_id: int, ad_id: str) -> bool:
        """Удалить объявление из избранного"""
        try:
            async with get_db_session() as session:
                user = await session.get(User, user_id)
                ad = await session.get(Ad, ad_id)
                
                if user and ad:
                    if ad in user.favorites:
                        user.favorites.remove(ad)
                        if ad.favorites_count > 0:
                            ad.favorites_count -= 1
                        await session.commit()
                        return True
        except Exception as e:
            logger.error(f"Error removing from favorites: {e}")
        return False
    
    @staticmethod
    async def get_user_favorites(user_id: int, limit: int = 50) -> List[Ad]:
        """Получить избранные объявления пользователя"""
        try:
            async with get_db_session() as session:
                user = await session.get(User, user_id)
                if user:
                    # Возвращаем только активные объявления из избранного
                    return [ad for ad in user.favorites if ad.status == AdStatus.ACTIVE.value][:limit]
        except Exception as e:
            logger.error(f"Error getting favorites: {e}")
        return []
    
    @staticmethod
    async def is_in_favorites(user_id: int, ad_id: str) -> bool:
        """Проверить, есть ли объявление в избранном"""
        try:
            async with get_db_session() as session:
                user = await session.get(User, user_id)
                if user:
                    return any(str(ad.id) == ad_id for ad in user.favorites)
        except Exception as e:
            logger.error(f"Error checking favorites: {e}")
        return False
