
import re
from typing import Optional, List, Dict, Any

def validate_price(price_text: str) -> Optional[float]:
    """Валидация цены"""
    try:
        price_text = re.sub(r'[^\d.]', '', price_text)
        return float(price_text)
    except (ValueError, TypeError):
        return None

def validate_phone(phone: str) -> Optional[str]:
    """Валидация телефона"""
    phone = re.sub(r'\D', '', phone)
    
    if len(phone) == 11 and phone[0] in '78':
        return f"+7{phone[1:]}"
    elif len(phone) == 10:
        return f"+7{phone}"
    
    return None

async def validate_description(description: str) -> Dict[str, Any]:
    """Валидация описания"""
    result = {"valid": True, "error": None}
    
    if len(description) < 10:
        result["valid"] = False
        result["error"] = "Описание слишком короткое (минимум 10 символов)"
    elif len(description) > 2000:
        result["valid"] = False
        result["error"] = "Описание слишком длинное (максимум 2000 символов)"
    
    return result

async def check_spam_words(text: str) -> bool:
    """Проверка на спам-слова"""
    spam_words = ["заработок", "криптовалюта", "млм"]
    text_lower = text.lower()
    return any(word in text_lower for word in spam_words)

def validate_hashtags(text: str) -> List[str]:
    """Извлечение хэштегов из текста"""
    hashtags = re.findall(r'#\w+', text)
    return hashtags[:10]
