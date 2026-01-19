# bot/services/ai_description.py
"""
Сервис улучшения описаний объявлений с помощью YandexGPT.
"""

import logging
import json
import httpx
from typing import Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class AIDescriptionResult:
    """Результат улучшения описания"""
    success: bool
    improved_text: Optional[str] = None
    error: Optional[str] = None


# Системный промпт для улучшения описаний
IMPROVE_DESCRIPTION_PROMPT = """Ты — помощник для написания объявлений о продаже на торговой площадке.

Твоя задача — улучшить описание объявления, сохранив всю информацию от пользователя.

Правила:
1. Сохрани ВСЮ фактическую информацию из оригинала
2. Исправь орфографию и пунктуацию
3. Сделай текст более читаемым и структурированным
4. Добавь эмодзи где уместно (не больше 2-3)
5. Длина: 2-5 предложений (не больше 500 символов)
6. Тон: дружелюбный, но деловой
7. НЕ добавляй информацию, которой нет в оригинале
8. НЕ добавляй цену, контакты, призывы "звоните/пишите"
9. Пиши на русском языке

Верни ТОЛЬКО улучшенный текст описания, без пояснений."""


class AIDescriptionService:
    """Сервис улучшения описаний через YandexGPT API"""

    def __init__(
        self,
        api_key: str,
        folder_id: str,
        model: str = "yandexgpt-lite",
    ):
        self.api_key = api_key
        self.folder_id = folder_id
        self.model = model
        self.api_url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"

    async def improve_description(
        self,
        original_text: str,
        title: str = None,
        category: str = None,
        subcategory: str = None,
    ) -> AIDescriptionResult:
        """
        Улучшить описание объявления.
        """
        if not self.api_key or not self.folder_id:
            logger.warning("[AI_DESC] YandexGPT API не настроен")
            return AIDescriptionResult(
                success=False,
                error="Функция временно недоступна"
            )

        if not original_text or len(original_text.strip()) < 5:
            return AIDescriptionResult(
                success=False,
                error="Описание слишком короткое"
            )

        try:
            result = await self._call_yandexgpt(original_text, title, category, subcategory)
            return result
        except Exception as e:
            logger.error(f"[AI_DESC] Ошибка: {type(e).__name__}: {e}")
            return AIDescriptionResult(
                success=False,
                error="Сервис временно недоступен, попробуйте позже"
            )

    async def _call_yandexgpt(
        self,
        original_text: str,
        title: str = None,
        category: str = None,
        subcategory: str = None,
    ) -> AIDescriptionResult:
        """Вызов YandexGPT API"""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Api-Key {self.api_key}",
            "x-folder-id": self.folder_id
        }

        # Формируем контекст
        context_parts = []
        if title:
            context_parts.append(f"Заголовок: {title}")
        if category:
            context_parts.append(f"Категория: {category}")
        if subcategory:
            context_parts.append(f"Рубрика: {subcategory}")

        context = "\n".join(context_parts) if context_parts else ""

        user_message = f"""{context}

Оригинальное описание от пользователя:
{original_text[:1000]}

Улучши это описание:"""

        payload = {
            "modelUri": f"gpt://{self.folder_id}/{self.model}/latest",
            "completionOptions": {
                "stream": False,
                "temperature": 0.7,  # Немного креативности для улучшения текста
                "maxTokens": 512
            },
            "messages": [
                {
                    "role": "system",
                    "text": IMPROVE_DESCRIPTION_PROMPT
                },
                {
                    "role": "user",
                    "text": user_message
                }
            ]
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                self.api_url,
                headers=headers,
                json=payload
            )

            if response.status_code >= 400:
                response_body = response.text
                logger.error(f"[AI_DESC] API error {response.status_code}: {response_body[:200]}")
                return AIDescriptionResult(success=False, error="Ошибка генерации")

            data = response.json()

        # Парсим ответ YandexGPT
        # Формат: {"result": {"alternatives": [{"message": {"role": "assistant", "text": "..."}}]}}
        try:
            content = data["result"]["alternatives"][0]["message"]["text"]
        except (KeyError, IndexError):
            logger.warning(f"[AI_DESC] Неожиданный формат ответа: {data}")
            return AIDescriptionResult(success=False, error="Не удалось улучшить описание")

        content = content.strip()

        if not content:
            return AIDescriptionResult(success=False, error="Не удалось улучшить описание")

        # Обрезаем если слишком длинное
        if len(content) > 1000:
            content = content[:997] + "..."

        logger.info(f"[AI_DESC] Успешно улучшено: {len(original_text)} -> {len(content)} символов")

        return AIDescriptionResult(success=True, improved_text=content)


# Глобальный экземпляр сервиса
_service: Optional[AIDescriptionService] = None


def get_ai_description_service() -> Optional[AIDescriptionService]:
    """Получить экземпляр сервиса"""
    global _service
    if _service is None:
        try:
            from bot.config import settings
            if settings.YANDEX_GPT_API_KEY and settings.YANDEX_GPT_FOLDER_ID and settings.AI_DESCRIPTION_ENABLED:
                _service = AIDescriptionService(
                    api_key=settings.YANDEX_GPT_API_KEY,
                    folder_id=settings.YANDEX_GPT_FOLDER_ID,
                    model=settings.YANDEX_GPT_MODEL,
                )
                logger.info(f"[AI_DESC] Сервис инициализирован (model={settings.YANDEX_GPT_MODEL})")
            else:
                logger.info("[AI_DESC] Сервис отключен (не настроен YandexGPT)")
        except Exception as e:
            logger.error(f"[AI_DESC] Ошибка инициализации: {e}")
    return _service


async def improve_description(
    original_text: str,
    title: str = None,
    category: str = None,
    subcategory: str = None,
) -> AIDescriptionResult:
    """
    Удобная функция для улучшения описания.

    Использование:
        result = await improve_description("телефон норм сост", title="iPhone 15")
        if result.success:
            print(result.improved_text)
    """
    service = get_ai_description_service()
    if service is None:
        return AIDescriptionResult(
            success=False,
            error="Функция временно недоступна"
        )
    return await service.improve_description(original_text, title, category, subcategory)
