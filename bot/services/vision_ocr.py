# bot/services/vision_ocr.py
"""
Сервис распознавания текста на изображениях через Yandex Vision OCR.
Используется для проверки фото объявлений на запрещённый контент.
"""

import logging
import base64
import httpx
from typing import Optional, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class OCRResult:
    """Результат распознавания текста"""
    success: bool
    text: Optional[str] = None  # Распознанный текст
    confidence: float = 0.0  # Средняя уверенность
    error: Optional[str] = None


class VisionOCRService:
    """Сервис распознавания текста через Yandex Vision OCR"""

    def __init__(self, api_key: str, folder_id: str):
        self.api_key = api_key
        self.folder_id = folder_id
        self.api_url = "https://ocr.api.cloud.yandex.net/ocr/v1/recognizeText"

    async def recognize_text(
        self,
        image_data: bytes,
        mime_type: str = "JPEG"
    ) -> OCRResult:
        """
        Распознать текст на изображении.

        Args:
            image_data: Байты изображения
            mime_type: Тип файла (JPEG, PNG, PDF)

        Returns:
            OCRResult с распознанным текстом
        """
        if not self.api_key or not self.folder_id:
            logger.warning("[OCR] Yandex Vision не настроен")
            return OCRResult(success=False, error="OCR не настроен")

        if not image_data:
            return OCRResult(success=False, error="Пустое изображение")

        try:
            # Кодируем изображение в base64
            content_base64 = base64.b64encode(image_data).decode('utf-8')

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Api-Key {self.api_key}",
                "x-folder-id": self.folder_id
            }

            payload = {
                "mimeType": mime_type.upper(),
                "languageCodes": ["*"],  # Автоопределение языка
                "model": "page",  # Модель для распознавания страниц
                "content": content_base64
            }

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.api_url,
                    headers=headers,
                    json=payload
                )

                if response.status_code >= 400:
                    logger.error(f"[OCR] API error {response.status_code}: {response.text[:200]}")
                    return OCRResult(success=False, error="Ошибка распознавания")

                data = response.json()

            # Парсим ответ
            return self._parse_response(data)

        except httpx.TimeoutException:
            logger.warning("[OCR] Таймаут запроса")
            return OCRResult(success=False, error="Таймаут")
        except Exception as e:
            logger.error(f"[OCR] Ошибка: {type(e).__name__}: {e}")
            return OCRResult(success=False, error="Ошибка распознавания")

    def _parse_response(self, data: dict) -> OCRResult:
        """Парсинг ответа от Yandex Vision OCR"""
        try:
            # Формат ответа:
            # {"result": {"textAnnotation": {"fullText": "...", "blocks": [...]}}}
            result = data.get("result", {})
            text_annotation = result.get("textAnnotation", {})

            full_text = text_annotation.get("fullText", "").strip()

            if not full_text:
                # Текст не найден — это нормально для фото без текста
                return OCRResult(success=True, text="", confidence=1.0)

            # Вычисляем среднюю уверенность из блоков
            blocks = text_annotation.get("blocks", [])
            confidences = []
            for block in blocks:
                for line in block.get("lines", []):
                    for word in line.get("words", []):
                        conf = word.get("confidence", 0)
                        if conf:
                            confidences.append(float(conf))

            avg_confidence = sum(confidences) / len(confidences) if confidences else 0.5

            logger.info(f"[OCR] Распознано {len(full_text)} символов, confidence={avg_confidence:.2f}")

            return OCRResult(
                success=True,
                text=full_text,
                confidence=avg_confidence
            )

        except Exception as e:
            logger.warning(f"[OCR] Ошибка парсинга: {e}, data: {str(data)[:200]}")
            return OCRResult(success=False, error="Ошибка парсинга ответа")

    async def recognize_from_url(self, url: str) -> OCRResult:
        """
        Распознать текст по URL изображения.
        Сначала скачивает изображение, потом распознаёт.
        """
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(url)
                if response.status_code != 200:
                    return OCRResult(success=False, error="Не удалось скачать изображение")

                # Определяем тип по content-type
                content_type = response.headers.get("content-type", "image/jpeg")
                if "png" in content_type:
                    mime_type = "PNG"
                elif "pdf" in content_type:
                    mime_type = "PDF"
                else:
                    mime_type = "JPEG"

                return await self.recognize_text(response.content, mime_type)

        except Exception as e:
            logger.error(f"[OCR] Ошибка загрузки URL: {e}")
            return OCRResult(success=False, error="Ошибка загрузки изображения")


# Глобальный экземпляр сервиса
_service: Optional[VisionOCRService] = None


def get_vision_ocr_service() -> Optional[VisionOCRService]:
    """Получить экземпляр сервиса OCR"""
    global _service
    if _service is None:
        try:
            from bot.config import settings
            # Используем отдельный ключ для Vision, если есть
            api_key = settings.YANDEX_VISION_API_KEY or settings.YANDEX_GPT_API_KEY
            if api_key and settings.YANDEX_GPT_FOLDER_ID:
                _service = VisionOCRService(
                    api_key=api_key,
                    folder_id=settings.YANDEX_GPT_FOLDER_ID
                )
                key_source = "YANDEX_VISION_API_KEY" if settings.YANDEX_VISION_API_KEY else "YANDEX_GPT_API_KEY"
                logger.info(f"[OCR] Yandex Vision OCR сервис инициализирован (key={key_source})")
            else:
                logger.info("[OCR] Yandex Vision OCR не настроен")
        except Exception as e:
            logger.error(f"[OCR] Ошибка инициализации: {e}")
    return _service


async def recognize_text_on_image(image_data: bytes, mime_type: str = "JPEG") -> OCRResult:
    """
    Удобная функция для распознавания текста.

    Использование:
        result = await recognize_text_on_image(photo_bytes)
        if result.success and result.text:
            print(f"Найден текст: {result.text}")
    """
    service = get_vision_ocr_service()
    if service is None:
        return OCRResult(success=False, error="OCR не настроен")
    return await service.recognize_text(image_data, mime_type)
