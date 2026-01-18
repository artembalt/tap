# bot/services/robokassa.py
"""
Сервис для работы с Robokassa.

Документация: https://docs.robokassa.ru/
"""

import hashlib
import logging
import time
from typing import Optional, Dict, Any
from urllib.parse import urlencode

from bot.config.settings import settings

logger = logging.getLogger(__name__)

# Специальный логгер для платежей (для удобной фильтрации)
payment_logger = logging.getLogger("payments.robokassa")

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


# =============================================================================
# ЛОГИРОВАНИЕ ПЛАТЕЖЕЙ
# =============================================================================

class PaymentLogger:
    """Структурированное логирование платежей Robokassa"""

    @staticmethod
    def log_payment_created(
        inv_id: int,
        user_id: int,
        amount: float,
        description: str
    ):
        """Логирование создания платежа"""
        payment_logger.info(
            f"[PAYMENT] CREATE | inv_id={inv_id} | user={user_id} | "
            f"amount={amount:.2f}₽ | desc={description[:50]}"
        )

    @staticmethod
    def log_webhook_received(
        endpoint: str,
        inv_id: str,
        ip: str,
        params: Dict[str, Any]
    ):
        """Логирование входящего webhook"""
        # Скрываем подпись в логах
        safe_params = {k: v for k, v in params.items() if k != "SignatureValue"}
        safe_params["SignatureValue"] = "***"
        payment_logger.info(
            f"[PAYMENT] WEBHOOK {endpoint} | inv_id={inv_id} | IP={ip} | params={safe_params}"
        )

    @staticmethod
    def log_signature_invalid(
        inv_id: str,
        ip: str,
        received: str,
        expected: str
    ):
        """Логирование неверной подписи"""
        payment_logger.warning(
            f"[PAYMENT] SIGNATURE_INVALID | inv_id={inv_id} | IP={ip} | "
            f"received={received[:16]}... | expected={expected[:16]}..."
        )

    @staticmethod
    def log_payment_success(
        inv_id: str,
        user_id: int,
        amount: float,
        balance_before: float,
        balance_after: float,
        ip: str,
        duration_ms: int
    ):
        """Логирование успешного платежа"""
        payment_logger.info(
            f"[PAYMENT] SUCCESS | inv_id={inv_id} | user={user_id} | "
            f"amount={amount:.2f}₽ | balance: {balance_before:.0f}→{balance_after:.0f}₽ | "
            f"IP={ip} | {duration_ms}ms"
        )

    @staticmethod
    def log_payment_duplicate(inv_id: str, ip: str):
        """Логирование дубликата уведомления"""
        payment_logger.info(
            f"[PAYMENT] DUPLICATE | inv_id={inv_id} | IP={ip} | already processed"
        )

    @staticmethod
    def log_payment_error(
        inv_id: str,
        error: str,
        ip: str = None,
        user_id: int = None
    ):
        """Логирование ошибки платежа"""
        parts = [f"[PAYMENT] ERROR | inv_id={inv_id}"]
        if user_id:
            parts.append(f"user={user_id}")
        if ip:
            parts.append(f"IP={ip}")
        parts.append(f"error={error}")
        payment_logger.error(" | ".join(parts))

    @staticmethod
    def log_payment_failed(inv_id: str, user_id: str, ip: str):
        """Логирование отменённого платежа (Fail URL)"""
        payment_logger.info(
            f"[PAYMENT] FAILED | inv_id={inv_id} | user={user_id} | IP={ip} | "
            f"user cancelled or payment declined"
        )

    @staticmethod
    def log_user_redirect(endpoint: str, inv_id: str, ip: str):
        """Логирование редиректа пользователя"""
        payment_logger.info(
            f"[PAYMENT] REDIRECT {endpoint} | inv_id={inv_id} | IP={ip}"
        )
