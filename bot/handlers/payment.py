# bot/handlers/payment.py
"""
Обработчики платежей.

Поддержка:
- Telegram Stars (встроенные платежи)
- Внешние платёжные системы (YooKassa и др.)

Telegram Stars:
- Пополнение баланса через Stars
- Покупка услуг напрямую за Stars
"""

import logging
from datetime import datetime
from typing import Optional

from aiogram import Router, F, Bot
from aiogram.types import (
    Message, CallbackQuery, LabeledPrice,
    PreCheckoutQuery, ContentType
)
from aiogram.filters import Command
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.connection import get_session
from bot.database.models import User, Payment, PaymentStatus
from bot.services.billing import BillingService, format_balance
from bot.services.exchange_rate import ExchangeRateService
from bot.config.pricing import PAID_SERVICES, ACCOUNT_TYPES
from bot.keyboards.billing import (
    get_deposit_keyboard,
    get_deposit_amount_keyboard,
    get_currency_choice_keyboard,
)

logger = logging.getLogger(__name__)

router = Router(name='payment')


# =============================================================================
# TELEGRAM STARS - ПОПОЛНЕНИЕ БАЛАНСА
# =============================================================================

@router.callback_query(F.data == "deposit_stars")
async def deposit_stars_start(callback: CallbackQuery):
    """Начало пополнения баланса через Stars"""
    await callback.message.edit_text(
        "⭐ <b>Пополнение баланса Stars</b>\n\n"
        "Выберите количество Stars для пополнения:",
        reply_markup=get_deposit_amount_keyboard("stars")
    )
    await callback.answer()


@router.callback_query(F.data.startswith("deposit_stars_"))
async def deposit_stars_amount(callback: CallbackQuery, bot: Bot):
    """Создание инвойса для оплаты Stars"""
    amount = int(callback.data.split("_")[-1])

    # Создаём инвойс для Telegram Stars
    # Currency XTR = Telegram Stars
    prices = [LabeledPrice(label=f"Пополнение {amount} ⭐", amount=amount)]

    try:
        await bot.send_invoice(
            chat_id=callback.from_user.id,
            title=f"Пополнение баланса на {amount} ⭐",
            description="Пополнение баланса в боте @proday_main_bot",
            payload=f"deposit_stars_{amount}",
            currency="XTR",  # Telegram Stars
            prices=prices,
            provider_token="",  # Пустой для Telegram Stars
        )
        await callback.message.delete()
    except Exception as e:
        logger.error(f"Ошибка создания инвойса Stars: {e}")
        await callback.message.edit_text(
            "❌ Не удалось создать платёж. Попробуйте позже."
        )

    await callback.answer()


@router.pre_checkout_query()
async def process_pre_checkout(pre_checkout: PreCheckoutQuery, bot: Bot):
    """Подтверждение платежа (pre-checkout)"""
    # Telegram требует ответить в течение 10 секунд
    # Здесь можно проверить наличие товара, валидность и т.д.

    logger.info(
        f"Pre-checkout: user={pre_checkout.from_user.id}, "
        f"payload={pre_checkout.invoice_payload}, "
        f"amount={pre_checkout.total_amount} {pre_checkout.currency}"
    )

    # Подтверждаем платёж
    await bot.answer_pre_checkout_query(pre_checkout.id, ok=True)


@router.message(F.content_type == ContentType.SUCCESSFUL_PAYMENT)
async def process_successful_payment(message: Message):
    """Обработка успешного платежа"""
    payment_info = message.successful_payment

    logger.info(
        f"Successful payment: user={message.from_user.id}, "
        f"amount={payment_info.total_amount} {payment_info.currency}, "
        f"payload={payment_info.invoice_payload}, "
        f"telegram_charge_id={payment_info.telegram_payment_charge_id}"
    )

    async with get_session() as session:
        # Получаем пользователя
        user = await session.get(User, message.from_user.id)
        if not user:
            await message.answer("❌ Пользователь не найден. Обратитесь в поддержку.")
            return

        payload = payment_info.invoice_payload

        # Пополнение баланса Stars
        if payload.startswith("deposit_stars_"):
            amount = int(payload.split("_")[-1])

            # Создаём запись о платеже
            payment = Payment(
                user_id=user.telegram_id,
                amount=amount,
                currency="XTR",
                status=PaymentStatus.SUCCESS.value,
                payment_type="deposit",
                payment_system="telegram_stars",
                telegram_payment_charge_id=payment_info.telegram_payment_charge_id,
                provider_payment_charge_id=payment_info.provider_payment_charge_id,
                paid_at=datetime.utcnow(),
            )
            session.add(payment)

            # Пополняем баланс
            billing = BillingService(session)
            await billing.deposit(
                user=user,
                amount=amount,
                currency="XTR",
                payment=payment,
                description=f"Пополнение баланса +{amount} ⭐"
            )

            await session.commit()

            await message.answer(
                f"✅ <b>Платёж успешен!</b>\n\n"
                f"Баланс пополнен на {amount} ⭐\n\n"
                f"{format_balance(user)}"
            )

        # Прямая покупка услуги за Stars
        elif payload.startswith("buy_service_"):
            parts = payload.split("_")
            service_code = "_".join(parts[2:-1])  # Убираем buy_service_ и ad_id
            # Обработка покупки услуги...
            # TODO: реализовать когда будет UI покупки услуг

            await message.answer("✅ Услуга успешно оплачена!")


# =============================================================================
# ПОКУПКА УСЛУГ
# =============================================================================

@router.callback_query(F.data == "paid_services")
async def paid_services_menu(callback: CallbackQuery):
    """Меню платных услуг"""
    text = (
        "💎 <b>Платные услуги</b>\n\n"
        "Выберите категорию:\n\n"
        "📅 <b>Продление</b> — продлить срок объявления\n"
        "🚀 <b>Продвижение</b> — поднять, закрепить, Stories\n"
        "✨ <b>Возможности</b> — видео, ссылки, регионы\n"
        "⭐ <b>Подписки</b> — PRO и Бизнес аккаунты\n"
    )

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📅 Продление", callback_data="services_ad_duration"),
            InlineKeyboardButton(text="🚀 Продвижение", callback_data="services_promotion"),
        ],
        [
            InlineKeyboardButton(text="✨ Возможности", callback_data="services_ad_feature"),
            InlineKeyboardButton(text="⭐ Подписки", callback_data="services_subscriptions"),
        ],
        [InlineKeyboardButton(text="« Назад", callback_data="billing_menu")],
    ])

    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("services_"))
async def services_category(callback: CallbackQuery):
    """Список услуг по категории"""
    category = callback.data.replace("services_", "")

    if category == "subscriptions":
        # Показываем подписки
        text = "⭐ <b>Подписки</b>\n\n"

        for acc_type, config in ACCOUNT_TYPES.items():
            if config["price_rub"] == 0:
                continue
            text += (
                f"{config['emoji']} <b>{config['name']}</b> — {config['price_rub']} ₽/мес\n"
                f"   {config['description']}\n\n"
            )

        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="⭐ PRO — 199₽", callback_data="subscribe_pro"),
                InlineKeyboardButton(text="💼 Бизнес — 499₽", callback_data="subscribe_business"),
            ],
            [InlineKeyboardButton(text="« Назад", callback_data="paid_services")],
        ])

        await callback.message.edit_text(text, reply_markup=keyboard)
    else:
        # Показываем услуги категории
        services = [
            (code, s) for code, s in PAID_SERVICES.items()
            if s.get("category") == category and s.get("is_active")
        ]

        if not services:
            await callback.answer("Услуги в этой категории пока недоступны", show_alert=True)
            return

        category_names = {
            "ad_duration": "📅 Продление",
            "ad_feature": "✨ Возможности",
            "promotion": "🚀 Продвижение",
            "advertising": "📢 Реклама",
        }

        text = f"<b>{category_names.get(category, category)}</b>\n\n"

        for code, service in services:
            text += f"• {service['name']} — {service['price_rub']} ₽\n"

        text += "\n<i>Для покупки перейдите в объявление</i>"

        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="« Назад", callback_data="paid_services")],
        ])

        await callback.message.edit_text(text, reply_markup=keyboard)

    await callback.answer()


@router.callback_query(F.data.startswith("subscribe_"))
async def subscribe_start(callback: CallbackQuery):
    """Начало оформления подписки"""
    account_type = callback.data.replace("subscribe_", "")

    if account_type not in ACCOUNT_TYPES:
        await callback.answer("Неизвестный тип подписки", show_alert=True)
        return

    config = ACCOUNT_TYPES[account_type]

    text = (
        f"{config['emoji']} <b>Подписка {config['name']}</b>\n\n"
        f"💰 Стоимость: {config['price_rub']} ₽ / {config['duration_days']} дней\n\n"
        f"<b>Включено:</b>\n"
        f"• До {config['limits']['max_active_ads']} объявлений\n"
        f"• Срок публикации {config['limits']['ad_duration_days']} дней\n"
        f"• До {config['limits']['max_regions_per_ad']} регионов\n"
        f"• До {config['limits']['max_links_per_ad']} ссылок\n"
        f"• Видео: {'✅' if config['limits']['video_allowed'] else '❌'}\n"
        f"• Быстрая модерация: {'✅' if config['limits']['priority_moderation'] else '❌'}\n\n"
        f"Выберите способ оплаты:"
    )

    await callback.message.edit_text(
        text,
        reply_markup=get_currency_choice_keyboard(f"pay_sub_{account_type}")
    )
    await callback.answer()


@router.callback_query(F.data.startswith("pay_sub_"))
async def subscribe_pay(callback: CallbackQuery):
    """Оплата подписки"""
    parts = callback.data.split("_")
    account_type = parts[2]
    currency = parts[3] if len(parts) > 3 else "RUB"

    async with get_session() as session:
        user = await session.get(User, callback.from_user.id)
        if not user:
            await callback.answer("Ошибка", show_alert=True)
            return

        billing = BillingService(session)
        success, message, tx = await billing.subscribe(user, account_type, currency)

        if success:
            await session.commit()
            await callback.message.edit_text(
                f"✅ {message}\n\n"
                f"Подписка активна до: {user.account_until.strftime('%d.%m.%Y')}\n\n"
                f"{format_balance(user)}"
            )
        else:
            await callback.message.edit_text(
                f"❌ {message}\n\n"
                "Пополните баланс и попробуйте снова.",
                reply_markup=get_deposit_keyboard()
            )

    await callback.answer()


# =============================================================================
# ПОКУПКА УСЛУГИ ДЛЯ ОБЪЯВЛЕНИЯ
# =============================================================================

@router.callback_query(F.data.startswith("buy_"))
async def buy_service_for_ad(callback: CallbackQuery):
    """
    Покупка услуги для объявления.
    Формат: buy_{service_code}_{ad_id}
    """
    parts = callback.data.split("_")
    if len(parts) < 3:
        await callback.answer("Неверный формат", show_alert=True)
        return

    service_code = "_".join(parts[1:-1])
    ad_id = parts[-1]

    service = PAID_SERVICES.get(service_code)
    if not service:
        await callback.answer("Услуга не найдена", show_alert=True)
        return

    # Показываем выбор валюты
    text = (
        f"💎 <b>{service['name']}</b>\n\n"
        f"{service.get('description', '')}\n\n"
        f"💰 Стоимость: {service['price_rub']} ₽\n\n"
        f"Выберите способ оплаты:"
    )

    await callback.message.edit_text(
        text,
        reply_markup=get_currency_choice_keyboard(f"confirm_buy_{service_code}_{ad_id}")
    )
    await callback.answer()


@router.callback_query(F.data.startswith("confirm_buy_"))
async def confirm_buy_service(callback: CallbackQuery):
    """Подтверждение покупки услуги"""
    parts = callback.data.split("_")
    # confirm_buy_{service_code}_{ad_id}_{currency}
    currency = parts[-1]
    ad_id = parts[-2]
    service_code = "_".join(parts[2:-2])

    async with get_session() as session:
        from bot.database.models import Ad

        user = await session.get(User, callback.from_user.id)
        ad = await session.get(Ad, ad_id)

        if not user or not ad:
            await callback.answer("Ошибка", show_alert=True)
            return

        billing = BillingService(session)
        success, message, tx = await billing.charge(
            user=user,
            service_code=service_code,
            currency=currency,
            ad=ad
        )

        if success:
            await session.commit()
            await callback.message.edit_text(
                f"✅ Услуга «{PAID_SERVICES[service_code]['name']}» активирована!\n\n"
                f"{format_balance(user)}"
            )
        else:
            await callback.message.edit_text(
                f"❌ {message}\n\n"
                "Пополните баланс и попробуйте снова.",
                reply_markup=get_deposit_keyboard()
            )

    await callback.answer()
