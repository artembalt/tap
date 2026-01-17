# bot/services/robokassa.py
"""
Сервис для работы с Robokassa.

Документация: https://docs.robokassa.ru/
"""

import hashlib
import logging
from typing import Optional, Tuple
from urllib.parse import urlencode

from bot.config.settings import settings

logger = logging.getLogger(__name__)

# URL для формирования платежа
ROBOKASSA_URL = "https://auth.robokassa.ru/Merchant/Index.aspx"


def generate_payment_url(
    amount: float,
    inv_id: int,
    description: str,
    user_id: int,
    email: Optional[str] = None,
) -> str:
    """
    Генерирует URL для оплаты через Robokassa.

    Args:
        amount: Сумма платежа в рублях
        inv_id: Уникальный номер счёта (InvId)
        description: Описание платежа
        user_id: ID пользователя Telegram (передаётся в Shp_user_id)
        email: Email пользователя (опционально)

    Returns:
        URL для перехода на страницу оплаты
    """
    merchant_login = settings.ROBOKASSA_MERCHANT_LOGIN
    password1 = settings.ROBOKASSA_PASSWORD1

    # Формируем подпись: MerchantLogin:OutSum:InvId:Password1:Shp_user_id
    # Shp_ параметры должны быть в алфавитном порядке
    signature_string = f"{merchant_login}:{amount:.2f}:{inv_id}:{password1}:Shp_user_id={user_id}"
    signature = hashlib.sha256(signature_string.encode()).hexdigest()

    # Параметры запроса
    params = {
        "MerchantLogin": merchant_login,
        "OutSum": f"{amount:.2f}",
        "InvId": inv_id,
        "Description": description,
        "SignatureValue": signature,
        "Shp_user_id": user_id,
        "Culture": "ru",
        "Encoding": "utf-8",
    }

    # Добавляем email если есть
    if email:
        params["Email"] = email

    # Тестовый режим
    if settings.ROBOKASSA_TEST_MODE:
        params["IsTest"] = 1

    url = f"{ROBOKASSA_URL}?{urlencode(params)}"

    logger.info(f"Robokassa payment URL generated: inv_id={inv_id}, amount={amount}, user_id={user_id}")

    return url


def verify_result_signature(
    out_sum: str,
    inv_id: str,
    signature: str,
    shp_user_id: str,
) -> bool:
    """
    Проверяет подпись Result URL (уведомление об оплате).

    Формат: OutSum:InvId:Password2:Shp_user_id

    Returns:
        True если подпись верна
    """
    password2 = settings.ROBOKASSA_PASSWORD2

    # Shp_ параметры в алфавитном порядке
    expected_string = f"{out_sum}:{inv_id}:{password2}:Shp_user_id={shp_user_id}"
    expected_signature = hashlib.sha256(expected_string.encode()).hexdigest().upper()

    is_valid = signature.upper() == expected_signature

    if not is_valid:
        logger.warning(
            f"Robokassa signature mismatch: inv_id={inv_id}, "
            f"received={signature}, expected={expected_signature}"
        )

    return is_valid


def verify_success_signature(
    out_sum: str,
    inv_id: str,
    signature: str,
    shp_user_id: str,
) -> bool:
    """
    Проверяет подпись Success URL (редирект после успешной оплаты).

    Формат: OutSum:InvId:Password1:Shp_user_id

    Returns:
        True если подпись верна
    """
    password1 = settings.ROBOKASSA_PASSWORD1

    expected_string = f"{out_sum}:{inv_id}:{password1}:Shp_user_id={shp_user_id}"
    expected_signature = hashlib.sha256(expected_string.encode()).hexdigest().upper()

    return signature.upper() == expected_signature


def parse_amount(out_sum: str) -> float:
    """Парсит сумму из строки Robokassa"""
    try:
        return float(out_sum.replace(",", "."))
    except (ValueError, AttributeError):
        return 0.0


def parse_inv_id(inv_id: str) -> int:
    """Парсит InvId из строки"""
    try:
        return int(inv_id)
    except (ValueError, TypeError):
        return 0
