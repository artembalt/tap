# bot/main.py
"""Главный файл Telegram бота для платформы объявлений"""

import asyncio
import logging
import sys
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from redis.asyncio import Redis

# Добавляем корневую директорию в путь
sys.path.append(str(Path(__file__).parent.parent))

from bot.config import settings
from bot.database.connection import init_db, get_session_maker
from bot.handlers import (
    start, ad_creation, ad_management, 
    search, profile, admin, payment
)
from bot.middlewares.antiflood import AntiFloodMiddleware
from bot.middlewares.auth import AuthMiddleware
from bot.utils.commands import set_bot_commands

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

async def on_startup(bot: Bot):
    """Действия при запуске бота"""
    logger.info("Бот запущен")
    
    # Инициализация базы данных
    await init_db()
    
    # Установка команд бота
    await set_bot_commands(bot)
    
    # Отправка уведомления админам
    for admin_id in settings.ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id, 
                "✅ Бот успешно запущен!"
            )
        except Exception as e:
            logger.error(f"Не удалось отправить уведомление админу {admin_id}: {e}")

async def on_shutdown(bot: Bot):
    """Действия при остановке бота"""
    logger.info("Бот остановлен")
    
    # Закрытие соединений с БД
    # await close_db_connections()
    
    # Отправка уведомления админам
    for admin_id in settings.ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id, 
                "⚠️ Бот остановлен"
            )
        except Exception as e:
            logger.error(f"Не удалось отправить уведомление админу {admin_id}: {e}")

async def main():
    """Основная функция запуска бота"""
    
    # Инициализация Redis для FSM
    redis = Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        db=settings.REDIS_DB,
        password=settings.REDIS_PASSWORD if settings.REDIS_PASSWORD else None,
        decode_responses=True
    )
    
    # Создание хранилища состояний
    storage = RedisStorage(redis=redis)
    
    # Инициализация бота и диспетчера
    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(
            parse_mode=ParseMode.HTML
        )
    )
    
    dp = Dispatcher(storage=storage)
    
    # Регистрация middleware
    dp.message.middleware(AntiFloodMiddleware())
    dp.callback_query.middleware(AntiFloodMiddleware())
    dp.message.middleware(AuthMiddleware())
    
    # Регистрация обработчиков
    dp.include_router(start.router)
    dp.include_router(ad_creation.router)
    dp.include_router(ad_management.router)
    dp.include_router(search.router)
    dp.include_router(profile.router)
    dp.include_router(payment.router)
    dp.include_router(admin.router)
    
    # Регистрация startup и shutdown хуков
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    
    # Запуск бота
    try:
        logger.info("Запуск бота...")
        await dp.start_polling(
            bot,
            allowed_updates=dp.resolve_used_update_types(),
            drop_pending_updates=True
        )
    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {e}")
        raise
    finally:
        await bot.session.close()
        await redis.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        sys.exit(1)