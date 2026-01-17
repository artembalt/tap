# bot/main.py
"""Telegram бот - webhook режим с retry"""

import asyncio
import logging
import sys
from pathlib import Path
from datetime import timedelta
from aiohttp import web, ClientTimeout

from aiogram import Bot, Dispatcher, BaseMiddleware
from aiogram.types import Update, TelegramObject, Message, CallbackQuery
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiogram.exceptions import TelegramNetworkError, TelegramRetryAfter
from redis.asyncio import Redis

sys.path.append(str(Path(__file__).parent.parent))

from bot.config import settings
from bot.database.connection import init_db
from bot.handlers import start, ad_creation, ad_management, search, profile, admin, payment, comments, favorites
from bot.handlers import billing as billing_handler
from bot.middlewares.antiflood import AntiFloodMiddleware
from bot.middlewares.auth import AuthMiddleware
from bot.utils.commands import set_bot_commands
from bot.database.connection import get_session
from bot.services.exchange_rate import ExchangeRateService
from bot.services.robokassa import (
    verify_result_signature, parse_amount, parse_inv_id
)
from bot.services.billing import BillingService
from bot.database.models import User, Payment, PaymentStatus

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler('logs/bot.log'), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Webhook конфигурация из settings
WEBHOOK_PATH = settings.WEBHOOK_PATH
WEBHOOK_URL = settings.webhook_url
WEB_SERVER_HOST = settings.WEBHOOK_HOST
WEB_SERVER_PORT = settings.WEBHOOK_PORT


class RetryMiddleware(BaseMiddleware):
    """Middleware для обработки rate limit (retry только для TelegramRetryAfter)"""

    async def __call__(self, handler, event: TelegramObject, data: dict):
        max_retries = 3

        for attempt in range(max_retries):
            try:
                return await handler(event, data)
            except TelegramRetryAfter as e:
                logger.warning(f"Rate limit, ждём {e.retry_after}с")
                await asyncio.sleep(e.retry_after)
            except TelegramNetworkError as e:
                # НЕ повторяем весь handler при сетевой ошибке -
                # это вызывает дублирование сообщений и зависание
                logger.error(f"Сетевая ошибка: {e}")
                raise


class RawUpdateLogger(BaseMiddleware):
    """Логирование входящих update"""
    
    async def __call__(self, handler, event: Update, data: dict):
        if hasattr(event, 'message') and event.message:
            logger.info(f"!!! RAW MESSAGE: text='{event.message.text}' from_user={event.message.from_user.id}")
        elif hasattr(event, 'callback_query') and event.callback_query:
            logger.info(f"!!! RAW CALLBACK: data='{event.callback_query.data}' from_user={event.callback_query.from_user.id}")
        return await handler(event, data)


async def keepalive_task(bot: Bot):
    """Фоновая задача для поддержания соединения с Telegram API"""
    while True:
        await asyncio.sleep(15)  # Каждые 15 секунд - держим соединение горячим
        try:
            await bot.get_me()
        except Exception:
            pass  # Игнорируем ошибки - главное держать соединение активным


async def exchange_rate_updater():
    """
    Фоновая задача для обновления курса валют.
    Обновляет курс Stars каждый день в 4:00 МСК (1:00 UTC).
    """
    from datetime import datetime, time
    import pytz

    msk = pytz.timezone('Europe/Moscow')

    while True:
        try:
            now = datetime.now(msk)
            # Следующее обновление в 4:00 МСК
            target_time = time(4, 0)
            target_dt = datetime.combine(now.date(), target_time, tzinfo=msk)

            if now.time() >= target_time:
                # Если уже прошло 4:00 сегодня - ждём до завтра
                target_dt = datetime.combine(
                    now.date() + timedelta(days=1),
                    target_time,
                    tzinfo=msk
                )

            # Сколько секунд до следующего обновления
            wait_seconds = (target_dt - now).total_seconds()
            logger.info(f"Следующее обновление курса через {wait_seconds/3600:.1f} часов")

            await asyncio.sleep(wait_seconds)

            # Обновляем курс
            async with get_session() as session:
                service = ExchangeRateService(session)
                success, message = await service.update_rate()
                logger.info(f"Обновление курса: {message}")
                if success:
                    await session.commit()

        except Exception as e:
            logger.error(f"Ошибка в exchange_rate_updater: {e}")
            # При ошибке ждём 1 час и пробуем снова
            await asyncio.sleep(3600)


async def on_startup(bot: Bot):
    logger.info("=" * 60)
    logger.info("ЗАПУСК БОТА")
    logger.info("=" * 60)

    await init_db()
    await set_bot_commands(bot)

    try:
        me = await bot.get_me()
        logger.info(f"Бот: @{me.username}")
    except Exception as e:
        logger.warning(f"Прогрев: {e}")

    await bot.set_webhook(
        url=WEBHOOK_URL,
        drop_pending_updates=True,
        allowed_updates=["message", "callback_query", "pre_checkout_query"]
    )
    logger.info(f"Webhook: {WEBHOOK_URL}")

    # Запускаем фоновые задачи
    asyncio.create_task(keepalive_task(bot))
    asyncio.create_task(exchange_rate_updater())

    # Обновляем курс при старте если его нет
    try:
        async with get_session() as session:
            service = ExchangeRateService(session)
            success, message = await service.update_rate()
            logger.info(f"Инициализация курса: {message}")
            if success:
                await session.commit()
    except Exception as e:
        logger.warning(f"Не удалось обновить курс при старте: {e}")


async def on_shutdown(bot: Bot):
    logger.info("Остановка бота...")
    await bot.delete_webhook()


# =============================================================================
# ROBOKASSA WEBHOOK HANDLERS
# =============================================================================

# Глобальная переменная для бота (нужна для отправки уведомлений)
_bot: Bot = None


async def robokassa_result_handler(request: web.Request) -> web.Response:
    """
    Result URL — уведомление об успешной оплате от Robokassa.
    Вызывается сервером Robokassa после оплаты.
    Должен вернуть OK{InvId} при успехе.
    """
    try:
        # Robokassa шлёт POST
        data = await request.post()

        out_sum = data.get("OutSum", "")
        inv_id = data.get("InvId", "")
        signature = data.get("SignatureValue", "")
        shp_user_id = data.get("Shp_user_id", "")

        logger.info(
            f"Robokassa Result: inv_id={inv_id}, out_sum={out_sum}, user_id={shp_user_id}"
        )

        # Проверяем подпись
        if not verify_result_signature(out_sum, inv_id, signature, shp_user_id):
            logger.error(f"Robokassa: неверная подпись для inv_id={inv_id}")
            return web.Response(text="bad signature", status=400)

        amount = parse_amount(out_sum)
        payment_inv_id = parse_inv_id(inv_id)
        user_id = int(shp_user_id) if shp_user_id else 0

        if not user_id or not amount:
            logger.error(f"Robokassa: некорректные данные inv_id={inv_id}")
            return web.Response(text="bad data", status=400)

        # Обрабатываем платёж
        async with get_session() as session:
            # Получаем платёж по inv_id
            from sqlalchemy import select
            result = await session.execute(
                select(Payment).where(Payment.payment_id == str(payment_inv_id))
            )
            payment = result.scalar_one_or_none()

            if not payment:
                logger.error(f"Robokassa: платёж не найден inv_id={inv_id}")
                return web.Response(text="payment not found", status=404)

            if payment.status == PaymentStatus.SUCCESS.value:
                # Уже обработан (дубликат уведомления)
                logger.info(f"Robokassa: платёж уже обработан inv_id={inv_id}")
                return web.Response(text=f"OK{inv_id}")

            # Получаем пользователя
            user = await session.get(User, user_id)
            if not user:
                logger.error(f"Robokassa: пользователь не найден user_id={user_id}")
                return web.Response(text="user not found", status=404)

            # Обновляем статус платежа
            payment.status = PaymentStatus.SUCCESS.value
            from datetime import datetime
            payment.paid_at = datetime.utcnow()

            # Пополняем баланс
            billing = BillingService(session)
            await billing.deposit(
                user=user,
                amount=amount,
                currency="RUB",
                payment=payment,
                description=f"Пополнение через Robokassa +{amount:.0f} ₽"
            )

            await session.commit()

            logger.info(
                f"Robokassa: платёж успешен inv_id={inv_id}, "
                f"user_id={user_id}, amount={amount}"
            )

            # Отправляем уведомление пользователю
            if _bot:
                try:
                    await _bot.send_message(
                        user_id,
                        f"✅ <b>Платёж получен!</b>\n\n"
                        f"Баланс пополнен на {amount:.0f} ₽\n\n"
                        f"💰 Текущий баланс: {user.balance_rub:.0f} ₽"
                    )
                except Exception as e:
                    logger.warning(f"Не удалось отправить уведомление: {e}")

        return web.Response(text=f"OK{inv_id}")

    except Exception as e:
        logger.error(f"Robokassa Result error: {e}")
        return web.Response(text="error", status=500)


async def robokassa_success_handler(request: web.Request) -> web.Response:
    """
    Success URL — редирект пользователя после успешной оплаты.
    Показываем страницу с благодарностью.
    """
    inv_id = request.query.get("InvId", "")
    out_sum = request.query.get("OutSum", "")

    logger.info(f"Robokassa Success: inv_id={inv_id}, out_sum={out_sum}")

    # Возвращаем HTML страницу
    html = f"""
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Оплата успешна</title>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                display: flex;
                justify-content: center;
                align-items: center;
                min-height: 100vh;
                margin: 0;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            }}
            .card {{
                background: white;
                padding: 40px;
                border-radius: 16px;
                box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                text-align: center;
                max-width: 400px;
            }}
            .icon {{ font-size: 64px; margin-bottom: 20px; }}
            h1 {{ color: #333; margin: 0 0 10px 0; }}
            p {{ color: #666; margin: 10px 0; }}
            .amount {{ font-size: 24px; font-weight: bold; color: #667eea; }}
            .btn {{
                display: inline-block;
                margin-top: 20px;
                padding: 12px 24px;
                background: #667eea;
                color: white;
                text-decoration: none;
                border-radius: 8px;
                font-weight: 500;
            }}
        </style>
    </head>
    <body>
        <div class="card">
            <div class="icon">✅</div>
            <h1>Оплата успешна!</h1>
            <p class="amount">{out_sum} ₽</p>
            <p>Баланс пополнен. Вернитесь в бот.</p>
            <a href="https://t.me/proday_main_bot" class="btn">Открыть бот</a>
        </div>
    </body>
    </html>
    """
    return web.Response(text=html, content_type="text/html")


async def robokassa_fail_handler(request: web.Request) -> web.Response:
    """
    Fail URL — редирект при отмене/ошибке оплаты.
    """
    inv_id = request.query.get("InvId", "")

    logger.info(f"Robokassa Fail: inv_id={inv_id}")

    html = """
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Оплата отменена</title>
        <style>
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                display: flex;
                justify-content: center;
                align-items: center;
                min-height: 100vh;
                margin: 0;
                background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
            }
            .card {
                background: white;
                padding: 40px;
                border-radius: 16px;
                box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                text-align: center;
                max-width: 400px;
            }
            .icon { font-size: 64px; margin-bottom: 20px; }
            h1 { color: #333; margin: 0 0 10px 0; }
            p { color: #666; }
            .btn {
                display: inline-block;
                margin-top: 20px;
                padding: 12px 24px;
                background: #f5576c;
                color: white;
                text-decoration: none;
                border-radius: 8px;
                font-weight: 500;
            }
        </style>
    </head>
    <body>
        <div class="card">
            <div class="icon">❌</div>
            <h1>Оплата отменена</h1>
            <p>Платёж не был завершён.<br>Вы можете попробовать снова в боте.</p>
            <a href="https://t.me/proday_main_bot" class="btn">Вернуться в бот</a>
        </div>
    </body>
    </html>
    """
    return web.Response(text=html, content_type="text/html")


async def main():
    global _bot

    redis = Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        db=settings.REDIS_DB,
        password=settings.REDIS_PASSWORD if settings.REDIS_PASSWORD else None,
        decode_responses=True
    )
    storage = RedisStorage(redis=redis)
    
    # Оптимальные таймауты - баланс между скоростью и надёжностью
    timeout = ClientTimeout(
        total=10,      # Общий таймаут 10 сек
        connect=5,     # Подключение 5 сек
        sock_read=8,   # Чтение 8 сек
        sock_connect=5 # Сокет 5 сек
    )

    session = AiohttpSession(timeout=timeout)
    # Настраиваем connector
    session._connector_init.update({
        'keepalive_timeout': 15,
        'enable_cleanup_closed': True,
    })
    bot = Bot(
        token=settings.BOT_TOKEN,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )

    # Сохраняем бота для Robokassa уведомлений
    _bot = bot

    dp = Dispatcher(storage=storage)

    # Middleware
    antiflood = AntiFloodMiddleware(
        rate_limit=5,        # 5 сообщений
        period=10,           # за 10 секунд
        block_duration=30,   # блокировка на 30 сек
        redis=redis
    )
    dp.update.outer_middleware(RawUpdateLogger())
    dp.message.outer_middleware(RetryMiddleware())
    dp.callback_query.outer_middleware(RetryMiddleware())
    dp.message.middleware(antiflood)
    dp.callback_query.middleware(antiflood)
    dp.message.middleware(AuthMiddleware())
    
    # Роутеры
    dp.include_router(start.router)
    dp.include_router(ad_creation.router)
    dp.include_router(ad_management.router)
    dp.include_router(search.router)
    dp.include_router(profile.router)
    dp.include_router(payment.router)
    dp.include_router(billing_handler.router)  # Биллинг (баланс, история)
    dp.include_router(admin.router)
    dp.include_router(comments.router)  # Мониторинг комментариев
    dp.include_router(favorites.router)  # Избранное
    
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    
    app = web.Application()
    webhook_requests_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    webhook_requests_handler.register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)

    # Robokassa webhooks
    app.router.add_post("/webhook/robokassa/result", robokassa_result_handler)
    app.router.add_get("/webhook/robokassa/success", robokassa_success_handler)
    app.router.add_get("/webhook/robokassa/fail", robokassa_fail_handler)

    logger.info(f"Сервер: {WEB_SERVER_HOST}:{WEB_SERVER_PORT}")
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, WEB_SERVER_HOST, WEB_SERVER_PORT)
    
    try:
        await site.start()
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()
        await bot.session.close()
        await redis.aclose()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен")