import os
import psycopg2
from datetime import datetime
import telebot
from flask import Flask, request
from PIL import Image
import numpy as np
import urllib.parse as urlparse

# Токен бота
TOKEN = os.environ.get('BOT_TOKEN', '7530748232:AAF8T5Zsoa-LzqsP9T0gt5hEWYtxBhB3iLE')
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# Подключение к PostgreSQL
def get_db_connection():
    database_url = os.environ.get('DATABASE_URL')
    
    if not database_url:
        raise Exception("DATABASE_URL not found in environment variables")
    
    # Парсим URL для Railway PostgreSQL
    url = urlparse.urlparse(database_url)
    
    conn = psycopg2.connect(
        dbname=url.path[1:],  # убираем первый слэш
        user=url.username,
        password=url.password,
        host=url.hostname,
        port=url.port,
        sslmode='require'
    )
    
    return conn

# Инициализация базы данных
def init_db():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Таблица пользователей
        cur.execute('''
            CREATE TABLE IF NOT EXISTS users (
                chat_id BIGINT PRIMARY KEY,
                username TEXT,
                password TEXT,
                registered_at TIMESTAMP,
                logged_in BOOLEAN DEFAULT FALSE,
                predictions_count INTEGER DEFAULT 0,
                is_admin BOOLEAN DEFAULT FALSE
            )
        ''')
        
        conn.commit()
        cur.close()
        conn.close()
        print("База данных инициализирована")
    except Exception as e:
        print(f"Ошибка инициализации БД: {e}")

# Инициализируем БД при запуске
init_db()

# Функции для работы с базой данных
def add_user(chat_id, username, password):
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("SELECT COUNT(*) FROM users")
    user_count = cur.fetchone()[0]
    is_first_user = user_count == 0
    
    cur.execute('''
        INSERT INTO users (chat_id, username, password, registered_at, is_admin) 
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (chat_id) DO UPDATE SET
        username = EXCLUDED.username,
        password = EXCLUDED.password
    ''', (chat_id, username, password, datetime.now(), is_first_user))
    
    conn.commit()
    cur.close()
    conn.close()
    return is_first_user

def get_user(chat_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT * FROM users WHERE chat_id = %s', (chat_id,))
    user = cur.fetchone()
    cur.close()
    conn.close()
    return user

def update_login_status(chat_id, status):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('UPDATE users SET logged_in = %s WHERE chat_id = %s', (status, chat_id))
    conn.commit()
    cur.close()
    conn.close()

def increment_predictions(chat_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('UPDATE users SET predictions_count = predictions_count + 1 WHERE chat_id = %s', (chat_id,))
    conn.commit()
    cur.close()
    conn.close()

def is_admin(chat_id):
    user = get_user(chat_id)
    return user and user[6]  # is_admin is 7th column

def get_all_users():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT * FROM users ORDER BY registered_at DESC')
    users = cur.fetchall()
    cur.close()
    conn.close()
    return users

def delete_user(chat_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('DELETE FROM users WHERE chat_id = %s', (chat_id,))
    conn.commit()
    cur.close()
    conn.close()

def add_admin(chat_id, added_by):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('UPDATE users SET is_admin = TRUE WHERE chat_id = %s', (chat_id,))
    conn.commit()
    cur.close()
    conn.close()

def analyze_image_colors(image_path):
    try:
        img = Image.open(image_path)
        if img.mode != 'RGB':
            img = img.convert('RGB')
        
        img_array = np.array(img)
        height, width = img_array.shape[:2]
        img_normalized = img_array / 255.0
        
        
        zones = [
            
            (height//3, height*2//3, width//3, width*2//3, 3.0),
              
            (height//4, height*3//4, width//4, width*3//4, 1.5),
            
            (0, height, 0, width, 1.0)
        ]
        
        total_wolf_score = 0
        total_weight = 0
        
        for h_start, h_end, w_start, w_end, weight in zones:
            zone = img_normalized[h_start:h_end, w_start:w_end]
            if zone.size == 0:
                continue
                
            
            wolf_colors = (
                
                ((zone[:,:,0] > 0.4) & (zone[:,:,0] < 0.6) &
                 (zone[:,:,1] > 0.4) & (zone[:,:,1] < 0.6) &
                 (zone[:,:,2] > 0.4) & (zone[:,:,2] < 0.6) &
                 (np.abs(zone[:,:,0] - zone[:,:,1]) < 0.08) &
                 (np.abs(zone[:,:,1] - zone[:,:,2]) < 0.08)) |
                
                
                ((zone[:,:,0] > 0.25) & (zone[:,:,0] < 0.45) &
                 (zone[:,:,1] > 0.25) & (zone[:,:,1] < 0.45) &
                 (zone[:,:,2] > 0.25) & (zone[:,:,2] < 0.45) &
                 (np.abs(zone[:,:,0] - zone[:,:,1]) < 0.1))
            )
            
            wolf_pixels = np.sum(wolf_colors)
            zone_pixels = zone.shape[0] * zone.shape[1]
            wolf_score = (wolf_pixels / zone_pixels) * weight
            
            total_wolf_score += wolf_score
            total_weight += weight
        
        if total_weight == 0:
            return "🤔 Не могу проанализировать"
        
        wolf_percentage = (total_wolf_score / total_weight) * 100
        
        
        if wolf_percentage > 35:
            return f"🐺 Это волк! (уверенность: {wolf_percentage:.1f}%)"
        elif wolf_percentage > 20:
            return f"🐺 Возможно волк (уверенность: {wolf_percentage:.1f}%)"
        else:
            human_confidence = 100 - wolf_percentage
            return f"Это человек! (уверенность: {human_confidence:.1f}%)"
        
    except Exception as e:
        return f"Ошибка при обработке изображения: {e}"
# Обработчики команд бота
@bot.message_handler(commands=['start'])
def send_welcome(message):
    user = get_user(message.chat.id)
    if user and user[6]:
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

@bot.message_handler(func=lambda message: 'спасибо' in message.text.lower())
def thank_you_response(message):
    bot.reply_to(message, "Стая с тобой навсегда! 🐺")

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

@bot.message_handler(commands=['instructions'])
def send_instructions(message):
    instructions_text = (
        "Что же, ищущий да обрящет!\n\n"
        
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
    user = get_user(chat_id)
    
    if not user:
        bot.reply_to(message, "Ты еще не в стае. Используй /register")
        return
    
    if user[4]:  # logged_in
        bot.reply_to(message, "Ты уже в стае, брат мой.")
        return
    
    bot.reply_to(message, "Введи пароль:")
    bot.register_next_step_handler(message, process_login_password)

def process_login_password(message):
    chat_id = message.chat.id
    password = message.text.strip()
    user = get_user(chat_id)
    
    if user and user[2] == password:  # password field
        update_login_status(chat_id, True)
        bot.reply_to(message, "Поздравляем, ты в стае! Используй /predict для анализа изображений.")
    else:
        bot.reply_to(message, "Неверный пароль.")

@bot.message_handler(commands=['logout'])
def logout_user(message):
    chat_id = message.chat.id
    user = get_user(chat_id)
    
    if user and user[4]:  # logged_in
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
    
    if not user[4]:  # logged_in
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
    total_predictions = sum(user[5] for user in users)  # predictions_count
    active_users = sum(1 for user in users if user[4])  # logged_in
    admins_count = sum(1 for user in users if user[6])  # is_admin
    
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
        status = "В стае" if user[4] else "Не в стае"  # logged_in
        admin_flag = " 👑" if user[6] else ""  # is_admin
        registered_date = user[3].strftime('%Y-%m-%d') if user[3] else 'N/A'
        users_text += (
            f"{i}. {user[1] or 'Без имени'}{admin_flag}\n"
            f"   ID: {user[0]}\n"
            f"   Статус: {status}\n"
            f"   Анализов: {user[5]}\n"
            f"   В стае с: {registered_date}\n\n"
        )
    
    users_text += "Для удаления используй /delete_user [ID]"
    bot.reply_to(message, users_text)

@bot.message_handler(commands=['delete_user'])
def delete_user_cmd(message):
    chat_id = message.chat.id
    
    if not is_admin(chat_id):
        bot.reply_to(message, "Только Вожак может изгонять из стаи.")
        return
    
    command_parts = message.text.split()
    if len(command_parts) == 2:
        try:
            user_id_to_delete = int(command_parts[1])
            user_to_delete = get_user(user_id_to_delete)
            
            if not user_to_delete:
                bot.reply_to(message, "Волк с таким ID не найден.")
                return
            
            if user_to_delete[6]:  # is_admin
                bot.reply_to(message, "Нельзя изгнать Вожака стаи.")
                return
            
            delete_user(user_id_to_delete)
            bot.reply_to(message, f"Волк {user_to_delete[1]} изгнан из стаи.")
            
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
        
        if new_admin_user[6]:  # is_admin
            bot.reply_to(message, "Этот волк уже Вожак.")
            return
        
        add_admin(new_admin_id, chat_id)
        bot.reply_to(message, f"{new_admin_user[1]} теперь Вожак стаи! 👑")
        
    except ValueError:
        bot.reply_to(message, "Неверный формат ID.")

@bot.message_handler(content_types=['photo'])
def process_image_prediction(message):
    chat_id = message.chat.id
    user = get_user(chat_id)
    
    if not user or not user[4]:  # logged_in
        bot.reply_to(message, "Сначала войди в стаю через /login")
        return
    
    try:
        
        
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
    return 'Бот-анализатор цветов с PostgreSQL работает! 🐺👑', 200

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