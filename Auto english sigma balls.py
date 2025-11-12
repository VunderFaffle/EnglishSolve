import time
import os
import base64
import requests
from io import BytesIO
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# ==================== КОНФИГУРАЦИЯ ====================
SITE_URL = "https://esdo.ssuwt.ru/login/index.php"
LOGIN_USERNAME = ""
LOGIN_PASSWORD = ""
COURSE_URL = "https://esdo.ssuwt.ru/course/view.php?id=1105"
WAIT_TIMEOUT = 15

# LM Studio API Configuration
LM_STUDIO_URL = "http://localhost:1234/v1/chat/completions"  # Стандартный URL LM Studio
LM_STUDIO_MODEL = "google/gemma-3-4b"  # Можно изменить на нужную модель

# Глобальная переменная дебага, так удобнее
DEBUG = False

# SYSTEM_PROMPT = """Ты — помощник для прохождения тестов. 
# Твоя задача отвечать максимально кратко и по делу на вопросы теста.
# Отвечай ТОЛЬКО ответом на вопрос, без пояснений и дополнительного текста, указывать номер ответа на вопрос или номер вопроса НЕЛЬЗЯ.
# Если требуется письменный ответ на вопрос, отвечай ОБЯЗАТЕЛЬНО на английском, ЗАПРЕЩАЕТСЯ давать ответы на других языках, до тех пор пока это не указано прямым текстом в задании.
# Если в задании требуется писать текстовые ответы полностью "in full", НУЖНО писать всё словами.
# ОБЯЗАТЕЛНЬО полностью следовать тексту задания, любые самовольничества запрещены.
# Если есть нумерация вариантов (1, 2, 3 и т.д.), указывай номер и ответ.
# Формат ответа:
# - Для выбора варианта: просто номер (например: "2")
# - Для текстового ответа: краткий ответ без лишних слов
# - Для множественного выбора: номера через запятую (например: "1, 3, 4")"""

# Доработанный системный промпт. С ним чуть лучше работает но возможно потом ещё лучше будет
SYSTEM_PROMPT = """
You are solving English tests. Follow the algorithm strictly:

1) If multiple choice answers are given:
- Determine which answer is correct in meaning.
- Return ONLY the answer number, without words or comments.
- No explanations.
- If there are multiple choices (multiple choice), return the numbers separated by commas, without spaces, for example: 1, 3, 4

2) If a word or phrase is required:
- Answer in English only.
- Minimum length.
- No quotation marks, no final period.

3) Never add unnecessary phrases.
4) Never retell the question.
5) DO NOT use languages ​​other than English.
"""

# ==================== НАСТРОЙКА БРАУЗЕРА ====================
def setup_driver():
    """Инициализация Chrome драйвера"""
    chrome_options = ChromeOptions()
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    # chrome_options.add_argument("--headless")
    
    try:
        from webdriver_manager.chrome import ChromeDriverManager
        service = ChromeService(ChromeDriverManager().install())
        print("✅ ChromeDriver установлен автоматически")
    except Exception as e:
        print(f"⚠️ Автоустановка не удалась: {e}")
        driver_path = os.path.join(os.path.dirname(__file__), "chromedriver.exe")
        if not os.path.isfile(driver_path):
            raise FileNotFoundError(
                f"❌ chromedriver.exe не найден!\n"
                f"Скачай с https://chromedriver.chromium.org/ и положи в {os.path.dirname(__file__)}"
            )
        service = ChromeService(executable_path=driver_path)
        print("✅ Используется локальный ChromeDriver")
    
    driver = webdriver.Chrome(service=service, options=chrome_options)
    driver.maximize_window()
    return driver

# ==================== LM STUDIO API ====================
def query_lm_studio(question_text, images_base64=None):
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

def image_to_base64(driver, img_element):
    """Конвертация изображения в base64"""
    try:
        # Получаем скриншот элемента
        img_screenshot = img_element.screenshot_as_png
        img_base64 = base64.b64encode(img_screenshot).decode('utf-8')
        return img_base64
    except Exception as e:
        print(f"⚠️ Не удалось конвертировать изображение: {e}")
        return None

# ==================== АВТОРИЗАЦИЯ ====================
def login(driver):
    """Вход на сайт Moodle"""
    print("\n🔐 Авторизация...")
    wait = WebDriverWait(driver, WAIT_TIMEOUT)
    
    try:
        driver.get(SITE_URL)
        time.sleep(2)
        
        # Закрытие попапов
        try:
            popup_selectors = [
                "button[title*='Accept']",
                "button[title*='Принять']",
                ".modal-footer button",
                "input[value*='Принять']"
            ]
            for selector in popup_selectors:
                try:
                    popup = driver.find_element(By.CSS_SELECTOR, selector)
                    popup.click()
                    print("✅ Попап закрыт")
                    time.sleep(1)
                    break
                except NoSuchElementException:
                    continue
        except Exception:
            pass
        
        # Ввод логина и пароля
        username_field = wait.until(EC.presence_of_element_located((By.ID, "username")))
        username_field.clear()
        username_field.send_keys(LOGIN_USERNAME)
        print("✅ Логин введён")
        
        password_field = wait.until(EC.presence_of_element_located((By.ID, "password")))
        password_field.clear()
        password_field.send_keys(LOGIN_PASSWORD)
        print("✅ Пароль введён")
        
        # Поиск кнопки входа
        login_button_selectors = [
            (By.ID, "loginbtn"),
            (By.NAME, "loginbtn"),
            (By.CSS_SELECTOR, "button[type='submit']"),
            (By.CSS_SELECTOR, "input[type='submit'][value*='Войти']"),
        ]
        
        login_button = None
        for by, selector in login_button_selectors:
            try:
                login_button = wait.until(EC.element_to_be_clickable((by, selector)))
                print(f"✅ Кнопка входа найдена")
                break
            except TimeoutException:
                continue
        
        if not login_button:
            raise Exception("❌ Кнопка входа не найдена!")
        
        driver.execute_script("arguments[0].scrollIntoView(true);", login_button)
        time.sleep(0.5)
        login_button.click()
        print("✅ Клик по кнопке входа выполнен")
        
        time.sleep(5)
        
        if "login" in driver.current_url.lower():
            raise Exception(f"❌ Вход не выполнен!")
        
        print(f"✅ Авторизация успешна!")
        
    except Exception as e:
        print(f"\n❌ Ошибка при авторизации: {e}")
        driver.save_screenshot("login_error.png")
        raise

# ==================== ПРОВЕРКА АУДИО ====================
def has_audio_player(driver):
    """Проверка наличия аудио плеера на странице"""
    audio_selectors = [
        "audio",
        "video",
        ".audio-player",
        "[class*='audio']",
        "[id*='audio']",
        "source[type*='audio']"
    ]
    
    for selector in audio_selectors:
        try:
            elements = driver.find_elements(By.CSS_SELECTOR, selector)
            if elements:
                print(f"⚠️ Обнаружен аудио/видео элемент: {selector}")
                return True
        except:
            continue
    
    return False

# ==================== РЕШЕНИЕ ТЕСТА ====================
def solve_quiz(driver, quiz_url, quiz_name):
    """Автоматическое решение теста"""
    global DEBUG
    #Обрезаем название чтобы убрать номера в конце и в начале, чтобы не смущать ИИшку лишними символами
    quiz_name = quiz_name[3:-1] if quiz_name[-1].isdigit() else quiz_name[3:]
    print(f"\n🎯 Начинаем решение теста...")
    wait = WebDriverWait(driver, WAIT_TIMEOUT)
    
    try:
        driver.get(quiz_url)
        time.sleep(3)
        
        # Проверка на аудио
        if has_audio_player(driver):
            print("🎵 Обнаружен аудио плеер - пропускаем тест")
            return False
        
        # Поиск кнопки "Начать попытку" или "Attempt quiz now"
        start_button_selectors = [
            (By.CSS_SELECTOR, "button[type='submit']"),
            (By.XPATH, "//button[contains(text(), 'Начать')]"),
            (By.XPATH, "//button[contains(text(), 'Attempt')]"),
            (By.XPATH, "//input[@type='submit' and contains(@value, 'Начать')]"),
            (By.XPATH, "//input[@type='submit' and contains(@value, 'Продолжить')]"), #!Чтобы можно было продолжать попытки, временная дебаг фича, потом закомментить 
        ]
        
        started = False
        for by, selector in start_button_selectors:
            try:
                start_btn = driver.find_element(by, selector)
                start_btn.click()
                print("✅ Начало попытки прохождения теста")
                time.sleep(3)
                started = True
                break
            except NoSuchElementException:
                continue
        
        if not started:
            print("⚠️ Кнопка начала теста не найдена, возможно тест уже начат")
        
        # Перепроверка на аудио после начала теста
        if has_audio_player(driver):
            print("🎵 Обнаружен аудио плеер в самом тесте - пропускаем")
            return False
        
        # Поиск всех вопросов на странице
        questions = driver.find_elements(By.CSS_SELECTOR, ".que, .formulation")
        
        if not questions:
            print("❌ Вопросы не найдены на странице!")
            driver.save_screenshot("no_questions.png")
            return False
        
        print(f"📝 Найдено вопросов: {len(questions)}")
        
        # Обработка каждого вопроса
        for idx, question in enumerate(questions, 1):
            try:
                print(f"\n--- Вопрос {idx}/{len(questions)} ---")
                
                # Извлечение текста вопроса
                question_text = ""
                try:
                    qtext = question.find_element(By.CSS_SELECTOR, ".qtext")
                    question_text = quiz_name + qtext.text.strip()
                    print(f"❓ Вопрос: {question_text[:100]}...")
                except NoSuchElementException:
                    question_text = quiz_name + question.text.strip()
                
                # Поиск изображений в вопросе
                images_base64 = []
                try:
                    images = question.find_elements(By.TAG_NAME, "img")
                    for img in images:
                        img_b64 = image_to_base64(driver, img)
                        if img_b64:
                            images_base64.append(img_b64)
                            print(f"🖼️ Найдено изображение в вопросе")
                except Exception as e:
                    print(f"⚠️ Ошибка при обработке изображений: {e}")
                
                # Поиск вариантов ответа
                answer_options = []
                try:
                    # Для radio buttons / checkboxes
                    options = question.find_elements(By.CSS_SELECTOR, ".answer label, .r0, .r1")
                    for i, opt in enumerate(options, 1):
                        answer_options.append(f"{i}. {opt.text.strip()}")
                    
                    # if answer_options:
                    #     question_text += "\n\nВарианты ответа:\n" + "\n".join(answer_options)
                except:
                    pass
                
                #? Улучшенный промпт для геммы, так она делает меньше затупов
                prompt = f"""
                QUESTION:
                {question_text}
                OPTIONS:
                {chr(10).join(answer_options) if answer_options else "No answer options in this question, you need to come up with an answer yourself and give it in a text format."}
                ANSWER:
                """
                if DEBUG:
                    print(prompt)
                # Отправка запроса в LM Studio
                ai_answer = query_lm_studio(prompt, images_base64 if images_base64 else None)
                
                if not ai_answer:
                    print("⚠️ Не удалось получить ответ от AI, пропускаем вопрос")
                    continue
                
                # Попытка вставить ответ
                answer_inserted = False
                
                # Попытка 1: Текстовое поле
                try:
                    text_input = question.find_element(By.CSS_SELECTOR, "input[type='text'], textarea")
                    text_input.clear()
                    text_input.send_keys(ai_answer)
                    print(f"✅ Ответ вставлен в текстовое поле: {ai_answer}")
                    answer_inserted = True
                except NoSuchElementException:
                    pass
                
                # Попытка 2: Radio button / Checkbox
                if not answer_inserted:
                    try:
                        # Извлекаем номер из ответа AI
                        answer_number = None
                        for char in ai_answer:
                            if char.isdigit():
                                answer_number = int(char)
                                break
                        
                        if answer_number:
                            # Находим все radio/checkbox
                            inputs = question.find_elements(By.CSS_SELECTOR, "input[type='radio'], input[type='checkbox']")
                            if answer_number <= len(inputs):
                                target_input = inputs[answer_number - 1]
                                driver.execute_script("arguments[0].click();", target_input)
                                print(f"✅ Выбран вариант №{answer_number}")
                                answer_inserted = True
                    except Exception as e:
                        print(f"⚠️ Ошибка при выборе варианта: {e}")
                
                if not answer_inserted:
                    print("⚠️ Не удалось вставить ответ автоматически")
                
                time.sleep(1)
                
            except Exception as e:
                print(f"⚠️ Ошибка при обработке вопроса {idx}: {e}")
                continue
        
        # Отправка теста
        print("\n📤 Попытка отправить тест...")
        submit_selectors = [
            (By.XPATH, "//button[contains(text(), 'Finish') or contains(text(), 'Завершить')]"),
            (By.CSS_SELECTOR, "button[type='submit']"),
            (By.CSS_SELECTOR, "input[type='submit'][value*='Finish']"),
            (By.CSS_SELECTOR, "input[type='submit'][value*='Завершить']"),
        ]
        
        for by, selector in submit_selectors:
            try:
                submit_btn = driver.find_element(by, selector)
                driver.execute_script("arguments[0].scrollIntoView(true);", submit_btn)
                time.sleep(1)
                submit_btn.click()
                print("✅ Тест отправлен!")
                time.sleep(2)
                
                # Подтверждение отправки, если требуется
                try:
                    confirm_btn = driver.find_element(By.XPATH, "//button[contains(text(), 'Submit') or contains(text(), 'Отправить')]")
                    confirm_btn.click()
                    print("✅ Отправка подтверждена")
                except:
                    pass
                
                time.sleep(3)
                return True
            except NoSuchElementException:
                continue
        
        print("⚠️ Кнопка отправки не найдена")
        return False
        
    except Exception as e:
        print(f"❌ Ошибка при решении теста: {e}")
        driver.save_screenshot("quiz_error.png")
        return False

# ==================== АНАЛИЗ РАЗДЕЛА ====================
def analyze_section(driver, section_number, auto_solve=False):
    """Анализ раздела с опцией автоматического решения"""
    global DEBUG
    print(f"\n📚 Анализ раздела {section_number}...")
    wait = WebDriverWait(driver, WAIT_TIMEOUT)
    
    try:
        driver.get(COURSE_URL)
        time.sleep(3)
        
        section_id = f"section-{section_number}"
        try:
            section = wait.until(EC.presence_of_element_located((By.ID, section_id)))
            print(f"✅ Раздел {section_number} найден")
        except TimeoutException:
            print(f"❌ Раздел с ID '{section_id}' не найден!")
            return None
        
        try:
            section_content = section.find_element(By.CSS_SELECTOR, "ul.section")
        except NoSuchElementException:
            print(f"❌ Контент раздела не найден!")
            return None
        
        quiz_elements = section_content.find_elements(
            By.CSS_SELECTOR, 
            "li.activity.quiz, li.activity.modtype_quiz"
        )
        
        if not quiz_elements:
            print(f"⚠️ В разделе {section_number} нет заданий типа 'quiz'")
            return None
        
        print(f"📝 Найдено заданий: {len(quiz_elements)}\n")
        
        quiz_list = []
        for idx, quiz_elem in enumerate(quiz_elements, 1):
            try:
                link = quiz_elem.find_element(By.CSS_SELECTOR, "a[href*='/mod/quiz/view.php']")
                quiz_url = link.get_attribute("href")
                quiz_id = quiz_url.split("id=")[-1].split("&")[0] if "id=" in quiz_url else "N/A"
                
                try:
                    name_elem = link.find_element(By.CSS_SELECTOR, ".instancename")
                    quiz_name = name_elem.text.strip()
                except NoSuchElementException:
                    quiz_name = link.text.strip()
                
                status = "Неизвестно"
                try:
                    completion_img = quiz_elem.find_element(
                        By.CSS_SELECTOR, 
                        ".autocompletion img, .completion img"
                    )
                    img_src = completion_img.get_attribute("src") or ""
                    img_alt = completion_img.get_attribute("alt") or ""
                    
                    if "completion-auto-pass" in img_src or "pass" in img_alt.lower():
                        status = "✅ Выполнено"
                    elif "completion-auto-n" in img_src or "not completed" in img_alt.lower():
                        status = "⏳ Не выполнено"
                except NoSuchElementException:
                    pass
                
                quiz_data = {
                    "number": idx,
                    "name": quiz_name,
                    "status": status,
                    "quiz_id": quiz_id,
                    "url": quiz_url
                }
                quiz_list.append(quiz_data)
                
                short_name = quiz_name[:60] + "..." if len(quiz_name) > 60 else quiz_name
                print(f"  {idx}. {short_name}")
                print(f"     Статус: {status} | ID: {quiz_id}")
                
            except Exception as e:
                print(f"  ⚠️ Ошибка при обработке задания {idx}: {e}")
                continue
        
        not_completed = [q for q in quiz_list if "⏳" in q["status"]]
        
        if not not_completed:
            print(f"\n🎉 Все задания выполнены!")
            return quiz_list
        
        if auto_solve:
            print(f"\n🤖 Автоматическое решение включено. Обрабатываем невыполненные задания...")
            
            for quiz in not_completed:
                print(f"\n{'='*70}")
                print(f"⏭️ Попытка решить: {quiz['name']}")
                print(f"{'='*70}")

                # Говорит само за себя
                if DEBUG:
                    print(quiz['url'])
                    print(quiz['name'])
                    input()

                # Получаем результат решения
                success = solve_quiz(driver, quiz['url'], quiz['name'])
                
                if success:
                    print(f"🎉 Тест '{quiz['name']}' успешно пройден!")
                    # Небольшая пауза перед следующим тестом
                    time.sleep(2)
                else:
                    print(f"⚠️ Тест '{quiz['name']}' пропущен (содержит аудио или произошла ошибка)")
                    # Продолжаем к следующему заданию
                    continue
            
            print(f"\n{'='*70}")
            print(f"✅ Обработка раздела {section_number} завершена!")
            print(f"{'='*70}")
        else:
            # Режим без автоматического решения - показываем только первое невыполненное
            next_todo = not_completed[0]
            print(f"\n⏭️ Следующее задание: {next_todo['name']}")
            response = input(f"\n🤖 Попытаться решить автоматически? (y/n): ").strip().lower()
            if response == 'y':
                success = solve_quiz(driver, next_todo['url'])
                if success:
                    print("🎉 Тест успешно пройден!")
                else:
                    print("⚠️ Тест пропущен или не удалось пройти")
        
        return quiz_list
        
    except Exception as e:
        print(f"\n❌ Ошибка при анализе раздела: {e}")
        return None

# =================== ПЕРВИЧНАЯ ИНИЦИАЛИЗАЦИЯ ===================
def initialize_credentails():
    """Инициализация файла с учётными данными"""
    print("⚙️ Первый запуск, инициализация файла с учётными данными. Файлы хранятся локально.")
    username = input("Введите ваш логин:")
    password = input("Введите ваш пароль:")
    with open("credentails.txt", "w", encoding="utf-8") as f:
        f.write(f"{username}\n{password}\n")
    print("✅ Файл с учётными данными создан.")


# ==================== ЗАГРУЗКА УЧЁТНЫХ ДАННЫХ ====================
def load_credentails():
    """Загрузка учётных данных из файла"""
    global LOGIN_USERNAME, LOGIN_PASSWORD
    with open("credentails.txt", "r", encoding="utf-8") as f:
        lines = f.readlines()
        if len(lines) >= 2:
            LOGIN_USERNAME = lines[0].strip()
            LOGIN_PASSWORD = lines[1].strip()
        else:
            raise Exception("Файл с учётными данными повреждён или некорректен.")




# ==================== ОСНОВНАЯ ПРОГРАММА ====================
def main():
    global DEBUG

    driver = None
    if not os.path.isfile("credentails.txt"):
        initialize_credentails()
    load_credentails()
    try:
        print("🚀 Запуск автоматического решателя Moodle тестов...")
        print("⚠️ Убедитесь, что LM Studio запущен на http://localhost:1234\n")
        
        driver = setup_driver()
        login(driver)
        
        while True:
            print("\n" + "="*70)
            print("Режимы работы:")
            print("  1. Проанализировать раздел (только просмотр)")
            print("  2. Автоматически решить ВСЕ невыполненные задания в разделе")
            print("  3. Выход")
            print("="*70)
            
            mode = input("Выберите режим (1-3): ").strip()
            
            # Дебаг мод для отладки автосолва
            if mode == "4":
                DEBUG=True
                mode = '2'

            if mode == '3':
                print("👋 Выход из программы...")
                break
            
            if mode not in ['1', '2']:
                print("❌ Неверный режим! Выберите 1, 2 или 3")
                continue
            
            section_input = input("📋 Введите номер раздела: ").strip()
            
            try:
                section_num = int(section_input)
                if section_num <= 0:
                    print("❌ Номер раздела должен быть положительным числом!")
                    continue
                
                auto_solve = (mode == '2')
                analyze_section(driver, section_num, auto_solve=auto_solve)
                
            except ValueError:
                print("❌ Пожалуйста, введите корректное число!")
            except Exception as e:
                print(f"❌ Произошла ошибка: {e}")
    
    except KeyboardInterrupt:
        print("\n\n🛑 Программа остановлена пользователем")
    except Exception as e:
        print(f"\n❌ Критическая ошибка: {e}")
    finally:
        if driver:
            driver.quit()
            print("✅ Браузер закрыт")

if __name__ == "__main__":
    main()