# bot/handlers/billing.py
"""
Обработчики для раздела биллинга (баланс, история, промокоды).

Команды:
- /balance — показать баланс
- /history — история транзакций

Меню:
- billing_menu — главное меню биллинга
- deposit_menu — меню пополнения
- transactions_history — история транзакций
- enter_promocode — ввод промокода
"""

import logging

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.database.connection import get_session
from bot.database.models import User
from bot.services.billing import BillingService, format_balance, format_transaction
from bot.services.exchange_rate import ExchangeRateService, format_rate_info
from bot.services.promocodes import PromocodeService
from bot.utils.limits import format_limits_info
from bot.keyboards.billing import (
    get_billing_menu_keyboard,
    get_deposit_keyboard,
    get_transactions_keyboard,
    get_promocode_keyboard,
)

logger = logging.getLogger(__name__)

router = Router(name='billing')


class PromocodeStates(StatesGroup):
    """Состояния для ввода промокода"""
    waiting_for_code = State()


# =============================================================================
# КОМАНДЫ
# =============================================================================

@router.message(F.text == "💰 Баланс")
async def btn_balance(message: Message):
    """Кнопка Баланс из reply клавиатуры"""
    await cmd_balance(message)


@router.message(Command("balance"))
async def cmd_balance(message: Message):
    """Команда /balance — показать баланс"""
    async with get_session() as session:
        user = await session.get(User, message.from_user.id)
        if not user:
            await message.answer("❌ Пользователь не найден")
            return

        # Получаем курс Stars
        rate_service = ExchangeRateService(session)
        star_rate = await rate_service.get_current_rate()

        text = (
            f"{format_balance(user)}\n\n"
            f"{format_limits_info(user)}\n\n"
            f"📊 Курс: 1 ⭐ = {star_rate:.2f} ₽"
        )

        await message.answer(text, reply_markup=get_billing_menu_keyboard())


@router.message(Command("history"))
async def cmd_history(message: Message):
    """Команда /history — история транзакций"""
    async with get_session() as session:
        user = await session.get(User, message.from_user.id)
        if not user:
            await message.answer("❌ Пользователь не найден")
            return

        billing = BillingService(session)
        transactions = await billing.get_transactions(user, limit=20)

        if not transactions:
            await message.answer(
                "📋 <b>История операций</b>\n\n"
                "<i>Пока нет операций</i>",
                reply_markup=get_billing_menu_keyboard()
            )
            return

        lines = ["📋 <b>История операций</b>\n"]
        for tx in transactions:
            lines.append(format_transaction(tx))

        await message.answer(
            "\n".join(lines),
            reply_markup=get_transactions_keyboard(has_more=len(transactions) >= 20)
        )


# =============================================================================
# МЕНЮ БИЛЛИНГА
# =============================================================================

@router.callback_query(F.data == "billing_menu")
async def billing_menu(callback: CallbackQuery):
    """Главное меню биллинга"""
    async with get_session() as session:
        user = await session.get(User, callback.from_user.id)
        if not user:
            await callback.answer("Ошибка", show_alert=True)
            return

        rate_service = ExchangeRateService(session)
        star_rate = await rate_service.get_current_rate()

        text = (
            f"{format_balance(user)}\n\n"
            f"📊 Курс: 1 ⭐ = {star_rate:.2f} ₽\n\n"
            f"Выберите действие:"
        )

        await callback.message.edit_text(text, reply_markup=get_billing_menu_keyboard())
    await callback.answer()


@router.callback_query(F.data == "deposit_menu")
async def deposit_menu(callback: CallbackQuery):
    """Меню пополнения баланса"""
    async with get_session() as session:
        user = await session.get(User, callback.from_user.id)
        rate_service = ExchangeRateService(session)
        star_rate = await rate_service.get_current_rate()

    text = (
        "💳 <b>Пополнение баланса</b>\n\n"
        f"Текущий курс: 1 ⭐ = {star_rate:.2f} ₽\n\n"
        "Выберите способ пополнения:"
    )

    await callback.message.edit_text(text, reply_markup=get_deposit_keyboard())
    await callback.answer()


@router.callback_query(F.data == "deposit_rub")
async def deposit_rub(callback: CallbackQuery):
    """Пополнение рублями (пока недоступно)"""
    await callback.answer(
        "💳 Пополнение рублями скоро будет доступно!\n"
        "Пока используйте Telegram Stars ⭐",
        show_alert=True
    )


# =============================================================================
# ИСТОРИЯ ТРАНЗАКЦИЙ
# =============================================================================

@router.callback_query(F.data == "transactions_history")
async def transactions_history(callback: CallbackQuery):
    """История транзакций"""
    async with get_session() as session:
        user = await session.get(User, callback.from_user.id)
        if not user:
            await callback.answer("Ошибка", show_alert=True)
            return

        billing = BillingService(session)
        transactions = await billing.get_transactions(user, limit=20)

        if not transactions:
            await callback.message.edit_text(
                "📋 <b>История операций</b>\n\n"
                "<i>Пока нет операций</i>",
                reply_markup=get_transactions_keyboard()
            )
            await callback.answer()
            return

        lines = ["📋 <b>История операций</b>\n"]
        for tx in transactions:
            lines.append(format_transaction(tx))

        await callback.message.edit_text(
            "\n".join(lines),
            reply_markup=get_transactions_keyboard(has_more=len(transactions) >= 20)
        )
    await callback.answer()


@router.callback_query(F.data.startswith("transactions_more_"))
async def transactions_more(callback: CallbackQuery):
    """Показать больше транзакций"""
    offset = int(callback.data.split("_")[-1])

    async with get_session() as session:
        user = await session.get(User, callback.from_user.id)
        if not user:
            await callback.answer("Ошибка", show_alert=True)
            return

        billing = BillingService(session)
        transactions = await billing.get_transactions(user, limit=20, offset=offset)

        if not transactions:
            await callback.answer("Больше нет транзакций", show_alert=True)
            return

        lines = ["📋 <b>История операций</b>\n"]

        # Добавляем предыдущие из сообщения
        current_text = callback.message.text or ""
        if "📋" in current_text:
            # Берём строки после заголовка
            old_lines = current_text.split("\n")[2:]  # Пропускаем заголовок и пустую строку
            lines.extend(old_lines)

        for tx in transactions:
            lines.append(format_transaction(tx))

        await callback.message.edit_text(
            "\n".join(lines),
            reply_markup=get_transactions_keyboard(
                has_more=len(transactions) >= 20,
                offset=offset
            )
        )
    await callback.answer()


# =============================================================================
# ПРОМОКОДЫ
# =============================================================================

@router.callback_query(F.data == "enter_promocode")
async def enter_promocode_start(callback: CallbackQuery, state: FSMContext):
    """Начало ввода промокода"""
    await state.set_state(PromocodeStates.waiting_for_code)

    await callback.message.edit_text(
        "🎟 <b>Введите промокод</b>\n\n"
        "Отправьте промокод в чат:",
        reply_markup=get_promocode_keyboard()
    )
    await callback.answer()


@router.message(StateFilter(PromocodeStates.waiting_for_code))
async def process_promocode(message: Message, state: FSMContext):
    """Обработка введённого промокода"""
    code = message.text.strip().upper()

    async with get_session() as session:
        user = await session.get(User, message.from_user.id)
        if not user:
            await message.answer("❌ Пользователь не найден")
            await state.clear()
            return

        promo_service = PromocodeService(session)

        # Применяем промокод
        success, discount, result_message = await promo_service.apply(
            code=code,
            user=user
        )

        if success:
            await session.commit()
            await message.answer(
                f"✅ {result_message}\n\n"
                f"{format_balance(user)}",
                reply_markup=get_billing_menu_keyboard()
            )
        else:
            await message.answer(
                f"❌ {result_message}\n\n"
                "Попробуйте другой промокод или вернитесь в меню.",
                reply_markup=get_promocode_keyboard()
            )

    await state.clear()


# =============================================================================
# ИНФОРМАЦИЯ О КУРСЕ
# =============================================================================

@router.callback_query(F.data == "exchange_rate_info")
async def exchange_rate_info(callback: CallbackQuery):
    """Информация о курсе Stars"""
    async with get_session() as session:
        rate_service = ExchangeRateService(session)
        star_rate = await rate_service.get_current_rate()
        usd_rate = await rate_service.get_usd_rub_rate()

        text = format_rate_info(star_rate, usd_rate)

        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="« Назад", callback_data="billing_menu")],
        ])

        await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()


# =============================================================================
# ИНФОРМАЦИЯ ОБ АККАУНТЕ
# =============================================================================

@router.callback_query(F.data == "account_info")
async def account_info(callback: CallbackQuery):
    """Информация об аккаунте и лимитах"""
    async with get_session() as session:
        user = await session.get(User, callback.from_user.id)
        if not user:
            await callback.answer("Ошибка", show_alert=True)
            return

        text = (
            "👤 <b>Ваш аккаунт</b>\n\n"
            f"{format_limits_info(user)}"
        )

        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⭐ Улучшить", callback_data="services_subscriptions")],
            [InlineKeyboardButton(text="« Назад", callback_data="billing_menu")],
        ])

        await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()
