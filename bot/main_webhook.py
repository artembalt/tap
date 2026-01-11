# bot/main_webhook.py
"""Webhook версия бота для Production"""

import asyncio
import logging
import sys
import os
from pathlib import Path

from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
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

# Логирование
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
WEBHOOK_HOST = "https://prodaybot.ru"
WEBHOOK_PATH = "/webhook/bot"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"

WEBAPP_HOST = "127.0.0.1"
WEBAPP_PORT = 8080


async def on_startup(bot: Bot):
    """Действия при запуске"""
    logger.info("Запуск webhook бота...")
    
    await init_db()
    await set_bot_commands(bot)
    
    # Установка webhook
    await bot.set_webhook(
        url=WEBHOOK_URL,
        drop_pending_updates=True,
        allowed_updates=["message", "callback_query"]
    )
    logger.info(f"Webhook установлен: {WEBHOOK_URL}")
    
    for admin_id in settings.ADMIN_IDS:
        try:
            await bot.send_message(admin_id, "✅ Бот запущен (webhook режим)")
        except Exception as e:
            logger.error(f"Ошибка уведомления админа {admin_id}: {e}")


async def on_shutdown(bot: Bot):
    """Действия при остановке"""
    logger.info("Остановка webhook бота...")
    
    await bot.delete_webhook()
    
    for admin_id in settings.ADMIN_IDS:
        try:
            await bot.send_message(admin_id, "⚠️ Бот остановлен")
        except Exception as e:
            logger.debug(f"Не удалось уведомить админа {admin_id}: {e}")
    
    await bot.session.close()


async def health_check(request):
    """Health check endpoint"""
    return web.Response(text="OK", status=200)


def main():
    """Запуск webhook бота"""
    
    # Redis
    redis = Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        db=settings.REDIS_DB,
        password=settings.REDIS_PASSWORD if settings.REDIS_PASSWORD else None,
        decode_responses=True
    )
    
    storage = RedisStorage(redis=redis)
    
    # Бот
    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    
    # Диспетчер
    dp = Dispatcher(storage=storage)
    
    # Middleware
    dp.update.outer_middleware(RetryMiddleware(max_retries=3, retry_delay=1.0))
    dp.message.middleware(AntiFloodMiddleware())
    dp.callback_query.middleware(AntiFloodMiddleware())
    dp.message.middleware(AuthMiddleware())
    
    # Роутеры
    dp.include_router(start.router)
    dp.include_router(ad_creation.router)
    dp.include_router(ad_management.router)
    dp.include_router(search.router)
    dp.include_router(profile.router)
    dp.include_router(payment.router)
    dp.include_router(admin.router)
    
    # События
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    
    # Веб-приложение
    app = web.Application()
    app.router.add_get("/health", health_check)
    
    # Webhook handler
    webhook_requests_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    webhook_requests_handler.register(app, path=WEBHOOK_PATH)
    
    setup_application(app, dp, bot=bot)
    
    # Запуск
    logger.info(f"Запуск сервера на {WEBAPP_HOST}:{WEBAPP_PORT}")
    web.run_app(app, host=WEBAPP_HOST, port=WEBAPP_PORT)


if __name__ == "__main__":
    main()