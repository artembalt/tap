# bot/services/local_moderation.py
"""
Локальная модерация изображений без облачных API.
- PaddleOCR для распознавания текста
- NudeNet для детекции NSFW-контента
"""

import logging
import asyncio
from io import BytesIO
from typing import Optional, List, Tuple
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
from functools import partial

logger = logging.getLogger(__name__)

# Глобальные модели (ленивая загрузка)
_ocr_model = None
_nsfw_detector = None
_executor = ThreadPoolExecutor(max_workers=2)


@dataclass
class LocalModerationResult:
    """Результат локальной модерации"""
    is_safe: bool
    nsfw_score: float = 0.0  # 0-1, где 1 = точно NSFW
    recognized_text: str = ""
    nsfw_labels: List[str] = None  # Обнаруженные NSFW-метки
    error: Optional[str] = None

    def __post_init__(self):
        if self.nsfw_labels is None:
            self.nsfw_labels = []


def _get_ocr_model():
    """Ленивая загрузка PaddleOCR"""
    global _ocr_model
    if _ocr_model is None:
        try:
            # Отключаем логи PaddlePaddle
            import logging as log
            log.getLogger('ppocr').setLevel(log.WARNING)
            log.getLogger('paddle').setLevel(log.WARNING)

            from paddleocr import PaddleOCR
            # Минимальные параметры для новой версии API
            _ocr_model = PaddleOCR(lang='ru')
            logger.info("[LocalMod] PaddleOCR загружен")
        except Exception as e:
            logger.error(f"[LocalMod] Ошибка загрузки PaddleOCR: {e}")
    return _ocr_model


def _get_nsfw_detector():
    """Ленивая загрузка NudeNet"""
    global _nsfw_detector
    if _nsfw_detector is None:
        try:
            from nudenet import NudeDetector
            _nsfw_detector = NudeDetector()
            logger.info("[LocalMod] NudeNet загружен")
        except Exception as e:
            logger.error(f"[LocalMod] Ошибка загрузки NudeNet: {e}")
    return _nsfw_detector


def _recognize_text_sync(image_bytes: bytes) -> str:
    """Синхронное распознавание текста (для ThreadPool)"""
    ocr = _get_ocr_model()
    if ocr is None:
        return ""

    try:
        import numpy as np
        from PIL import Image

        # Конвертируем bytes в numpy array
        image = Image.open(BytesIO(image_bytes))
        image_np = np.array(image)

        # Распознаём текст
        result = ocr.ocr(image_np, cls=True)

        if not result or not result[0]:
            return ""

        # Собираем весь текст
        texts = []
        for line in result[0]:
            if line and len(line) >= 2:
                text = line[1][0]  # Текст
                confidence = line[1][1]  # Уверенность
                if confidence > 0.5:  # Фильтруем низкую уверенность
                    texts.append(text)

        return " ".join(texts)

    except Exception as e:
        logger.warning(f"[LocalMod] Ошибка OCR: {e}")
        return ""


def _detect_nsfw_sync(image_bytes: bytes) -> Tuple[float, List[str]]:
    """Синхронная детекция NSFW (для ThreadPool)"""
    detector = _get_nsfw_detector()
    if detector is None:
        return 0.0, []

    try:
        import tempfile
        import os

        # NudeNet требует файл, создаём временный
        with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as f:
            f.write(image_bytes)
            temp_path = f.name

        try:
            # Детекция
            detections = detector.detect(temp_path)

            # NSFW-классы, которые считаем запрещёнными
            nsfw_classes = {
                'FEMALE_BREAST_EXPOSED': 0.9,
                'FEMALE_GENITALIA_EXPOSED': 1.0,
                'MALE_GENITALIA_EXPOSED': 1.0,
                'BUTTOCKS_EXPOSED': 0.7,
                'ANUS_EXPOSED': 1.0,
                'FEMALE_BREAST_COVERED': 0.3,  # Низкий вес для прикрытого
                'BELLY_EXPOSED': 0.1,
                'ARMPITS_EXPOSED': 0.0,  # Это нормально
                'FEET_EXPOSED': 0.0,  # Это нормально
                'FACE_FEMALE': 0.0,
                'FACE_MALE': 0.0,
            }

            max_score = 0.0
            found_labels = []

            for det in detections:
                label = det.get('class', '')
                confidence = det.get('score', 0)

                if label in nsfw_classes:
                    weight = nsfw_classes[label]
                    score = confidence * weight

                    if score > 0.3:  # Порог для записи метки
                        found_labels.append(f"{label}:{confidence:.2f}")

                    if score > max_score:
                        max_score = score

            return max_score, found_labels

        finally:
            os.unlink(temp_path)

    except Exception as e:
        logger.warning(f"[LocalMod] Ошибка NSFW-детекции: {e}")
        return 0.0, []


async def moderate_image(
    image_bytes: bytes,
    check_nsfw: bool = True,
    check_text: bool = True,
    nsfw_threshold: float = 0.6
) -> LocalModerationResult:
    """
    Модерация изображения локальными моделями.

    Args:
        image_bytes: Байты изображения
        check_nsfw: Проверять на NSFW
        check_text: Распознавать текст
        nsfw_threshold: Порог NSFW (0-1)

    Returns:
        LocalModerationResult
    """
    if not image_bytes:
        return LocalModerationResult(is_safe=False, error="Пустое изображение")

    loop = asyncio.get_event_loop()

    nsfw_score = 0.0
    nsfw_labels = []
    recognized_text = ""

    try:
        # Запускаем проверки параллельно
        tasks = []

        if check_nsfw:
            tasks.append(loop.run_in_executor(
                _executor,
                partial(_detect_nsfw_sync, image_bytes)
            ))

        if check_text:
            tasks.append(loop.run_in_executor(
                _executor,
                partial(_recognize_text_sync, image_bytes)
            ))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        idx = 0
        if check_nsfw:
            if isinstance(results[idx], Exception):
                logger.warning(f"[LocalMod] NSFW error: {results[idx]}")
            else:
                nsfw_score, nsfw_labels = results[idx]
            idx += 1

        if check_text:
            if isinstance(results[idx], Exception):
                logger.warning(f"[LocalMod] OCR error: {results[idx]}")
            else:
                recognized_text = results[idx]

        # Определяем безопасность
        is_safe = nsfw_score < nsfw_threshold

        if nsfw_labels:
            logger.info(f"[LocalMod] NSFW: score={nsfw_score:.2f}, labels={nsfw_labels}")
        if recognized_text:
            logger.info(f"[LocalMod] OCR: {len(recognized_text)} символов")

        return LocalModerationResult(
            is_safe=is_safe,
            nsfw_score=nsfw_score,
            recognized_text=recognized_text,
            nsfw_labels=nsfw_labels
        )

    except Exception as e:
        logger.error(f"[LocalMod] Ошибка модерации: {e}")
        return LocalModerationResult(is_safe=True, error=str(e))


async def check_image_content(
    image_bytes: bytes,
    category: str = None
) -> Tuple[bool, str]:
    """
    Проверка изображения на запрещённый контент.
    Возвращает (is_valid, reason).

    Использование:
        is_valid, reason = await check_image_content(photo_bytes, "electronics")
        if not is_valid:
            await message.answer(f"Фото отклонено: {reason}")
    """
    from bot.utils.content_filter import validate_content

    # Модерируем локально
    result = await moderate_image(
        image_bytes,
        check_nsfw=True,
        check_text=True,
        nsfw_threshold=0.6
    )

    # Проверка NSFW
    if not result.is_safe:
        return False, f"Обнаружен недопустимый контент (NSFW: {result.nsfw_score:.0%})"

    # Проверка текста через rule-based фильтр
    if result.recognized_text:
        filter_result = validate_content(result.recognized_text)
        if not filter_result.is_valid:
            return False, f"На фото обнаружен запрещённый текст: {filter_result.reason}"

    return True, ""


def preload_models():
    """Предзагрузка моделей при старте бота (опционально)"""
    logger.info("[LocalMod] Предзагрузка моделей...")
    _get_ocr_model()
    _get_nsfw_detector()
    logger.info("[LocalMod] Модели загружены")


# Проверка доступности
def is_available() -> bool:
    """Проверить, доступны ли локальные модели"""
    try:
        from paddleocr import PaddleOCR
        from nudenet import NudeDetector
        return True
    except ImportError:
        return False
