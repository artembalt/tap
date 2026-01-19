# bot/services/ai_description.py
"""
Сервис улучшения описаний объявлений с помощью Claude AI.
Использует официальный Anthropic SDK.
"""

import logging
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
    """Сервис улучшения описаний через Claude API (официальный SDK)"""

    def __init__(
        self,
        api_key: str,
        model: str = "claude-3-haiku-20240307",
    ):
        self.api_key = api_key
        self.model = model
        self._client = None

    def _get_client(self):
        """Ленивая инициализация клиента"""
        if self._client is None:
            import anthropic
            import httpx
            # Явно создаём httpx клиент чтобы избежать конфликтов с aiogram
            http_client = httpx.AsyncClient(timeout=30.0)
            self._client = anthropic.AsyncAnthropic(
                api_key=self.api_key,
                http_client=http_client
            )
        return self._client

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
        except Exception as e:
            logger.error(f"[AI_DESC] Ошибка: {type(e).__name__}: {e}")
            return AIDescriptionResult(
                success=False,
                error="Сервис временно недоступен, попробуйте позже"
            )

    async def _call_claude(
        self,
        original_text: str,
        title: str = None,
        category: str = None,
        subcategory: str = None,
    ) -> AIDescriptionResult:
        """Вызов Claude API через subprocess (изоляция от окружения бота)"""
        import asyncio
        import subprocess
        import json

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

        # Используем json.dumps для безопасной сериализации строк
        user_message_json = json.dumps(user_message, ensure_ascii=False)
        system_prompt_json = json.dumps(IMPROVE_DESCRIPTION_PROMPT, ensure_ascii=False)

        # Python скрипт для выполнения в subprocess
        script = f'''
import anthropic
import json

client = anthropic.Anthropic(api_key="{self.api_key}")
try:
    message = client.messages.create(
        model="{self.model}",
        max_tokens=512,
        system={system_prompt_json},
        messages=[{{"role": "user", "content": {user_message_json}}}]
    )
    result = {{"success": True, "text": message.content[0].text}}
except Exception as e:
    result = {{"success": False, "error": str(e)}}
print(json.dumps(result, ensure_ascii=False))
'''

        try:
            # Запускаем в subprocess для изоляции
            # Прокси нужен! Сервер в RU, а Anthropic не работает в RU
            # Прокси выходит из DE — там API работает
            proc = await asyncio.create_subprocess_exec(
                '/home/telegram-ads-platform/tramp/bin/python', '-c', script,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30.0)

            if proc.returncode != 0:
                logger.error(f"[AI_DESC] Subprocess error: {stderr.decode()}")
                return AIDescriptionResult(success=False, error="Ошибка генерации")

            result = json.loads(stdout.decode())

            if not result.get("success"):
                logger.error(f"[AI_DESC] API error: {result.get('error')}")
                return AIDescriptionResult(success=False, error="Сервис временно недоступен")

            content = result.get("text", "").strip()

            if not content:
                return AIDescriptionResult(success=False, error="Не удалось улучшить описание")

            # Обрезаем если слишком длинное
            if len(content) > 1000:
                content = content[:997] + "..."

            logger.info(f"[AI_DESC] Успешно улучшено: {len(original_text)} -> {len(content)} символов")

            return AIDescriptionResult(success=True, improved_text=content)

        except asyncio.TimeoutError:
            logger.error("[AI_DESC] Timeout")
            return AIDescriptionResult(success=False, error="Превышено время ожидания")
        except Exception as e:
            logger.error(f"[AI_DESC] Error: {e}")
            return AIDescriptionResult(success=False, error="Сервис временно недоступен")


# Глобальный экземпляр сервиса
_service: Optional[AIDescriptionService] = None


def get_ai_description_service() -> Optional[AIDescriptionService]:
    """Получить экземпляр сервиса"""
    global _service
    if _service is None:
        try:
            from bot.config import settings
            # Используем отдельный ключ для AI-описаний, если указан
            api_key = settings.AI_DESCRIPTION_API_KEY or settings.CLAUDE_API_KEY
            if api_key and settings.AI_DESCRIPTION_ENABLED:
                _service = AIDescriptionService(
                    api_key=api_key,
                    model=settings.CLAUDE_MODEL,
                )
                key_source = "AI_DESCRIPTION_API_KEY" if settings.AI_DESCRIPTION_API_KEY else "CLAUDE_API_KEY"
                logger.info(f"[AI_DESC] Сервис инициализирован (model={settings.CLAUDE_MODEL}, key={key_source})")
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
