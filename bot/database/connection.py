# bot/database/connection.py
"""Модуль для работы с подключением к базе данных"""

import logging
from typing import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncSession, 
    create_async_engine,
    async_sessionmaker
)
from sqlalchemy.orm import declarative_base
from sqlalchemy.pool import NullPool

from bot.config import settings
from bot.database.models import Base

logger = logging.getLogger(__name__)

# Создание асинхронного движка
engine = create_async_engine(
    settings.database_url,
    echo=settings.DEBUG,
    pool_size=20,
    max_overflow=40,
    pool_pre_ping=True,
    # Используем NullPool для избежания проблем с подключениями
    poolclass=NullPool if settings.DEBUG else None
)

# Создание фабрики сессий
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)

async def init_db():
    """Инициализация базы данных - создание таблиц"""
    try:
        async with engine.begin() as conn:
            # Создаем все таблицы
            await conn.run_sync(Base.metadata.create_all)
            logger.info("База данных успешно инициализирована")
    except Exception as e:
        logger.error(f"Ошибка при инициализации БД: {e}")
        raise

async def close_db():
    """Закрытие соединения с БД"""
    await engine.dispose()
    logger.info("Соединение с БД закрыто")

def get_session_maker():
    """Получить фабрику сессий"""
    return async_session_maker

@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Контекстный менеджер для работы с сессией БД"""
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

async def check_db_connection():
    """Проверка подключения к БД"""
    try:
        async with engine.connect() as conn:
            await conn.execute("SELECT 1")
            return True
    except Exception as e:
        logger.error(f"Ошибка подключения к БД: {e}")
        return False


# Алиас для удобства
get_session = get_db_session