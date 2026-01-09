# bot/main.py
"""Главный файл Telegram бота - с оптимизацией сети для российских VPS"""

import asyncio
import logging
import sys
from pathlib import Path
from aiohttp import web, ClientTimeout

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from redis.asyncio import Redis

# Добавляем корневую директорию в путь
sys.path.append(str(Path(__file__).parent.parent))

from bot.config import settings
from bot.database.connection import init_db
from bot.handlers import (
    start, ad_creation, ad_management, 
    search, profile, admin, payment
)
from bot.middlewares.antiflood import AntiFloodMiddleware
from bot.middlewares.auth import AuthMiddleware
from bot.middlewares.retry import RetryMiddleware
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

# Webhook настройки
WEBHOOK_PATH = "/webhook/bot"
DOMAIN = getattr(settings, 'DOMAIN', 'prodaybot.ru')
WEBHOOK_URL = f"https://{DOMAIN}{WEBHOOK_PATH}"
WEB_SERVER_HOST = "127.0.0.1"
WEB_SERVER_PORT = 8080

async def on_startup(bot: Bot):
    """Действия при запуске бота"""
    logger.info("Запуск webhook бота...")
    await init_db()
    await set_bot_commands(bot)
    
    # Устанавливаем webhook
    await bot.set_webhook(
        url=WEBHOOK_URL,
        drop_pending_updates=True
    )
    logger.info(f"Webhook установлен: {WEBHOOK_URL}")

async def on_shutdown(bot: Bot):
    """Действия при остановке бота"""
    logger.info("Остановка webhook бота...")
    await bot.delete_webhook()


def create_optimized_session() -> AiohttpSession:
    """
    Создаёт оптимизированную сессию для работы с Telegram API.
    Решает проблемы с нестабильной сетью на российских VPS.
    """
    # Короткие таймауты - лучше быстро получить ошибку и повторить
    timeout = ClientTimeout(
        total=30,           # Общий таймаут запроса
        connect=10,         # Таймаут на установку соединения
        sock_read=20,       # Таймаут на чтение данных
        sock_connect=10     # Таймаут на socket connect
    )
    
    return AiohttpSession(timeout=timeout)


async def main():
    """Основная функция запуска бота с webhook"""
    
    # Инициализация Redis для FSM
    redis = Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        db=settings.REDIS_DB,
        password=settings.REDIS_PASSWORD if settings.REDIS_PASSWORD else None,
        decode_responses=True
    )
    
    storage = RedisStorage(redis=redis)
    
    # Создаём оптимизированную сессию
    session = create_optimized_session()
    
    # Инициализация бота с кастомной сессией
    bot = Bot(
        token=settings.BOT_TOKEN,
        session=session,
        default=DefaultBotProperties(
            parse_mode=ParseMode.HTML
        )
    )
    
    dp = Dispatcher(storage=storage)
    
    # Регистрация middleware (RetryMiddleware первым - для перехвата сетевых ошибок)
    dp.message.middleware(RetryMiddleware(max_retries=3, base_delay=1.0))
    dp.callback_query.middleware(RetryMiddleware(max_retries=3, base_delay=1.0))
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
    
    # Регистрация хуков
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    
    # Создаём веб-приложение
    app = web.Application()
    
    # Настраиваем webhook handler
    webhook_requests_handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot
    )
    webhook_requests_handler.register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)
    
    # Запуск сервера
    logger.info(f"Запуск сервера на {WEB_SERVER_HOST}:{WEB_SERVER_PORT}")
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, WEB_SERVER_HOST, WEB_SERVER_PORT)
    
    try:
        await site.start()
        # Держим сервер запущенным
        await asyncio.Event().wait()
    except Exception as e:
        logger.error(f"Ошибка сервера: {e}")
        raise
    finally:
        await runner.cleanup()
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
