# bot/services/promocodes.py
"""
Сервис промокодов.

Типы промокодов:
- fixed_rub: Фиксированная скидка в рублях
- percent: Процент скидки
- bonus_rub: Бонус на баланс в рублях
- bonus_stars: Бонус на баланс в Stars
- free_service: Бесплатная услуга

Использование:
    from bot.services.promocodes import PromocodeService

    service = PromocodeService(session)

    # Проверка промокода
    valid, promo, message = await service.validate("LAUNCH2026", user)

    # Применение промокода
    success, discount, message = await service.apply("LAUNCH2026", user, amount=100)
"""

import logging
from datetime import datetime
from typing import Optional, Tuple, List

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import (
    User, Promocode, PromocodeUsage, Payment, PromocodeType
)
from bot.config.pricing import PAID_SERVICES

logger = logging.getLogger(__name__)


class PromocodeService:
    """Сервис для работы с промокодами"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def validate(
        self,
        code: str,
        user: User,
        service_code: Optional[str] = None,
        amount: Optional[float] = None
    ) -> Tuple[bool, Optional[Promocode], str]:
        """
        Проверить промокод.

        Args:
            code: Код промокода
            user: Пользователь
            service_code: Код услуги (для проверки ограничений)
            amount: Сумма заказа (для проверки минимальной суммы)

        Returns:
            (is_valid, promocode, message)
        """
        # Ищем промокод
        result = await self.session.execute(
            select(Promocode).where(
                Promocode.code == code.upper().strip()
            )
        )
        promo = result.scalar_one_or_none()

        if not promo:
            return False, None, "Промокод не найден"

        if not promo.is_active:
            return False, None, "Промокод не активен"

        # Проверяем срок действия
        now = datetime.utcnow()
        if promo.valid_from and now < promo.valid_from:
            return False, None, "Промокод ещё не действует"

        if promo.valid_until and now > promo.valid_until:
            return False, None, "Срок действия промокода истёк"

        # Проверяем лимит использований
        if promo.max_uses and promo.uses_count >= promo.max_uses:
            return False, None, "Лимит использований промокода исчерпан"

        # Проверяем использование этим пользователем
        user_uses = await self._count_user_uses(promo.id, user.telegram_id)
        if user_uses >= promo.max_uses_per_user:
            return False, None, "Вы уже использовали этот промокод"

        # Проверяем минимальную сумму
        if promo.min_amount and amount and amount < promo.min_amount:
            return False, None, f"Минимальная сумма заказа: {promo.min_amount:.0f} ₽"

        # Проверяем ограничение по услугам
        if promo.allowed_services and service_code:
            if service_code not in promo.allowed_services:
                return False, None, "Промокод не применим к этой услуге"

        return True, promo, "Промокод действителен"

    async def calculate_discount(
        self,
        promo: Promocode,
        amount: float
    ) -> Tuple[float, float]:
        """
        Рассчитать скидку.

        Args:
            promo: Промокод
            amount: Исходная сумма

        Returns:
            (discount, final_amount)
        """
        discount = 0.0

        if promo.type == PromocodeType.FIXED_RUB.value:
            discount = min(promo.value, amount)  # Не больше суммы заказа

        elif promo.type == PromocodeType.PERCENT.value:
            discount = amount * (promo.value / 100)

        final_amount = max(amount - discount, 0)

        return discount, final_amount

    async def apply(
        self,
        code: str,
        user: User,
        amount: Optional[float] = None,
        payment: Optional[Payment] = None,
        service_code: Optional[str] = None
    ) -> Tuple[bool, float, str]:
        """
        Применить промокод.

        Args:
            code: Код промокода
            user: Пользователь
            amount: Сумма заказа (для скидочных промокодов)
            payment: Платёж (опционально)
            service_code: Код услуги

        Returns:
            (success, discount_or_bonus, message)
        """
        # Валидация
        valid, promo, message = await self.validate(code, user, service_code, amount)
        if not valid:
            return False, 0, message

        discount = 0.0

        # Применяем в зависимости от типа
        if promo.type == PromocodeType.FIXED_RUB.value:
            if amount:
                discount, _ = await self.calculate_discount(promo, amount)
            else:
                discount = promo.value

        elif promo.type == PromocodeType.PERCENT.value:
            if amount:
                discount, _ = await self.calculate_discount(promo, amount)
            else:
                return False, 0, "Для процентной скидки нужна сумма заказа"

        elif promo.type == PromocodeType.BONUS_RUB.value:
            # Начисляем бонус на баланс
            user.balance_rub = (user.balance_rub or 0) + promo.value
            discount = promo.value

        elif promo.type == PromocodeType.BONUS_STARS.value:
            # Начисляем бонус в Stars
            user.balance_stars = (user.balance_stars or 0) + int(promo.value)
            discount = promo.value

        elif promo.type == PromocodeType.FREE_SERVICE.value:
            # Помечаем услугу как бесплатную (обрабатывается отдельно)
            service = PAID_SERVICES.get(promo.service_code)
            if service:
                discount = service["price_rub"]
            else:
                return False, 0, "Услуга промокода не найдена"

        # Записываем использование
        usage = PromocodeUsage(
            promocode_id=promo.id,
            user_id=user.telegram_id,
            discount_amount=discount,
            payment_id=payment.id if payment else None,
        )
        self.session.add(usage)

        # Обновляем статистику промокода
        promo.uses_count += 1
        promo.total_discount_given += discount

        await self.session.flush()

        logger.info(
            f"Promocode applied: code={code}, user={user.telegram_id}, "
            f"type={promo.type}, discount={discount}"
        )

        # Формируем сообщение
        if promo.type in [PromocodeType.BONUS_RUB.value, PromocodeType.BONUS_STARS.value]:
            currency = "₽" if promo.type == PromocodeType.BONUS_RUB.value else "⭐"
            message = f"Бонус {discount:.0f} {currency} начислен на баланс!"
        elif promo.type == PromocodeType.FREE_SERVICE.value:
            service_name = PAID_SERVICES.get(promo.service_code, {}).get("name", "Услуга")
            message = f"Услуга «{service_name}» доступна бесплатно!"
        else:
            message = f"Скидка {discount:.0f} ₽ применена!"

        return True, discount, message

    async def create(
        self,
        code: str,
        promo_type: str,
        value: float,
        created_by: int,
        max_uses: Optional[int] = None,
        max_uses_per_user: int = 1,
        min_amount: Optional[float] = None,
        allowed_services: Optional[List[str]] = None,
        valid_from: Optional[datetime] = None,
        valid_until: Optional[datetime] = None,
        service_code: Optional[str] = None
    ) -> Tuple[bool, Optional[Promocode], str]:
        """
        Создать новый промокод.

        Returns:
            (success, promocode, message)
        """
        # Проверяем уникальность кода
        code = code.upper().strip()
        existing = await self.session.execute(
            select(Promocode).where(Promocode.code == code)
        )
        if existing.scalar_one_or_none():
            return False, None, f"Промокод {code} уже существует"

        # Валидируем тип
        if promo_type not in [t.value for t in PromocodeType]:
            return False, None, f"Неизвестный тип промокода: {promo_type}"

        promo = Promocode(
            code=code,
            type=promo_type,
            value=value,
            service_code=service_code,
            max_uses=max_uses,
            max_uses_per_user=max_uses_per_user,
            min_amount=min_amount,
            allowed_services=allowed_services,
            valid_from=valid_from,
            valid_until=valid_until,
            created_by=created_by,
        )
        self.session.add(promo)
        await self.session.flush()

        logger.info(f"Promocode created: code={code}, type={promo_type}, value={value}")

        return True, promo, f"Промокод {code} создан"

    async def deactivate(self, code: str) -> Tuple[bool, str]:
        """Деактивировать промокод"""
        result = await self.session.execute(
            select(Promocode).where(Promocode.code == code.upper())
        )
        promo = result.scalar_one_or_none()

        if not promo:
            return False, "Промокод не найден"

        promo.is_active = False
        await self.session.flush()

        return True, f"Промокод {code} деактивирован"

    async def get_stats(self, code: str) -> Optional[dict]:
        """Получить статистику промокода"""
        result = await self.session.execute(
            select(Promocode).where(Promocode.code == code.upper())
        )
        promo = result.scalar_one_or_none()

        if not promo:
            return None

        return {
            "code": promo.code,
            "type": promo.type,
            "value": promo.value,
            "uses_count": promo.uses_count,
            "max_uses": promo.max_uses,
            "total_discount_given": promo.total_discount_given,
            "is_active": promo.is_active,
            "valid_from": promo.valid_from,
            "valid_until": promo.valid_until,
            "created_at": promo.created_at,
        }

    async def _count_user_uses(self, promo_id: int, user_id: int) -> int:
        """Посчитать сколько раз пользователь использовал промокод"""
        result = await self.session.execute(
            select(func.count(PromocodeUsage.id))
            .where(PromocodeUsage.promocode_id == promo_id)
            .where(PromocodeUsage.user_id == user_id)
        )
        return result.scalar() or 0

    async def list_active(self, limit: int = 20) -> List[Promocode]:
        """Получить список активных промокодов"""
        result = await self.session.execute(
            select(Promocode)
            .where(Promocode.is_active == True)
            .order_by(Promocode.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())


def format_promocode_info(promo: Promocode) -> str:
    """Форматирование информации о промокоде"""
    type_names = {
        "fixed_rub": "Фиксированная скидка",
        "percent": "Процент скидки",
        "bonus_rub": "Бонус в рублях",
        "bonus_stars": "Бонус в Stars",
        "free_service": "Бесплатная услуга",
    }

    lines = [
        f"🎟 <b>Промокод:</b> <code>{promo.code}</code>",
        f"📋 Тип: {type_names.get(promo.type, promo.type)}",
    ]

    if promo.type == "percent":
        lines.append(f"💰 Скидка: {promo.value:.0f}%")
    elif promo.type == "bonus_stars":
        lines.append(f"💰 Бонус: {int(promo.value)} ⭐")
    elif promo.type == "free_service":
        service = PAID_SERVICES.get(promo.service_code, {})
        lines.append(f"🎁 Услуга: {service.get('name', promo.service_code)}")
    else:
        lines.append(f"💰 Сумма: {promo.value:.0f} ₽")

    lines.append(f"📊 Использован: {promo.uses_count}/{promo.max_uses or '∞'}")

    if promo.valid_until:
        lines.append(f"📅 Действует до: {promo.valid_until.strftime('%d.%m.%Y')}")

    status = "✅ Активен" if promo.is_active else "❌ Не активен"
    lines.append(f"Статус: {status}")

    return "\n".join(lines)
