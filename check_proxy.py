import anthropic
import httpx

# Ваши данные прокси
proxy_url = "http://user353807:na570m@93.127.144.239:8899"

# Клиент с прокси
client = anthropic.Anthropic(
    api_key="sk-ant-...",  # <--- СЮДА ВСТАВЬТЕ ВАШ КЛЮЧ
    http_client=httpx.Client(proxies=proxy_url)
)

print("Отправляю запрос в Claude...")

try:
    message = client.messages.create(
        model="claude-3-opus-20240229",
        max_tokens=100,
        messages=[
            {"role": "user", "content": "Привет! Если ты видишь это сообщение, значит прокси работает. Напиши 'Успех!'"}
        ]
    )
    print(message.content[0].text)
except Exception as e:
    print(f"Ошибка: {e}")
