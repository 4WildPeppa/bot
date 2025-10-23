import os
import telebot
from flask import Flask, request, jsonify
from PIL import Image
import io
import numpy as np

# Токен бота из переменных окружения
TOKEN = os.environ.get('BOT_TOKEN', '7530748232:AAF8T5Zsoa-LzqsP9T0gt5hEWYtxBhB3iLE')
bot = telebot.TeleBot(TOKEN)

app = Flask(__name__)
user_data = {}

def analyze_image_colors(image_path):
    """
    Анализирует изображение и определяет, волк это или человек по цветам
    """
    try:
        # Открываем изображение
        img = Image.open(image_path)
        
        # Конвертируем в RGB если нужно
        if img.mode != 'RGB':
            img = img.convert('RGB')
        
        # Преобразуем в numpy array
        img_array = np.array(img)
        
        # Нормализуем значения пикселей (0-1)
        img_normalized = img_array / 255.0
        
        # Определяем цветовые диапазоны
        # Серые цвета (волчья шерсть)
        gray_mask = (
            (img_normalized[:,:,0] > 0.2) & (img_normalized[:,:,0] < 0.8) &
            (img_normalized[:,:,1] > 0.2) & (img_normalized[:,:,1] < 0.8) &
            (img_normalized[:,:,2] > 0.2) & (img_normalized[:,:,2] < 0.8) &
            (np.abs(img_normalized[:,:,0] - img_normalized[:,:,1]) < 0.2) &
            (np.abs(img_normalized[:,:,1] - img_normalized[:,:,2]) < 0.2)
        )
        
        # Коричневые/бежевые цвета (человеческая кожа/одежда)
        brown_mask = (
            (img_normalized[:,:,0] > 0.4) & (img_normalized[:,:,0] < 0.8) &
            (img_normalized[:,:,1] > 0.3) & (img_normalized[:,:,1] < 0.6) &
            (img_normalized[:,:,2] > 0.2) & (img_normalized[:,:,2] < 0.4)
        )
        
        # Белые цвета (снег, может быть волк в снегу)
        white_mask = (
            (img_normalized[:,:,0] > 0.7) &
            (img_normalized[:,:,1] > 0.7) &
            (img_normalized[:,:,2] > 0.7)
        )
        
        # Черные цвета (темная шерсть волка)
        black_mask = (
            (img_normalized[:,:,0] < 0.3) &
            (img_normalized[:,:,1] < 0.3) &
            (img_normalized[:,:,2] < 0.3)
        )
        
        # Считаем количество пикселей каждого типа
        total_pixels = img_array.shape[0] * img_array.shape[1]
        gray_pixels = np.sum(gray_mask)
        brown_pixels = np.sum(brown_mask)
        white_pixels = np.sum(white_mask)
        black_pixels = np.sum(black_mask)
        
        # Проценты
        gray_percent = (gray_pixels / total_pixels) * 100
        brown_percent = (brown_pixels / total_pixels) * 100
        white_percent = (white_pixels / total_pixels) * 100
        black_percent = (black_pixels / total_pixels) * 100
        
        # Простая логика классификации
        wolf_score = gray_percent + black_percent + (white_percent * 0.5)
        human_score = brown_percent
        
        # Дополнительные факторы
        if wolf_score > human_score:
            confidence = wolf_score / (wolf_score + human_score) * 100
            result = f"🐺 Это волк! (уверенность: {confidence:.1f}%)"
        else:
            confidence = human_score / (wolf_score + human_score) * 100
            result = f"👤 Это человек! (уверенность: {confidence:.1f}%)"
        
        # Детальный анализ
        
        
        return result 
        
    except Exception as e:
        return f"Ошибка при анализе изображения: {e}"

# --- Команды бота (остаются без изменений) --- #
@bot.message_handler(commands=['start'])
def send_welcome(message):
    welcome_text = (
        "Приветствуем тебя в стае! 🐺\n"
        "Я анализирую изображения по цветам и определяю, человек это или волк!\n\n"
        "Вот что ты можешь сделать:\n"
        "🐺 /register — присоединиться к стае\n"
        "🐺 /login — войти в стаю\n"
        "🐺 /predict — отправить изображение для анализа\n"
        "🐺 /logout — покинуть стаю\n"
        "🐺 /instructions — узнать, что можно делать\n\n"
        "Начни с команды /register."
    )
    bot.reply_to(message, welcome_text)

@bot.message_handler(func=lambda message: 'спасибо' in message.text.lower())
def thank_you_response(message):
    bot.reply_to(message, "Стая с тобой навсегда! 🐺")

@bot.message_handler(commands=['register'])
def register_user(message):
    chat_id = message.chat.id
    if chat_id in user_data:
        bot.reply_to(message, "Ты уже зарегистрирован. Используй /login")
        return
    bot.reply_to(message, "Придумай пароль для входа:")
    bot.register_next_step_handler(message, process_register_password)

def process_register_password(message):
    chat_id = message.chat.id
    password = message.text.strip()
    user_data[chat_id] = {'password': password, 'logged_in': False}
    bot.reply_to(message, "Поздравляем, ты теперь часть стаи! Запиши пароль. Используй /login для входа.")

@bot.message_handler(commands=['instructions'])
def send_instructions(message):
    instructions_text = (
        "Что же, ищущий да обрящет!\n\n"
        "Я анализирую цвета на изображениях:\n"
        "• Серые, черные, белые оттенки → волк 🐺\n"
        "• Коричневые, бежевые оттенки → человек 👤\n\n"
        "Команды:\n"
        "🐺 /register — присоединиться к стае\n"
        "🐺 /login — войти в стаю\n"
        "🐺 /predict — отправить изображение\n"
        "🐺 /logout — покинуть стаю\n\n"
        "Просто отправь мне фото или используй /predict!"
    )
    bot.reply_to(message, instructions_text)

@bot.message_handler(commands=['login'])
def login_user(message):
    chat_id = message.chat.id
    if chat_id not in user_data:
        bot.reply_to(message, "Ты еще не зарегистрирован. Используй /register.")
        return
    if user_data[chat_id]['logged_in']:
        bot.reply_to(message, "Ты уже в стае, брат мой.")
        return
    bot.reply_to(message, "Введи пароль:")
    bot.register_next_step_handler(message, process_login_password)

def process_login_password(message):
    chat_id = message.chat.id
    password = message.text.strip()
    if user_data[chat_id]['password'] == password:
        user_data[chat_id]['logged_in'] = True
        bot.reply_to(message, "Поздравляем, ты в стае! Отправь фото или используй /predict для анализа.")
    else:
        bot.reply_to(message, "Неверный пароль.")

@bot.message_handler(commands=['logout'])
def logout_user(message):
    chat_id = message.chat.id
    if chat_id in user_data and user_data[chat_id]['logged_in']:
        user_data[chat_id]['logged_in'] = False
        bot.reply_to(message, "Спокойной ночи, стая. Возвращайся! 🐺")
    else:
        bot.reply_to(message, "Нельзя выйти откуда-то, не зайдя куда-то.")

@bot.message_handler(commands=['predict'])
def predict(message):
    chat_id = message.chat.id
    if chat_id not in user_data:
        bot.reply_to(message, "Ты еще не зарегистрирован. Используй /register.")
        return
    if not user_data[chat_id]['logged_in']:
        bot.reply_to(message, "Ты пока не вошел. Используй /login.")
        return
    bot.reply_to(message, "Отправь изображение для анализа цветов! 🐺👤")

@bot.message_handler(content_types=['photo'])
def process_image_prediction(message):
    chat_id = message.chat.id
    
    # Проверяем авторизацию
    if chat_id not in user_data or not user_data[chat_id]['logged_in']:
        bot.reply_to(message, "Сначала войди в стаю используя /login.")
        return
        
    if not message.photo:
        bot.reply_to(message, "Пожалуйста, отправь изображение.")
        return
    
    try:
        bot.reply_to(message, "🔍 Анализирую цвета...")
        
        file_info = bot.get_file(message.photo[-1].file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        # Сохраняем временный файл
        temp_file_path = "temp_image.jpg"
        with open(temp_file_path, 'wb') as new_file:
            new_file.write(downloaded_file)
        
        # Анализируем изображение
        result = analyze_image_colors(temp_file_path)
        
        # Отправляем результат
        bot.reply_to(message, result)
        
        # Удаляем временный файл
        os.remove(temp_file_path)
        
    except Exception as e:
        bot.reply_to(message, f"Ошибка при обработке изображения: {e}")

@bot.message_handler(func=lambda message: True)
def handle_unknown(message):
    if message.text.startswith('/'):
        bot.reply_to(message, "Неизвестная команда. Вот что я умею:")
        send_instructions(message)
    else:
        bot.reply_to(message, "Нам неизвестны такие слова! Вот что ты можешь делать в стае:")
        send_instructions(message)

# Webhook обработчики
@app.route('/', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return 'OK', 200
    return 'Bad Request', 400

@app.route('/', methods=['GET'])
def index():
    return 'Бот-анализатор цветов работает! 🐺', 200

if __name__ == "__main__":
    # Получаем порт из переменной окружения
    port = int(os.environ.get('PORT', 8000))
    
    # Проверяем, запущено ли в Railway
    if os.environ.get('RAILWAY_STATIC_URL'):
        # Режим Railway - настраиваем webhook
        railway_url = os.environ.get('RAILWAY_STATIC_URL')
        webhook_url = f"{railway_url}/"
        
        print(f"Устанавливаем webhook: {webhook_url}")
        bot.remove_webhook()
        bot.set_webhook(url=webhook_url)
        
        app.run(host='0.0.0.0', port=port)
    else:
        # Локальная разработка
        print("Локальный режим - запуск polling...")
        bot.polling(none_stop=True)