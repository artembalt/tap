# bot/services/ai_description.py
"""
Сервис улучшения описаний объявлений с помощью Claude AI.
Использует тот же API что и модерация (claude-3-haiku).
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
    """Сервис улучшения описаний через Claude API"""

    def __init__(
        self,
        api_key: str,
        model: str = "claude-3-haiku-20240307",
    ):
        self.api_key = api_key
        self.model = model
        self.api_url = "https://api.anthropic.com/v1/messages"

    async def improve_description(
        self,
        original_text: str,
        title: str = None,
        category: str = None,
        subcategory: str = None,
    ) -> AIDescriptionResult:
        """
        Улучшить описание объявления.

        Args:
            original_text: Оригинальное описание от пользователя
            title: Заголовок объявления (для контекста)
            category: Категория (для контекста)
            subcategory: Подкатегория (для контекста)

        Returns:
            AIDescriptionResult с улучшенным текстом или ошибкой
        """
        if not self.api_key:
            logger.warning("[AI_DESC] API ключ не настроен")
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
            result = await self._call_claude(original_text, title, category, subcategory)
            return result
        except httpx.TimeoutException:
            logger.error("[AI_DESC] Таймаут запроса к API")
            return AIDescriptionResult(
                success=False,
                error="Сервис временно недоступен, попробуйте позже"
            )
        except Exception as e:
            logger.error(f"[AI_DESC] Ошибка: {e}")
            return AIDescriptionResult(
                success=False,
                error="Произошла ошибка, попробуйте позже"
            )

    async def _call_claude(
        self,
        original_text: str,
        title: str = None,
        category: str = None,
        subcategory: str = None,
    ) -> AIDescriptionResult:
        """Вызов Claude API для улучшения описания"""
        # DEBUG: проверяем ключ в момент запроса
        logger.info(f"[AI_DESC] DEBUG _call_claude: api_key_len={len(self.api_key)}, api_key={self.api_key[:20]}...{self.api_key[-10:]}")

        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01"
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
            "model": self.model,
            "max_tokens": 512,
            "system": IMPROVE_DESCRIPTION_PROMPT,
            "messages": [
                {
                    "role": "user",
                    "content": user_message
                }
            ]
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                self.api_url,
                headers=headers,
                json=payload
            )

            if response.status_code >= 400:
                logger.error(f"[AI_DESC] HTTP {response.status_code}: {response.text[:200]}")
                return AIDescriptionResult(
                    success=False,
                    error="Сервис временно недоступен"
                )

            data = response.json()

        # Извлекаем текст из ответа
        content = data.get("content", [{}])[0].get("text", "").strip()

        if not content:
            return AIDescriptionResult(
                success=False,
                error="Не удалось улучшить описание"
            )

        # Обрезаем если слишком длинное
        if len(content) > 1000:
            content = content[:997] + "..."

        logger.info(f"[AI_DESC] Успешно улучшено: {len(original_text)} -> {len(content)} символов")

        return AIDescriptionResult(
            success=True,
            improved_text=content
        )


# Глобальный экземпляр сервиса
_service: Optional[AIDescriptionService] = None


def get_ai_description_service() -> Optional[AIDescriptionService]:
    """Получить экземпляр сервиса"""
    global _service
    if _service is None:
        try:
            from bot.config import settings
            # DEBUG: логируем часть ключа для диагностики
            key = settings.CLAUDE_API_KEY or ""
            logger.info(f"[AI_DESC] DEBUG: key_len={len(key)}, start={key[:15]}...")
            if settings.CLAUDE_API_KEY and settings.AI_DESCRIPTION_ENABLED:
                _service = AIDescriptionService(
                    api_key=settings.CLAUDE_API_KEY,
                    model=settings.CLAUDE_MODEL,
                )
                logger.info(f"[AI_DESC] Сервис инициализирован (model={settings.CLAUDE_MODEL})")
            else:
                logger.info("[AI_DESC] Сервис отключен")
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
