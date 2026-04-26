import telebot
from telebot import types
import json
import os
import time
import logging
import datetime

# =================================================================
# 1. ОСНОВНАЯ КОНФИГУРАЦИЯ И НАСТРОЙКИ
# =================================================================

# ТВОЙ ТОКЕН ОТ @BotFather
TOKEN = "ТВОЙ_ТОКЕН_ТУТ" 

# ID КАНАЛА ДЛЯ ПУБЛИКАЦИЙ
CHANNEL_ID = '-1003740141875' 

# ГЛАВНЫЙ АДМИНИСТРАТОР (Твой ник без @)
SUPER_ADMIN = "Nazikrrk" 

# ИНИЦИАЛИЗАЦИЯ БОТА
bot = telebot.TeleBot(TOKEN)
DATA_FILE = "tm_mega_system_v7.json"

# Настройка логирования для отслеживания ошибок
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# =================================================================
# 2. ДЕТАЛЬНЫЙ СПИСОК КЛУБОВ И ИХ НАЧАЛЬНЫХ ВЛАДЕЛЬЦЕВ
# =================================================================

INITIAL_CLUBS_DATA = {
    "Inter Milan 🇮🇹": "sipskdo",
    "Barcelona 🇪🇸": "banditdontrealme",
    "Napoli 🇮🇹": "estavaojr",
    "Sporting 🇵🇹": "nikitos_201064",
    "Arsenal 🏴󠁧󠁢󠁥󠁮󠁧󠁿": "ilikembb",
    "Sochi 🇷🇺": "amolikergob",
    "Nottingham Forest 🏴󠁧󠁢󠁥󠁮󠁧󠁿": "levvvo_1",
    "Juventus 🇮🇹": "topor_12",
    "Kalev 🇪🇪": "miha10021",
    "Real Madrid 🇪🇸": None,
    "Bayern Munich 🇩🇪": None,
    "Manchester City 🏴󠁧󠁢󠁥󠁮󠁧󠁿": None,
    "Manchester United 🏴󠁧󠁢󠁥󠁮󠁧󠁿": None,
    "Borussia Dortmund 🇩🇪": None,
    "Roma 🇮🇹": None
}

# =================================================================
# 3. УПРАВЛЕНИЕ БАЗОЙ ДАННЫХ (JSON)
# =================================================================

def load_database():
    """Загружает базу данных или создает новую с полным набором полей"""
    if not os.path.exists(DATA_FILE):
        new_db = {
            "users": {},
            "admins": [SUPER_ADMIN.lower()],
            "clubs": {},
            "config": {
                "top_clubs_text": "🏆 **ТОП КЛУБОВ ТМ**\n\n1. Место свободно\n2. Место свободно",
                "clubs_list_text": ""
            }
        }
        
        # Заполнение клубов из начальных данных
        for club_name, owner_tag in INITIAL_CLUBS_DATA.items():
            new_db["clubs"][club_name] = {
                "owner": owner_tag.lower() if owner_tag else None,
                "deputy": None,
                "history": []
            }
        
        # Формирование начального текста списка
        clubs_list_msg = "🏆 **СПИСОК ОФИЦИАЛЬНЫХ КЛУБОВ**\n\n"
        for name, owner in INITIAL_CLUBS_DATA.items():
            owner_display = f"@{owner}" if owner else "❓ Свободно"
            clubs_list_msg += f"{name} — {owner_display}\n"
        
        new_db["config"]["clubs_list_text"] = clubs_list_msg
        
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(new_db, f, ensure_ascii=False, indent=4)
        return new_db
    
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Критическая ошибка при чтении базы: {e}")
        return None

def save_database(data):
    """Сохраняет состояние базы в файл"""
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logging.error(f"Ошибка сохранения базы: {e}")

# =================================================================
# 4. ВСПОМОГАТЕЛЬНЫЕ ПРОВЕРКИ И ИНСТРУМЕНТЫ
# =================================================================

def is_user_admin(username):
    """Проверяет, является ли пользователь администратором бота"""
    db = load_database()
    return (username or "").lower() in db["admins"]

def get_user_managed_club(username):
    """Находит клуб, которым управляет юзер (как владелец или зам)"""
    db = load_database()
    uname = (username or "").lower()
    for club_name, data in db["clubs"].items():
        if data["owner"] == uname or data["deputy"] == uname:
            return club_name
    return None

def get_user_id_by_tag(tag):
    """Находит Telegram ID по юзернейму в базе данных"""
    clean_tag = tag.replace("@", "").lower().strip()
    db = load_database()
    for uid, info in db["users"].items():
        if info.get("username") == clean_tag:
            return uid
    return None

# =================================================================
# 5. СИСТЕМА КУЛДАУНОВ (ОГРАНИЧЕНИЙ)
# =================================================================

def check_cooldown_period(user_id, username, action_type, seconds_limit):
    """
    Проверяет КД. 
    ВАЖНО: Для SUPER_ADMIN и Админов всегда возвращает False (нет ограничений).
    """
    db = load_database()
    uname_low = (username or "").lower()
    
    # Снятие ограничений для тебя и админов
    if uname_low in db["admins"]:
        return False, 0
    
    uid_str = str(user_id)
    if uid_str not in db["users"]:
        return False, 0
    
    last_action_time = db["users"][uid_str].get("timers", {}).get(action_type, 0)
    current_time = time.time()
    
    if (current_time - last_action_time) < seconds_limit:
        remaining = int(seconds_limit - (current_time - last_action_time))
        return True, remaining
    return False, 0

def update_action_timer(user_id, action_type):
    """Записывает время последнего совершенного действия"""
    db = load_database()
    uid_str = str(user_id)
    if "timers" not in db["users"][uid_str]:
        db["users"][uid_str]["timers"] = {}
    db["users"][uid_str]["timers"][action_type] = time.time()
    save_database(db)

# =================================================================
# 6. КЛАВИАТУРЫ И ИНТЕРФЕЙС
# =================================================================

def main_menu_markup(user_id, username):
    """Генерация основного меню в зависимости от прав доступа"""
    db = load_database()
    uid_str = str(user_id)
    u_info = db["users"].get(uid_str, {})
    uname_low = (username or "").lower()
    
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    
    # Кнопка для администрации
    if is_user_admin(uname_low):
        markup.add(types.KeyboardButton("👑 Админ Панель"))

    # Меню для тех, кто на пенсии
    if u_info.get("is_retired", False):
        markup.add(types.KeyboardButton("Возвращение карьеры 🔙"))
        markup.add(types.KeyboardButton("Написать админам 📩"))
        markup.add(types.KeyboardButton("Список клубов 📋"), types.KeyboardButton("Топ клубов 🏆"))
        markup.add(types.KeyboardButton("Профиль 👤"))
        return markup

    # Основные функции игрока
    markup.add(types.KeyboardButton("Свободный агент 🆓"), types.KeyboardButton("Свой текст 📝"))
    
    # Кнопки для Владельцев и Заместителей
    managed_club = get_user_managed_club(uname_low)
    if managed_club or is_user_admin(uname_low):
        markup.add(types.KeyboardButton("Предложить трансфер 🤝"))
    
    # Специальные кнопки только для Главных Владельцев (управление замами)
    is_main_owner = False
    for club_name, staff in db["clubs"].items():
        if staff["owner"] == uname_low:
            is_main_owner = True
            break
            
    if is_main_owner:
        markup.add(types.KeyboardButton("Добавить зама 👤+"), types.KeyboardButton("Удалить зама 👤-"))

    # Нижний ряд кнопок
    markup.add(types.KeyboardButton("Список клубов 📋"), types.KeyboardButton("Топ клубов 🏆"))
    markup.add(types.KeyboardButton("Профиль 👤"), types.KeyboardButton("Изменить ник ✏️"))
    markup.add(types.KeyboardButton("Написать админам 📩"), types.KeyboardButton("Завершение карьера 🚫"))
    
    return markup

def admin_panel_markup(username):
    """Меню администратора"""
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("🚫 Забанить", "✅ Разбанить")
    markup.add("🔑 Дать влд", "🗑 Снять влд")
    
    # Только Супер Админ может управлять админ-составом
    if username.lower() == SUPER_ADMIN.lower():
        markup.add("⭐ Дать админку", "❌ Снять админку")
        
    markup.add("📝 Изменить список", "🔥 Изменить ТОП")
    markup.add("🔙 Назад в меню")
    return markup

def cancel_markup():
    """Кнопка отмены для всех пошаговых действий"""
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("Отмена 🔙"))
    return markup

# =================================================================
# 7. ПОШАГОВЫЕ ОБРАБОТЧИКИ (SCRIPTS)
# =================================================================

# --- Регистрация ника ---
def process_step_nickname_reg(message):
    if message.text == "Отмена 🔙":
        bot.send_message(message.chat.id, "❌ Регистрация отменена. Используйте /start.", reply_markup=types.ReplyKeyboardRemove())
        return
    if not message.text or len(message.text) < 2:
        msg = bot.send_message(message.chat.id, "⚠️ Ник слишком короткий. Введите еще раз:")
        bot.register_next_step_handler(msg, process_step_nickname_reg)
        return
        
    db = load_database()
    db["users"][str(message.from_user.id)]["rb_nick"] = message.text.strip()
    save_database(db)
    bot.send_message(message.chat.id, f"✅ Ник {message.text} успешно привязан!", reply_markup=main_menu_markup(message.from_user.id, message.from_user.username))

# --- Предложение трансфера ---
def process_step_transfer_offer(message, sender_club):
    if message.text == "Отмена 🔙":
        bot.send_message(message.chat.id, "🏠 Возврат в меню.", reply_markup=main_menu_markup(message.from_user.id, message.from_user.username))
        return
    
    target_uid = get_user_id_by_tag(message.text)
    if not target_uid:
        bot.send_message(message.chat.id, "❌ Ошибка: Игрок с таким юзернеймом не найден в базе бота.")
        return

    # Создание инлайн кнопок для игрока
    inline_kb = types.InlineKeyboardMarkup()
    inline_kb.add(
        types.InlineKeyboardButton("✅ Принять", callback_data=f"accept_{message.from_user.id}"),
        types.InlineKeyboardButton("❌ Отклонить", callback_data=f"decline_{message.from_user.id}")
    )
    
    try:
        bot.send_message(target_uid, f"⚽️ **ВАМ ПРЕДЛОЖИЛИ КОНТРАКТ!**\n🏢 Клуб: {sender_club}\n👤 Отправитель: @{message.from_user.username}", reply_markup=inline_kb, parse_mode="Markdown")
        bot.send_message(message.chat.id, f"✅ Предложение успешно отправлено игроку {message.text}!", reply_markup=main_menu_markup(message.from_user.id, message.from_user.username))
    except Exception as e:
        bot.send_message(message.chat.id, "❌ Не удалось отправить сообщение (возможно, бот заблокирован).")

# --- Добавление заместителя ---
def process_step_add_zam(message, club_name):
    if message.text == "Отмена 🔙":
        bot.send_message(message.chat.id, "🏠 Отменено.", reply_markup=main_menu_markup(message.from_user.id, message.from_user.username))
        return
    
    target_tag = message.text.replace("@", "").lower().strip()
    db = load_database()
    db["clubs"][club_name]["deputy"] = target_tag
    save_database(db)
    
    bot.send_message(message.chat.id, f"✅ Игрок @{target_tag} теперь является вашим заместителем в {club_name}!", reply_markup=main_menu_markup(message.from_user.id, message.from_user.username))

# --- Изменение списка клубов (Админ) ---
def process_step_edit_clubs_list(message):
    if message.text == "Отмена 🔙":
        bot.send_message(message.chat.id, "🏠 Отменено.", reply_markup=admin_panel_markup(message.from_user.username))
        return
    db = load_database()
    db["config"]["clubs_list_text"] = message.text
    save_database(db)
    bot.send_message(message.chat.id, "✅ Список клубов успешно обновлен!", reply_markup=admin_panel_markup(message.from_user.username))

# --- Изменение ТОПа (Админ) ---
def process_step_edit_top(message):
    if message.text == "Отмена 🔙":
        bot.send_message(message.chat.id, "🏠 Отменено.", reply_markup=admin_panel_markup(message.from_user.username))
        return
    db = load_database()
    db["config"]["top_clubs_text"] = message.text
    save_database(db)
    bot.send_message(message.chat.id, "✅ ТОП успешно обновлен!", reply_markup=admin_panel_markup(message.from_user.username))

# --- Назначение владельца (Админ) ---
def process_step_give_owner(message):
    if message.text == "Отмена 🔙":
        bot.send_message(message.chat.id, "🏠 Отменено.", reply_markup=admin_panel_markup(message.from_user.username))
        return
    
    if "|" not in message.text:
        bot.send_message(message.chat.id, "❌ Неверный формат! Используйте: Клуб | @юзер")
        return
        
    try:
        parts = message.text.split("|")
        club_name = parts[0].strip()
        user_tag = parts[1].replace("@", "").lower().strip()
        
        db = load_database()
        if club_name in db["clubs"]:
            db["clubs"][club_name]["owner"] = user_tag
            save_database(db)
            bot.send_message(message.chat.id, f"✅ Клуб {club_name} теперь принадлежит @{user_tag}")
        else:
            bot.send_message(message.chat.id, "❌ Ошибка: Клуб с таким названием не найден. Проверьте флаг и пробелы.")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {e}")

# --- Снятие владельца (Админ) ---
def process_step_remove_owner(message):
    if message.text == "Отмена 🔙":
        bot.send_message(message.chat.id, "🏠 Отменено.", reply_markup=admin_panel_markup(message.from_user.username))
        return
    
    club_name = message.text.strip()
    db = load_database()
    if club_name in db["clubs"]:
        db["clubs"][club_name]["owner"] = None
        db["clubs"][club_name]["deputy"] = None
        save_database(db)
        bot.send_message(message.chat.id, f"✅ Клуб {club_name} теперь свободен!")
    else:
        bot.send_message(message.chat.id, "❌ Клуб не найден в базе.")

# =================================================================
# 8. ОСНОВНЫЕ ОБРАБОТЧИКИ СООБЩЕНИЙ
# =================================================================

@bot.message_handler(commands=['start'])
def command_start(message):
    """Начало работы с ботом, инициализация профиля"""
    bot.clear_step_handler_by_chat_id(message.chat.id)
    db = load_database()
    uid = str(message.from_user.id)
    un = (message.from_user.username or "none").lower()
    
    # Регистрация нового пользователя в системе
    if uid not in db["users"]:
        db["users"][uid] = {
            "username": un,
            "rb_nick": None,
            "is_retired": False,
            "is_banned": False,
            "timers": {}
        }
    else:
        db["users"][uid]["username"] = un
    
    save_database(db)

    # Проверка на наличие бана
    if db["users"][uid].get("is_banned") and un != SUPER_ADMIN.lower():
        bot.send_message(message.chat.id, "🚫 Вы заблокированы администрацией бота.")
        return

    # Проверка наличия ника Roblox
    if not db["users"][uid].get("rb_nick"):
        msg = bot.send_message(message.chat.id, "👋 Привет! Чтобы пользоваться ботом, тебе нужно зарегистрироваться.\n\nВведите ваш **Ник в Roblox**:", parse_mode="Markdown", reply_markup=cancel_markup())
        bot.register_next_step_handler(msg, process_step_nickname_reg)
    else:
        bot.send_message(message.chat.id, "🔘 Вы находитесь в главном меню:", reply_markup=main_menu_markup(message.from_user.id, un))

@bot.message_handler(content_types=['text'])
def global_text_handler(message):
    """Главный диспетчер текстовых кнопок"""
    uid = str(message.from_user.id)
    un = (message.from_user.username or "").lower()
    db = load_database()
    
    if uid not in db["users"]: return
    u_info = db["users"][uid]
    
    # Блокировка команд для забаненных
    if u_info.get("is_banned") and un != SUPER_ADMIN.lower(): return

    # --- СЕКЦИЯ АДМИНИСТРАТОРА ---
    if message.text == "👑 Админ Панель" and is_user_admin(un):
        bot.send_message(message.chat.id, "🛠 Добро пожаловать в панель управления:", reply_markup=admin_panel_markup(un))
        return

    if message.text == "🔙 Назад в меню":
        bot.send_message(message.chat.id, "🏠 Возвращаю в основное меню:", reply_markup=main_menu_markup(message.from_user.id, un))
        return

    if is_user_admin(un):
        if message.text == "🔑 Дать влд":
            msg = bot.send_message(message.chat.id, "Введите данные в формате:\n`Название Клуба | @юзер`", parse_mode="Markdown", reply_markup=cancel_markup())
            bot.register_next_step_handler(msg, process_step_give_owner)
            return
        elif message.text == "🗑 Снять влд":
            msg = bot.send_message(message.chat.id, "Введите точное название клуба (с флагом):", reply_markup=cancel_markup())
            bot.register_next_step_handler(msg, process_step_remove_owner)
            return
        elif message.text == "📝 Изменить список":
            msg = bot.send_message(message.chat.id, "Введите новый текст для списка клубов:", reply_markup=cancel_markup())
            bot.register_next_step_handler(msg, process_step_edit_clubs_list)
            return
        elif message.text == "🔥 Изменить ТОП":
            msg = bot.send_message(message.chat.id, "Введите новый текст для ТОПа:", reply_markup=cancel_markup())
            bot.register_next_step_handler(msg, process_step_edit_top)
            return
        elif message.text == "🚫 Забанить":
            # (Логика бана по аналогии)
            pass

    # --- СЕКЦИЯ ВЛАДЕЛЬЦА КЛУБА И ЗАМА ---
    if message.text == "Предложить трансфер 🤝":
        my_club = get_user_managed_club(un) or (is_user_admin(un) and "Администрация")
        if my_club:
            msg = bot.send_message(message.chat.id, "🎯 Введите @username игрока, которому хотите сделать предложение:", reply_markup=cancel_markup())
            bot.register_next_step_handler(msg, process_step_transfer_offer, my_club)
        return

    elif message.text == "Добавить зама 👤+":
        my_real_club = None
        for c_name, staff in db["clubs"].items():
            if staff["owner"] == un:
                my_real_club = c_name
                break
        if my_real_club:
            msg = bot.send_message(message.chat.id, f"👤 Введите @username игрока, которого хотите назначить замом в {my_real_club}:", reply_markup=cancel_markup())
            bot.register_next_step_handler(msg, process_step_add_zam, my_real_club)
        return

    elif message.text == "Удалить зама 👤-":
        my_real_club = None
        for c_name, staff in db["clubs"].items():
            if staff["owner"] == un:
                my_real_club = c_name
                break
        if my_real_club:
            db["clubs"][my_real_club]["deputy"] = None
            save_database(db)
            bot.send_message(message.chat.id, f"✅ Заместитель в клубе {my_real_club} был удален.")
        return

    # --- СЕКЦИЯ ОБЫЧНОГО ИГРОКА ---
    if message.text == "Свободный агент 🆓":
        # Проверка КД 12 часов (43200 секунд). Для админов КД = 0.
        on_cd, wait = check_cooldown_period(message.from_user.id, un, "free_agent", 43200)
        if on_cd:
            bot.send_message(message.chat.id, f"⚠️ Вы уже подавали заявку! Ждите еще {wait // 3600} ч. { (wait % 3600) // 60 } мин.")
            return
        
        nick = u_info.get("rb_nick", "Игрок")
        contact = f"@{un}" if un else "Юзернейм скрыт"
        
        status_msg = f"🆓 **СВОБОДНЫЙ АГЕНТ**\n\n🎮 Игрок: `{nick}`\n🔗 Контакт: {contact}\n⚽️ Текущий статус: В поиске новой команды!"
        
        try:
            bot.send_message(CHANNEL_ID, status_msg, parse_mode="Markdown")
            update_action_timer(message.from_user.id, "free_agent")
            bot.send_message(message.chat.id, "✅ Ваш статус «Свободный агент» опубликован в канале!")
        except Exception:
            bot.send_message(message.chat.id, "❌ Ошибка публикации. Проверьте права бота в канале.")

    elif message.text == "Свой текст 📝":
        on_cd, wait = check_cooldown_period(message.from_user.id, un, "custom_text", 43200)
        if on_cd:
            bot.send_message(message.chat.id, f"⚠️ Лимит сообщений! Ждите еще {wait // 3600} ч.")
            return
        
        msg = bot.send_message(message.chat.id, "💬 Введите текст сообщения для канала (Без КД для администрации):", reply_markup=cancel_markup())
        bot.register_next_step_handler(msg, lambda m: (
            bot.send_message(CHANNEL_ID, f"📝 **СООБЩЕНИЕ**\n👤 От: @{un}\n💬 {m.text}") if m.text != "Отмена 🔙" else None,
            update_action_timer(message.from_user.id, "custom_text") if m.text != "Отмена 🔙" else None,
            bot.send_message(message.chat.id, "✅ Отправлено!", reply_markup=main_menu_markup(message.from_user.id, un)) if m.text != "Отмена 🔙" else None
        ))

    elif message.text == "Профиль 👤":
        my_club = get_user_managed_club(un) or "Нет"
        st = "На пенсии ❌" if u_info.get("is_retired") else "Активен ✅"
        profile_text = (
            f"👤 **ВАШ ИГРОВОЙ ПРОФИЛЬ**\n\n"
            f"🎮 Roblox Ник: `{u_info.get('rb_nick')}`\n"
            f"📉 Текущий статус: {st}\n"
            f"🏢 Клуб/Должность: {my_club}\n"
            f"🆔 Ваш ID: `{uid}`"
        )
        bot.send_message(message.chat.id, profile_text, parse_mode="Markdown")

    elif message.text == "Список клубов 📋":
        # Динамически собираем список из базы
        updated_list = "🏆 **СПИСОК ОФИЦИАЛЬНЫХ КЛУБОВ**\n\n"
        for name, staff in db["clubs"].items():
            owner = f"@{staff['owner']}" if staff['owner'] else "❓ Свободно"
            deputy = f" (Зам: @{staff['deputy']})" if staff['deputy'] else ""
            updated_list += f"{name} — {owner}{deputy}\n"
        bot.send_message(message.chat.id, updated_list, parse_mode="Markdown")

    elif message.text == "Топ клубов 🏆":
        bot.send_message(message.chat.id, db["config"].get("top_clubs_text", "Пусто"))

    elif message.text == "Завершение карьера 🚫":
        db["users"][uid]["is_retired"] = True
        save_database(db)
        bot.send_message(message.chat.id, "🚫 Вы завершили карьеру. Теперь вы в списке неактивных игроков.", reply_markup=main_menu_markup(message.from_user.id, un))

    elif message.text == "Возвращение карьеры 🔙":
        db["users"][uid]["is_retired"] = False
        save_database(db)
        bot.send_message(message.chat.id, "✅ С возвращением в спорт! Вы снова активны.", reply_markup=main_menu_markup(message.from_user.id, un))

# =================================================================
# 9. ОБРАБОТКА ИНЛАЙН-ОТВЕТОВ (ТРАНСФЕРЫ)
# =================================================================

@bot.callback_query_handler(func=lambda call: True)
def handle_callback_queries(call):
    db = load_database()
    # Формат данных: accept_ID_ОТПРАВИТЕЛЯ или decline_ID_ОТПРАВИТЕЛЯ
    data_parts = call.data.split("_")
    action = data_parts[0]
    sender_id = data_parts[1]
    
    player_uid = str(call.from_user.id)
    player_nick = db["users"].get(player_uid, {}).get("rb_nick", "Неизвестно")
    
    # Находим клуб отправителя
    sender_info = db["users"].get(sender_id, {})
    sender_un = sender_info.get("username", "")
    club_name = get_user_managed_club(sender_un) or "Клуб"

    if action == "accept":
        # Уведомление игроку
        bot.edit_message_text(f"✅ Вы ПРИНЯЛИ предложение от клуба {club_name}!", call.message.chat.id, call.message.message_id)
        # Уведомление владельцу
        bot.send_message(sender_id, f"🔥 Отличные новости! Игрок **{player_nick}** принял ваш контракт!", parse_mode="Markdown")
        # Пост в канал
        bot.send_message(CHANNEL_ID, f"🏠 **НОВЫЙ ТРАНСФЕР**\n\n🎮 Игрок: `{player_nick}`\n🏢 Перешел в: {club_name}\n🤝 Поздравляем с подписанием!")
    
    elif action == "decline":
        bot.edit_message_text(f"❌ Вы отклонили предложение от {club_name}.", call.message.chat.id, call.message.message_id)
        bot.send_message(sender_id, f"😔 Игрок **{player_nick}** отклонил ваше предложение.", parse_mode="Markdown")

# =================================================================
# 10. ЗАПУСК БОТА
# =================================================================

if __name__ == "__main__":
    print(f"[{datetime.datetime.now()}] Бот TM System v7 успешно запущен...")
    try:
        bot.infinity_polling(timeout=10, long_polling_timeout=5)
    except Exception as e:
        print(f"Ошибка при работе: {e}")
        time.sleep(5)
