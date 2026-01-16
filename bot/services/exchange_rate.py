# bot/services/exchange_rate.py
"""
Сервис курса валют для расчёта стоимости Telegram Stars.

Обновление курса:
- Ежедневно в 4:00 МСК (cron-задача)
- Курс берётся с ЦБ РФ (cbr.ru)

Формула расчёта курса Stars:
    star_rub = USD_RUB * 0.013 * 0.9
    star_rub = max(star_rub, 1.0)  # Минимум 1₽ за звезду

Использование:
    from bot.services.exchange_rate import ExchangeRateService

    service = ExchangeRateService(session)
    rate = await service.get_current_rate()  # 1.05 ₽ за 1 Star
"""

import logging
import aiohttp
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from typing import Optional, Tuple

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config.pricing import STARS_CONFIG
from bot.database.models import ExchangeRate

logger = logging.getLogger(__name__)

# URL API ЦБ РФ для получения курса валют
CBR_API_URL = "https://www.cbr.ru/scripts/XML_daily.asp"


class ExchangeRateService:
    """Сервис для работы с курсами валют"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_current_rate(self) -> float:
        """
        Получить текущий курс Stars в рублях.

        Returns:
            float: Курс (сколько рублей стоит 1 Star)
        """
        today = date.today()

        # Пробуем получить курс на сегодня
        rate = await self._get_rate_for_date(today)
        if rate:
            return rate.star_rub

        # Если нет — берём последний доступный
        rate = await self._get_latest_rate()
        if rate:
            return rate.star_rub

        # Fallback — расчёт по дефолтному курсу
        return self._calculate_star_rate(STARS_CONFIG["fallback_usd_rub"])

    async def get_usd_rub_rate(self) -> float:
        """Получить текущий курс USD/RUB"""
        today = date.today()
        rate = await self._get_rate_for_date(today)
        if rate:
            return rate.usd_rub

        rate = await self._get_latest_rate()
        if rate:
            return rate.usd_rub

        return STARS_CONFIG["fallback_usd_rub"]

    async def update_rate(self) -> Tuple[bool, str]:
        """
        Обновить курс валют (вызывается cron-задачей в 4:00 МСК).

        Returns:
            (success, message)
        """
        today = date.today()

        # Проверяем, не обновляли ли уже сегодня
        existing = await self._get_rate_for_date(today)
        if existing:
            return True, f"Курс на {today} уже существует: {existing.star_rub:.4f} ₽"

        # Получаем курс USD/RUB с ЦБ РФ
        usd_rub = await self._fetch_cbr_rate()
        if not usd_rub:
            # Fallback: берём вчерашний курс или дефолтный
            yesterday_rate = await self._get_rate_for_date(today - timedelta(days=1))
            if yesterday_rate:
                usd_rub = yesterday_rate.usd_rub
            else:
                usd_rub = STARS_CONFIG["fallback_usd_rub"]
            logger.warning(f"Не удалось получить курс ЦБ, используем fallback: {usd_rub}")

        # Рассчитываем курс Stars
        star_rub = self._calculate_star_rate(usd_rub)

        # Сохраняем
        rate = ExchangeRate(
            rate_date=today,
            usd_rub=usd_rub,
            star_rub=star_rub,
            source="cbr",
        )
        self.session.add(rate)
        await self.session.flush()

        logger.info(f"Обновлён курс: USD/RUB={usd_rub:.4f}, Star/RUB={star_rub:.4f}")

        return True, f"Курс обновлён: 1⭐ = {star_rub:.2f} ₽"

    async def _fetch_cbr_rate(self) -> Optional[float]:
        """
        Получить курс USD/RUB с API ЦБ РФ.

        Returns:
            float или None при ошибке
        """
        try:
            async with aiohttp.ClientSession() as http_session:
                async with http_session.get(CBR_API_URL, timeout=10) as response:
                    if response.status != 200:
                        logger.error(f"CBR API вернул статус {response.status}")
                        return None

                    xml_text = await response.text()

            # Парсим XML
            root = ET.fromstring(xml_text)

            # Ищем USD
            for valute in root.findall(".//Valute"):
                char_code = valute.find("CharCode")
                if char_code is not None and char_code.text == "USD":
                    value = valute.find("Value")
                    nominal = valute.find("Nominal")

                    if value is not None and nominal is not None:
                        # ЦБ возвращает значение с запятой
                        rate = float(value.text.replace(",", "."))
                        nom = int(nominal.text)
                        return rate / nom

            logger.error("USD не найден в ответе CBR")
            return None

        except aiohttp.ClientError as e:
            logger.error(f"Ошибка HTTP при запросе к CBR: {e}")
            return None
        except ET.ParseError as e:
            logger.error(f"Ошибка парсинга XML от CBR: {e}")
            return None
        except Exception as e:
            logger.error(f"Неожиданная ошибка при получении курса: {e}")
            return None

    def _calculate_star_rate(self, usd_rub: float) -> float:
        """
        Рассчитать курс Stars по формуле.

        Формула: star_rub = USD_RUB * 0.013 * 0.9
        Минимум: 1.0 ₽
        """
        multiplier = STARS_CONFIG["usd_multiplier"]  # 0.013
        discount = STARS_CONFIG["discount"]  # 0.9
        min_rate = STARS_CONFIG["min_rate_rub"]  # 1.0

        star_rub = usd_rub * multiplier * discount
        return max(star_rub, min_rate)

    async def _get_rate_for_date(self, rate_date: date) -> Optional[ExchangeRate]:
        """Получить курс на конкретную дату"""
        result = await self.session.execute(
            select(ExchangeRate).where(ExchangeRate.rate_date == rate_date)
        )
        return result.scalar_one_or_none()

    async def _get_latest_rate(self) -> Optional[ExchangeRate]:
        """Получить последний доступный курс"""
        result = await self.session.execute(
            select(ExchangeRate)
            .order_by(desc(ExchangeRate.rate_date))
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def convert_rub_to_stars(self, amount_rub: float) -> int:
        """
        Конвертировать рубли в Stars.

        Args:
            amount_rub: Сумма в рублях

        Returns:
            Количество Stars (округление вниз)
        """
        rate = await self.get_current_rate()
        stars = int(amount_rub / rate)
        return max(stars, 1) if amount_rub > 0 else 0

    async def convert_stars_to_rub(self, stars: int) -> float:
        """
        Конвертировать Stars в рубли.

        Args:
            stars: Количество Stars

        Returns:
            Сумма в рублях
        """
        rate = await self.get_current_rate()
        return stars * rate

    async def get_price_in_both(self, price_rub: float) -> dict:
        """
        Получить цену в обеих валютах.

        Args:
            price_rub: Цена в рублях

        Returns:
            {"rub": 100.0, "stars": 95}
        """
        rate = await self.get_current_rate()
        stars = int(price_rub / rate)
        return {
            "rub": price_rub,
            "stars": max(stars, 1),
            "rate": rate,
        }


async def update_exchange_rate_task(session: AsyncSession):
    """
    Задача для cron — обновление курса в 4:00 МСК.

    Вызывается из main.py
    """
    service = ExchangeRateService(session)
    success, message = await service.update_rate()
    logger.info(f"Cron update_exchange_rate: {message}")
    return success


def format_rate_info(rate: float, usd_rub: float) -> str:
    """Форматирование информации о курсе для отображения"""
    return (
        f"📊 <b>Курс Stars:</b>\n"
        f"   • 1 ⭐ = {rate:.2f} ₽\n"
        f"   • USD/RUB = {usd_rub:.2f}\n"
        f"\n"
        f"<i>Обновляется ежедневно в 4:00 МСК</i>"
    )
