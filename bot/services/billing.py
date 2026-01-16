# bot/services/billing.py
"""
Сервис биллинга — работа с балансом пользователя.

Функции:
- Пополнение баланса (рубли, Stars)
- Списание за услуги
- Возвраты
- История транзакций
- Проверка баланса

Использование:
    from bot.services.billing import BillingService

    billing = BillingService(session)
    success = await billing.charge(user, "pin_channel_24h", currency="RUB", ad=ad)
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple, List, Dict, Any
from uuid import UUID

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config.pricing import PAID_SERVICES, ACCOUNT_TYPES, get_service_price
from bot.database.models import (
    User, Ad, Payment, Transaction, UserServicePurchase,
    TransactionType, PaymentStatus
)

logger = logging.getLogger(__name__)


class BillingService:
    """Сервис для работы с балансом и платежами"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_balance(self, user: User) -> Dict[str, Any]:
        """
        Получить баланс пользователя.

        Returns:
            {
                "rub": 150.0,
                "stars": 50,
                "total_spent_rub": 500.0,
                "total_spent_stars": 100
            }
        """
        return {
            "rub": user.balance_rub or 0.0,
            "stars": user.balance_stars or 0,
            "total_spent_rub": user.total_spent_rub or 0.0,
            "total_spent_stars": user.total_spent_stars or 0,
        }

    async def deposit(
        self,
        user: User,
        amount: float,
        currency: str,
        payment: Optional[Payment] = None,
        description: str = "Пополнение баланса"
    ) -> Transaction:
        """
        Пополнить баланс пользователя.

        Args:
            user: Пользователь
            amount: Сумма
            currency: 'RUB' или 'XTR'
            payment: Связанный платёж (опционально)
            description: Описание операции

        Returns:
            Transaction
        """
        if currency == "RUB":
            user.balance_rub = (user.balance_rub or 0) + amount
        elif currency == "XTR":
            user.balance_stars = (user.balance_stars or 0) + int(amount)
        else:
            raise ValueError(f"Неизвестная валюта: {currency}")

        # Создаём транзакцию
        transaction = Transaction(
            user_id=user.telegram_id,
            type=TransactionType.DEPOSIT.value,
            currency=currency,
            amount=amount,
            balance_rub_after=user.balance_rub or 0,
            balance_stars_after=user.balance_stars or 0,
            payment_id=payment.id if payment else None,
            description=description,
        )
        self.session.add(transaction)
        await self.session.flush()

        logger.info(
            f"Deposit: user={user.telegram_id}, amount={amount} {currency}, "
            f"new_balance_rub={user.balance_rub}, new_balance_stars={user.balance_stars}"
        )

        return transaction

    async def charge(
        self,
        user: User,
        service_code: str,
        currency: str = "RUB",
        ad: Optional[Ad] = None,
        quantity: int = 1,
        custom_price: Optional[float] = None
    ) -> Tuple[bool, str, Optional[Transaction]]:
        """
        Списать с баланса за услугу.

        Args:
            user: Пользователь
            service_code: Код услуги из PAID_SERVICES
            currency: 'RUB' или 'XTR'
            ad: Объявление (для услуг привязанных к объявлению)
            quantity: Количество (для per_item услуг)
            custom_price: Кастомная цена (если отличается от стандартной)

        Returns:
            (success, message, transaction)
        """
        service = PAID_SERVICES.get(service_code)
        if not service:
            return False, "Услуга не найдена", None

        if not service.get("is_active"):
            return False, "Услуга временно недоступна", None

        # Рассчитываем цену
        if custom_price is not None:
            price = custom_price
        else:
            price = service["price_rub"] * quantity

        # Конвертируем в Stars если нужно
        if currency == "XTR":
            from bot.services.exchange_rate import ExchangeRateService
            rate_service = ExchangeRateService(self.session)
            star_rate = await rate_service.get_current_rate()
            price_stars = int(price / star_rate)  # Округляем вниз
            if price_stars < 1:
                price_stars = 1
            price = price_stars

        # Проверяем баланс
        if currency == "RUB":
            if (user.balance_rub or 0) < price:
                return False, f"Недостаточно средств. Нужно {price:.2f} ₽", None
        elif currency == "XTR":
            if (user.balance_stars or 0) < price:
                return False, f"Недостаточно звёзд. Нужно {int(price)} ⭐", None
        else:
            return False, f"Неизвестная валюта: {currency}", None

        # Списываем
        if currency == "RUB":
            user.balance_rub = (user.balance_rub or 0) - price
            user.total_spent_rub = (user.total_spent_rub or 0) + price
        else:
            user.balance_stars = (user.balance_stars or 0) - int(price)
            user.total_spent_stars = (user.total_spent_stars or 0) + int(price)

        # Создаём транзакцию
        transaction = Transaction(
            user_id=user.telegram_id,
            type=TransactionType.PURCHASE.value,
            currency=currency,
            amount=price,
            balance_rub_after=user.balance_rub or 0,
            balance_stars_after=user.balance_stars or 0,
            ad_id=ad.id if ad else None,
            service_code=service_code,
            description=f"{service['name']} x{quantity}" if quantity > 1 else service['name'],
        )
        self.session.add(transaction)

        # Активируем услугу
        await self._activate_service(user, service_code, ad, quantity, transaction)

        await self.session.flush()

        logger.info(
            f"Charge: user={user.telegram_id}, service={service_code}, "
            f"price={price} {currency}, ad={ad.id if ad else None}"
        )

        return True, "Успешно", transaction

    async def _activate_service(
        self,
        user: User,
        service_code: str,
        ad: Optional[Ad],
        quantity: int,
        transaction: Transaction
    ):
        """Активировать купленную услугу"""
        service = PAID_SERVICES[service_code]

        # Вычисляем срок действия
        expires_at = None
        if "duration_hours" in service:
            expires_at = datetime.utcnow() + timedelta(hours=service["duration_hours"])

        # Создаём запись о покупке
        purchase = UserServicePurchase(
            user_id=user.telegram_id,
            ad_id=ad.id if ad else None,
            service_code=service_code,
            quantity=quantity,
            expires_at=expires_at,
            is_active=True,
            transaction_id=transaction.id,
        )
        self.session.add(purchase)

        # Применяем эффект услуги
        await self._apply_service_effect(user, ad, service_code, expires_at)

    async def _apply_service_effect(
        self,
        user: User,
        ad: Optional[Ad],
        service_code: str,
        expires_at: Optional[datetime]
    ):
        """Применить эффект услуги (обновить флаги в моделях)"""

        # Услуги для объявления
        if ad:
            if service_code.startswith("pin_channel"):
                ad.pinned_until = expires_at
                ad.premium_features = ad.premium_features or {}
                ad.premium_features["pinned"] = True

            elif service_code == "story_publish":
                ad.in_stories_until = expires_at

            elif service_code == "badge_urgent":
                ad.premium_features = ad.premium_features or {}
                ad.premium_features["urgent"] = True
                ad.premium_features["urgent_until"] = expires_at.isoformat() if expires_at else None

            elif service_code == "btn_call":
                ad.premium_features = ad.premium_features or {}
                ad.premium_features["call_button"] = True

            elif service_code == "ad_video":
                ad.premium_features = ad.premium_features or {}
                ad.premium_features["video_allowed"] = True

        # Услуги для аккаунта
        if service_code.startswith("ads_pack"):
            ads_count = PAID_SERVICES[service_code].get("ads_count", 0)
            user.extra_ads_limit = (user.extra_ads_limit or 0) + ads_count

    async def refund(
        self,
        user: User,
        transaction: Transaction,
        reason: str = "Возврат средств"
    ) -> Tuple[bool, str, Optional[Transaction]]:
        """
        Вернуть средства за транзакцию.

        Returns:
            (success, message, refund_transaction)
        """
        if transaction.type != TransactionType.PURCHASE.value:
            return False, "Можно вернуть только покупки", None

        currency = transaction.currency
        amount = transaction.amount

        # Возвращаем на баланс
        if currency == "RUB":
            user.balance_rub = (user.balance_rub or 0) + amount
            user.total_spent_rub = (user.total_spent_rub or 0) - amount
        else:
            user.balance_stars = (user.balance_stars or 0) + int(amount)
            user.total_spent_stars = (user.total_spent_stars or 0) - int(amount)

        # Создаём транзакцию возврата
        refund_tx = Transaction(
            user_id=user.telegram_id,
            type=TransactionType.REFUND.value,
            currency=currency,
            amount=amount,
            balance_rub_after=user.balance_rub or 0,
            balance_stars_after=user.balance_stars or 0,
            service_code=transaction.service_code,
            description=reason,
        )
        self.session.add(refund_tx)

        # Деактивируем услугу
        if transaction.service_code:
            result = await self.session.execute(
                select(UserServicePurchase)
                .where(UserServicePurchase.transaction_id == transaction.id)
            )
            purchase = result.scalar_one_or_none()
            if purchase:
                purchase.is_active = False

        await self.session.flush()

        logger.info(
            f"Refund: user={user.telegram_id}, amount={amount} {currency}, "
            f"original_tx={transaction.id}"
        )

        return True, "Возврат выполнен", refund_tx

    async def add_bonus(
        self,
        user: User,
        amount: float,
        currency: str,
        description: str = "Бонус"
    ) -> Transaction:
        """
        Начислить бонус на баланс.
        """
        if currency == "RUB":
            user.balance_rub = (user.balance_rub or 0) + amount
        else:
            user.balance_stars = (user.balance_stars or 0) + int(amount)

        transaction = Transaction(
            user_id=user.telegram_id,
            type=TransactionType.BONUS.value,
            currency=currency,
            amount=amount,
            balance_rub_after=user.balance_rub or 0,
            balance_stars_after=user.balance_stars or 0,
            description=description,
        )
        self.session.add(transaction)
        await self.session.flush()

        logger.info(f"Bonus: user={user.telegram_id}, amount={amount} {currency}")

        return transaction

    async def get_transactions(
        self,
        user: User,
        limit: int = 20,
        offset: int = 0,
        tx_type: Optional[str] = None
    ) -> List[Transaction]:
        """
        Получить историю транзакций пользователя.
        """
        query = (
            select(Transaction)
            .where(Transaction.user_id == user.telegram_id)
            .order_by(desc(Transaction.created_at))
            .limit(limit)
            .offset(offset)
        )

        if tx_type:
            query = query.where(Transaction.type == tx_type)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def subscribe(
        self,
        user: User,
        account_type: str,
        currency: str = "RUB"
    ) -> Tuple[bool, str, Optional[Transaction]]:
        """
        Оформить подписку (PRO или Business).

        Returns:
            (success, message, transaction)
        """
        if account_type not in ACCOUNT_TYPES:
            return False, "Неизвестный тип аккаунта", None

        account_config = ACCOUNT_TYPES[account_type]
        price = account_config["price_rub"]
        duration_days = account_config["duration_days"]

        if price == 0:
            return False, "Этот тип аккаунта бесплатный", None

        # Конвертируем в Stars если нужно
        if currency == "XTR":
            from bot.services.exchange_rate import ExchangeRateService
            rate_service = ExchangeRateService(self.session)
            star_rate = await rate_service.get_current_rate()
            price = int(price / star_rate)

        # Проверяем баланс
        if currency == "RUB":
            if (user.balance_rub or 0) < price:
                return False, f"Недостаточно средств. Нужно {price:.2f} ₽", None
        else:
            if (user.balance_stars or 0) < price:
                return False, f"Недостаточно звёзд. Нужно {price} ⭐", None

        # Списываем
        if currency == "RUB":
            user.balance_rub = (user.balance_rub or 0) - price
            user.total_spent_rub = (user.total_spent_rub or 0) + price
        else:
            user.balance_stars = (user.balance_stars or 0) - int(price)
            user.total_spent_stars = (user.total_spent_stars or 0) + int(price)

        # Обновляем подписку
        user.account_type = account_type
        if user.account_until and user.account_until > datetime.utcnow():
            # Продлеваем существующую подписку
            user.account_until = user.account_until + timedelta(days=duration_days)
        else:
            # Новая подписка
            user.account_until = datetime.utcnow() + timedelta(days=duration_days)

        # Создаём транзакцию
        transaction = Transaction(
            user_id=user.telegram_id,
            type=TransactionType.SUBSCRIPTION.value,
            currency=currency,
            amount=price,
            balance_rub_after=user.balance_rub or 0,
            balance_stars_after=user.balance_stars or 0,
            service_code=f"subscription_{account_type}",
            description=f"Подписка {account_config['name']} на {duration_days} дней",
        )
        self.session.add(transaction)
        await self.session.flush()

        logger.info(
            f"Subscription: user={user.telegram_id}, type={account_type}, "
            f"until={user.account_until}"
        )

        return True, "Подписка оформлена", transaction

    async def check_can_purchase(
        self,
        user: User,
        service_code: str,
        currency: str = "RUB"
    ) -> Tuple[bool, str, float]:
        """
        Проверить, может ли пользователь купить услугу.

        Returns:
            (can_purchase, message, price)
        """
        service = PAID_SERVICES.get(service_code)
        if not service:
            return False, "Услуга не найдена", 0

        price = service["price_rub"]

        # Конвертируем в Stars
        if currency == "XTR":
            from bot.services.exchange_rate import ExchangeRateService
            rate_service = ExchangeRateService(self.session)
            star_rate = await rate_service.get_current_rate()
            price = int(price / star_rate)
            if price < 1:
                price = 1

        # Проверяем баланс
        if currency == "RUB":
            if (user.balance_rub or 0) < price:
                return False, f"Недостаточно средств ({user.balance_rub:.2f} ₽)", price
        else:
            if (user.balance_stars or 0) < price:
                return False, f"Недостаточно звёзд ({user.balance_stars} ⭐)", price

        return True, "OK", price


def format_balance(user: User) -> str:
    """Форматирование баланса для отображения"""
    rub = user.balance_rub or 0
    stars = user.balance_stars or 0

    lines = ["💰 <b>Ваш баланс:</b>"]
    lines.append(f"   • {rub:.2f} ₽")
    lines.append(f"   • {stars} ⭐")

    return "\n".join(lines)


def format_transaction(tx: Transaction) -> str:
    """Форматирование транзакции для отображения"""
    type_emoji = {
        "deposit": "➕",
        "purchase": "🛒",
        "refund": "↩️",
        "bonus": "🎁",
        "subscription": "⭐",
    }

    emoji = type_emoji.get(tx.type, "•")
    sign = "+" if tx.type in ["deposit", "refund", "bonus"] else "-"
    currency_symbol = "₽" if tx.currency == "RUB" else "⭐"

    amount_str = f"{sign}{tx.amount:.2f}" if tx.currency == "RUB" else f"{sign}{int(tx.amount)}"

    date_str = tx.created_at.strftime("%d.%m %H:%M")

    return f"{emoji} {date_str} | {amount_str} {currency_symbol} | {tx.description}"
