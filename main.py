import os
import sqlite3
import json
from datetime import datetime
import telebot
from flask import Flask, request
from PIL import Image
import numpy as np

# Токен бота
TOKEN = os.environ.get('BOT_TOKEN', '7530748232:AAF8T5Zsoa-LzqsP9T0gt5hEWYtxBhB3iLE')
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# Инициализация базы данных
def init_db():
    conn = sqlite3.connect('users.db', check_same_thread=False)
    c = conn.cursor()
    
    # Таблица пользователей
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (chat_id INTEGER PRIMARY KEY,
                  username TEXT,
                  password TEXT,
                  registered_at TEXT,
                  logged_in BOOLEAN DEFAULT FALSE,
                  predictions_count INTEGER DEFAULT 0,
                  is_admin BOOLEAN DEFAULT FALSE)''')
    
    # Таблица администраторов
    c.execute('''CREATE TABLE IF NOT EXISTS admins
                 (chat_id INTEGER PRIMARY KEY,
                  added_by INTEGER,
                  added_at TEXT)''')
    
    # Проверяем, есть ли администраторы
    c.execute("SELECT COUNT(*) FROM users WHERE is_admin = TRUE")
    if c.fetchone()[0] == 0:
        # Первый пользователь станет администратором
        print("Нет администраторов. Первый зарегистрированный пользователь станет админом.")
    
    conn.commit()
    conn.close()

init_db()

# Функции для работы с базой данных
def get_db_connection():
    conn = sqlite3.connect('users.db', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def add_user(chat_id, username, password):
    conn = get_db_connection()
    c = conn.cursor()
    
    # Проверяем, первый ли это пользователь
    c.execute("SELECT COUNT(*) FROM users")
    user_count = c.fetchone()[0]
    
    is_first_user = user_count == 0
    
    c.execute('''INSERT OR REPLACE INTO users 
                 (chat_id, username, password, registered_at, is_admin) 
                 VALUES (?, ?, ?, ?, ?)''',
              (chat_id, username, password, datetime.now().isoformat(), is_first_user))
    
    if is_first_user:
        c.execute('''INSERT OR REPLACE INTO admins (chat_id, added_by, added_at)
                     VALUES (?, ?, ?)''',
                  (chat_id, chat_id, datetime.now().isoformat()))
        print(f"Пользователь {chat_id} назначен первым администратором")
    
    conn.commit()
    conn.close()
    return is_first_user

def get_user(chat_id):
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE chat_id = ?', (chat_id,)).fetchone()
    conn.close()
    return user

def update_user_password(chat_id, password):
    conn = get_db_connection()
    conn.execute('UPDATE users SET password = ? WHERE chat_id = ?', (password, chat_id))
    conn.commit()
    conn.close()

def update_login_status(chat_id, status):
    conn = get_db_connection()
    conn.execute('UPDATE users SET logged_in = ? WHERE chat_id = ?', (status, chat_id))
    conn.commit()
    conn.close()

def increment_predictions(chat_id):
    conn = get_db_connection()
    conn.execute('UPDATE users SET predictions_count = predictions_count + 1 WHERE chat_id = ?', (chat_id,))
    conn.commit()
    conn.close()

def is_admin(chat_id):
    user = get_user(chat_id)
    return user and user['is_admin']

def get_all_users():
    conn = get_db_connection()
    users = conn.execute('SELECT * FROM users ORDER BY registered_at DESC').fetchall()
    conn.close()
    return users

def delete_user(chat_id):
    conn = get_db_connection()
    conn.execute('DELETE FROM users WHERE chat_id = ?', (chat_id,))
    conn.execute('DELETE FROM admins WHERE chat_id = ?', (chat_id,))
    conn.commit()
    conn.close()

def add_admin(chat_id, added_by):
    conn = get_db_connection()
    conn.execute('UPDATE users SET is_admin = TRUE WHERE chat_id = ?', (chat_id,))
    conn.execute('INSERT OR REPLACE INTO admins (chat_id, added_by, added_at) VALUES (?, ?, ?)',
                 (chat_id, added_by, datetime.now().isoformat()))
    conn.commit()
    conn.close()

# Функция анализа изображения
def analyze_image_colors(image_path):
    try:
        img = Image.open(image_path)
        if img.mode != 'RGB':
            img = img.convert('RGB')
        
        img_array = np.array(img)
        img_normalized = img_array / 255.0
        
        # Цветовые маски
        gray_mask = (
            (img_normalized[:,:,0] > 0.2) & (img_normalized[:,:,0] < 0.8) &
            (img_normalized[:,:,1] > 0.2) & (img_normalized[:,:,1] < 0.8) &
            (img_normalized[:,:,2] > 0.2) & (img_normalized[:,:,2] < 0.8) &
            (np.abs(img_normalized[:,:,0] - img_normalized[:,:,1]) < 0.2) &
            (np.abs(img_normalized[:,:,1] - img_normalized[:,:,2]) < 0.2)
        )
        
        brown_mask = (
            (img_normalized[:,:,0] > 0.4) & (img_normalized[:,:,0] < 0.8) &
            (img_normalized[:,:,1] > 0.3) & (img_normalized[:,:,1] < 0.6) &
            (img_normalized[:,:,2] > 0.2) & (img_normalized[:,:,2] < 0.4)
        )
        
        white_mask = (
            (img_normalized[:,:,0] > 0.7) &
            (img_normalized[:,:,1] > 0.7) &
            (img_normalized[:,:,2] > 0.7)
        )
        
        black_mask = (
            (img_normalized[:,:,0] < 0.3) &
            (img_normalized[:,:,1] < 0.3) &
            (img_normalized[:,:,2] < 0.3)
        )
        
        total_pixels = img_array.shape[0] * img_array.shape[1]
        gray_pixels = np.sum(gray_mask)
        brown_pixels = np.sum(brown_mask)
        white_pixels = np.sum(white_mask)
        black_pixels = np.sum(black_mask)
        
        gray_percent = (gray_pixels / total_pixels) * 100
        brown_percent = (brown_pixels / total_pixels) * 100
        white_percent = (white_pixels / total_pixels) * 100
        black_percent = (black_pixels / total_pixels) * 100
        
        wolf_score = gray_percent + black_percent + (white_percent * 0.5)
        human_score = brown_percent
        
        if wolf_score > human_score:
            confidence = wolf_score / (wolf_score + human_score) * 100
            result = f"🐺 Это волк! (уверенность: {confidence:.1f}%)"
        else:
            confidence = human_score / (wolf_score + human_score) * 100
            result = f"👤 Это человек! (уверенность: {confidence:.1f}%)"
        
        
        
        return result
        
    except Exception as e:
        return f"Ошибка при анализе изображения: {e}"

# Обработчики команд бота
@bot.message_handler(commands=['start'])
def send_welcome(message):
    user = get_user(message.chat.id)
    if user and user['is_admin']:
        welcome_text = (
            "Приветствуем тебя, Вожак стаи! 🐺👑\n"
            "Ты обладаешь силой управлять стаей.\n\n"
            "Команды для стаи:\n"
            "🐺 /register - Присоединиться к стае\n"
            "🐺 /login - Войти в стаю\n"
            "🐺 /predict - Анализ изображения\n"
            "🐺 /logout - Покинуть стаю\n\n"
            "Команды Вожака:\n"
            "👑 /admin - Панель управления\n"
            "👑 /users - Список волков\n"
            "👑 /stats - Статистика стаи\n\n"
            "Используй свою мудрость с умом!"
        )
    else:
        welcome_text = (
            "Приветствуем тебя в стае! 🐺\n"
            "Я анализирую изображения по цветам и определяю, человек это или волк!\n\n"
            "Вот что ты можешь сделать:\n"
            "🐺 /register - Присоединиться к стае\n"
            "🐺 /login - Войти в стаю\n"
            "🐺 /predict - Анализ изображения\n"
            "🐺 /logout - Покинуть стаю\n"
            "🐺 /instructions - Инструкции\n\n"
            "Начни с команды /register."
        )
    bot.reply_to(message, welcome_text)

@bot.message_handler(commands=['register'])
def register_user(message):
    chat_id = message.chat.id
    user = get_user(chat_id)
    
    if user:
        bot.reply_to(message, "Ты уже в стае! Используй /login")
        return
    
    bot.reply_to(message, "Придумай пароль для входа в стаю:")
    bot.register_next_step_handler(message, process_register_password)

def process_register_password(message):
    chat_id = message.chat.id
    password = message.text.strip()
    username = message.from_user.username or message.from_user.first_name
    
    if len(password) < 3:
        bot.reply_to(message, "Пароль слишком короткий. Минимум 3 символа.")
        return
    
    is_first_user = add_user(chat_id, username, password)
    
    if is_first_user:
        response = "Ты первый в стае и становишься Вожаком! Используй /admin для управления."
    else:
        response = "Поздравляем, ты теперь часть стаи! Запомни пароль. Используй /login"
    
    bot.reply_to(message, response)

@bot.message_handler(commands=['login'])
def login_user(message):
    chat_id = message.chat.id
    user = get_user(chat_id)
    
    if not user:
        bot.reply_to(message, "Ты еще не в стае. Используй /register")
        return
    
    if user['logged_in']:
        bot.reply_to(message, "Ты уже в стае, брат мой.")
        return
    
    bot.reply_to(message, "Введи пароль:")
    bot.register_next_step_handler(message, process_login_password)

def process_login_password(message):
    chat_id = message.chat.id
    password = message.text.strip()
    user = get_user(chat_id)
    
    if user and user['password'] == password:
        update_login_status(chat_id, True)
        bot.reply_to(message, "Поздравляем, ты в стае! Используй /predict для анализа изображений.")
    else:
        bot.reply_to(message, "Неверный пароль.")

@bot.message_handler(commands=['logout'])
def logout_user(message):
    chat_id = message.chat.id
    user = get_user(chat_id)
    
    if user and user['logged_in']:
        update_login_status(chat_id, False)
        bot.reply_to(message, "Спокойной ночи, волк. Возвращайся в стаю!")
    else:
        bot.reply_to(message, "Ты еще не в стае. Используй /register")

@bot.message_handler(commands=['predict'])
def predict(message):
    chat_id = message.chat.id
    user = get_user(chat_id)
    
    if not user:
        bot.reply_to(message, "Сначала присоединись к стае через /register")
        return
    
    if not user['logged_in']:
        bot.reply_to(message, "Сначала войди в стаю через /login")
        return
    
    bot.reply_to(message, "Отправь изображение для анализа 🐺")

# АДМИН-ПАНЕЛЬ
@bot.message_handler(commands=['admin'])
def admin_panel(message):
    chat_id = message.chat.id
    
    if not is_admin(chat_id):
        bot.reply_to(message, "Только Вожак стаи может использовать эту команду.")
        return
    
    admin_text = (
        "👑 Панель Вожака стаи:\n\n"
        "Статистика:\n"
        "• /stats - Общая статистика\n\n"
        "🐺 Управление волками:\n"
        "• /users - Список всей стаи\n"
        "• /add_admin - Добавить Вожака\n"
        "• /delete_user - Изгнать из стаи\n\n"
        "Используй команды с мудростью!"
    )
    bot.reply_to(message, admin_text)

@bot.message_handler(commands=['stats'])
def show_stats(message):
    chat_id = message.chat.id
    
    if not is_admin(chat_id):
        bot.reply_to(message, "Доступ только для Вожака.")
        return
    
    users = get_all_users()
    total_users = len(users)
    total_predictions = sum(user['predictions_count'] for user in users)
    active_users = sum(1 for user in users if user['logged_in'])
    admins_count = sum(1 for user in users if user['is_admin'])
    
    stats_text = (
        f"Статистика стаи:\n\n"
        f"Всего волков: {total_users}\n"
        f"В стае сейчас: {active_users}\n"
        f"Вожаков: {admins_count}\n"
        f"Анализов проведено: {total_predictions}\n\n"
        f"Используй /users для подробного списка"
    )
    bot.reply_to(message, stats_text)

@bot.message_handler(commands=['users'])
def show_users(message):
    chat_id = message.chat.id
    
    if not is_admin(chat_id):
        bot.reply_to(message, "Только Вожак может видеть стаю.")
        return
    
    users = get_all_users()
    
    if not users:
        bot.reply_to(message, "Стая пока пуста.")
        return
    
    users_text = "🐺 Вся стая:\n\n"
    for i, user in enumerate(users, 1):
        status = "В стае" if user['logged_in'] else "Не в стае"
        admin_flag = "" if user['is_admin'] else ""
        users_text += (
            f"{i}. {user['username'] or 'Без имени'}{admin_flag}\n"
            f"   ID: {user['chat_id']}\n"
            f"   Статус: {status}\n"
            f"   Анализов: {user['predictions_count']}\n"
            f"   В стае с: {user['registered_at'][:10]}\n\n"
        )
    
    users_text += "Для удаления используй /delete_user [ID]"
    bot.reply_to(message, users_text)

@bot.message_handler(commands=['delete_user'])
def delete_user_cmd(message):
    chat_id = message.chat.id
    
    if not is_admin(chat_id):
        bot.reply_to(message, "Только Вожак может изгонять из стаи.")
        return
    
    # Проверяем, передан ли ID пользователя
    command_parts = message.text.split()
    if len(command_parts) == 2:
        try:
            user_id_to_delete = int(command_parts[1])
            user_to_delete = get_user(user_id_to_delete)
            
            if not user_to_delete:
                bot.reply_to(message, "Волк с таким ID не найден.")
                return
            
            if user_to_delete['is_admin']:
                bot.reply_to(message, "Нельзя изгнать Вожака стаи.")
                return
            
            delete_user(user_id_to_delete)
            bot.reply_to(message, f"Волк {user_to_delete['username']} изгнан из стаи.")
            
        except ValueError:
            bot.reply_to(message, "Неверный формат ID. Используй: /delete_user [ID]")
    else:
        bot.reply_to(message, "Для изгнания укажи ID волка:\n/delete_user [ID]\n\nID можно посмотреть в /users")

@bot.message_handler(commands=['add_admin'])
def add_admin_cmd(message):
    chat_id = message.chat.id
    
    if not is_admin(chat_id):
        bot.reply_to(message, "Только Вожак может назначать новых Вожаков.")
        return
    
    bot.reply_to(message, "Введи ID волка, которого хочешь сделать Вожаком:\n(ID можно посмотреть в /users)")
    bot.register_next_step_handler(message, process_add_admin)

def process_add_admin(message):
    chat_id = message.chat.id
    
    try:
        new_admin_id = int(message.text.strip())
        new_admin_user = get_user(new_admin_id)
        
        if not new_admin_user:
            bot.reply_to(message, "Волк с таким ID не найден.")
            return
        
        if new_admin_user['is_admin']:
            bot.reply_to(message, "Этот волк уже Вожак.")
            return
        
        add_admin(new_admin_id, chat_id)
        bot.reply_to(message, f"{new_admin_user['username']} теперь Вожак стаи 👑")
        
    except ValueError:
        bot.reply_to(message, "Неверный формат ID.")

@bot.message_handler(content_types=['photo'])
def process_image_prediction(message):
    chat_id = message.chat.id
    user = get_user(chat_id)
    
    if not user or not user['logged_in']:
        bot.reply_to(message, "Сначала войди в стаю через /login")
        return
    
    try:
        #bot.reply_to(message, "🔍 Анализирую цвета...")
        
        file_info = bot.get_file(message.photo[-1].file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        temp_file_path = "temp_image.jpg"
        with open(temp_file_path, 'wb') as new_file:
            new_file.write(downloaded_file)
        
        result = analyze_image_colors(temp_file_path)
        increment_predictions(chat_id)
        
        bot.reply_to(message, result)
        os.remove(temp_file_path)
        
    except Exception as e:
        bot.reply_to(message, f"Ошибка при обработке изображения: {e}")

@bot.message_handler(func=lambda message: True)
def handle_unknown(message):
    if message.text.startswith('/'):
        bot.reply_to(message, "Неизвестная команда. Используй /start для списка команд.")
    else:
        bot.reply_to(message, "Просто отправь мне фото для анализа или используй /start")

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
    return 'Бот-анализатор цветов с админ-панелью работает! 🐺👑', 200

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 8000))
    
    if os.environ.get('RAILWAY_STATIC_URL'):
        railway_url = os.environ.get('RAILWAY_STATIC_URL')
        webhook_url = f"{railway_url}/"
        
        print("Устанавливаем webhook...")
        bot.remove_webhook()
        bot.set_webhook(url=webhook_url)
        print(f"Webhook установлен: {webhook_url}")
        
        app.run(host='0.0.0.0', port=port)
    else:
        print("Локальный режим - запуск polling...")
        bot.polling(none_stop=True)