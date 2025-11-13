import requests
import base64

LM_STUDIO_URL = "http://localhost:1234/v1/chat/completions"  # Стандартный URL LM Studio
LM_STUDIO_MODEL = "google/gemma-3-4b"  # Можно изменить на нужную модель
SYSTEM_PROMPT = "отвечай на вопросы"
def image_to_base64(img_path="img.png"):
    """Конвертация изображения в base64"""
    try:
        # Получаем скриншот элемента
        with open(img_path, "rb") as img_element:
            img_base64 = base64.b64encode(img_element.read()).decode('utf-8')
            return img_base64
    except Exception as e:
        print(f"⚠️ Не удалось конвертировать изображение: {e}")
        return None


def query_lm_studio(question_text, images_base64=[image_to_base64()]):
    """Отправка запроса в LM Studio API с поддержкой изображений"""
    try:
        # Формируем контент сообщения
        content = []
        
        # Добавляем текст вопроса
        content.append({
            "type": "text",
            "text": question_text
        })
        
        # Добавляем изображения, если есть
        if images_base64:
            for img_b64 in images_base64:
                content.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{img_b64}"
                    }
                })
        
        payload = {
            "model": LM_STUDIO_MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": content if images_base64 else question_text}
            ],
            "temperature": 0.3,
            "max_tokens": 500
        }
        
        print(f"🤖 Отправка запроса в LM Studio...")
        response = requests.post(LM_STUDIO_URL, json=payload, timeout=60)
        
        if response.status_code == 200:
            result = response.json()
            answer = result['choices'][0]['message']['content'].strip()
            print(f"✅ Получен ответ: {answer}")
            return answer
        else:
            print(f"❌ Ошибка LM Studio API: {response.status_code}")
            print(f"Ответ: {response.text}")
            return None
            
    except requests.exceptions.ConnectionError:
        print("❌ Не удалось подключиться к LM Studio. Убедитесь, что сервер запущен на http://localhost:1234")
        return None
    except Exception as e:
        print(f"❌ Ошибка при запросе к LM Studio: {e}")
        return None

print(query_lm_studio("Что на картинке?"))
