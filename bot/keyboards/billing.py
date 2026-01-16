# bot/keyboards/billing.py
"""Клавиатуры для раздела биллинга и платежей"""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def get_billing_menu_keyboard() -> InlineKeyboardMarkup:
    """Главное меню биллинга"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="💳 Пополнить", callback_data="deposit_menu"),
            InlineKeyboardButton(text="📊 История", callback_data="transactions_history"),
        ],
        [
            InlineKeyboardButton(text="💎 Услуги", callback_data="paid_services"),
            InlineKeyboardButton(text="⭐ Подписки", callback_data="services_subscriptions"),
        ],
        [
            InlineKeyboardButton(text="🎟 Промокод", callback_data="enter_promocode"),
        ],
        [InlineKeyboardButton(text="« Главное меню", callback_data="main_menu")],
    ])


def get_deposit_keyboard() -> InlineKeyboardMarkup:
    """Меню пополнения баланса"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⭐ Пополнить Stars", callback_data="deposit_stars"),
        ],
        [
            InlineKeyboardButton(text="💳 Пополнить ₽ (скоро)", callback_data="deposit_rub"),
        ],
        [InlineKeyboardButton(text="« Назад", callback_data="billing_menu")],
    ])


def get_deposit_amount_keyboard(currency: str = "stars") -> InlineKeyboardMarkup:
    """Выбор суммы пополнения"""
    if currency == "stars":
        amounts = [50, 100, 250, 500, 1000]
        buttons = [
            [
                InlineKeyboardButton(text=f"{a} ⭐", callback_data=f"deposit_stars_{a}")
                for a in amounts[:3]
            ],
            [
                InlineKeyboardButton(text=f"{a} ⭐", callback_data=f"deposit_stars_{a}")
                for a in amounts[3:]
            ],
        ]
    else:  # rub
        amounts = [100, 250, 500, 1000, 2500]
        buttons = [
            [
                InlineKeyboardButton(text=f"{a} ₽", callback_data=f"deposit_rub_{a}")
                for a in amounts[:3]
            ],
            [
                InlineKeyboardButton(text=f"{a} ₽", callback_data=f"deposit_rub_{a}")
                for a in amounts[3:]
            ],
        ]

    buttons.append([InlineKeyboardButton(text="« Назад", callback_data="deposit_menu")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_currency_choice_keyboard(callback_prefix: str) -> InlineKeyboardMarkup:
    """
    Выбор валюты оплаты.

    Args:
        callback_prefix: Префикс для callback_data (к нему добавится _RUB или _XTR)
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="💰 Оплатить рублями", callback_data=f"{callback_prefix}_RUB"),
        ],
        [
            InlineKeyboardButton(text="⭐ Оплатить Stars", callback_data=f"{callback_prefix}_XTR"),
        ],
        [InlineKeyboardButton(text="« Назад", callback_data="billing_menu")],
    ])


def get_transactions_keyboard(has_more: bool = False, offset: int = 0) -> InlineKeyboardMarkup:
    """Клавиатура для истории транзакций"""
    buttons = []

    if has_more:
        buttons.append([
            InlineKeyboardButton(
                text="Показать ещё",
                callback_data=f"transactions_more_{offset + 20}"
            )
        ])

    buttons.append([InlineKeyboardButton(text="« Назад", callback_data="billing_menu")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_service_purchase_keyboard(service_code: str, ad_id: str) -> InlineKeyboardMarkup:
    """Клавиатура покупки услуги"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="💰 Оплатить рублями",
                callback_data=f"confirm_buy_{service_code}_{ad_id}_RUB"
            ),
        ],
        [
            InlineKeyboardButton(
                text="⭐ Оплатить Stars",
                callback_data=f"confirm_buy_{service_code}_{ad_id}_XTR"
            ),
        ],
        [InlineKeyboardButton(text="« Отмена", callback_data=f"ad_view_{ad_id}")],
    ])


def get_promocode_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для ввода промокода"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="« Отмена", callback_data="billing_menu")],
    ])


def get_subscription_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора подписки"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⭐ PRO — 199₽/мес", callback_data="subscribe_pro"),
        ],
        [
            InlineKeyboardButton(text="💼 Бизнес — 499₽/мес", callback_data="subscribe_business"),
        ],
        [InlineKeyboardButton(text="« Назад", callback_data="billing_menu")],
    ])
