import telebot
from telebot import types
import json
import os
import time
import logging

# =================================================================
# КОНФИГУРАЦИЯ
# =================================================================

TOKEN = os.getenv('TOKEN') 
CHANNEL_ID = '-1003740141875' 

# ГЛАВНЫЙ АДМИНИСТРАТОР (Твой юзернейм без @)
SUPER_ADMIN = "Nazikrrk" 

# Список владельцев клубов по умолчанию (для проверки прав на трансферы)
CLUB_OWNERS_LIST = {
    "banditdontrealme": "Inter Milan 🇮🇹",
    "ez_mbappe": "Real Madrid 🇪🇸",
    "estavaojr": "Bayern Munich 🇩🇪",
    "amojvucu": "Napoli 🇮🇹",
    "nikitos_201064": "Sporting 🇵🇹",
    "ilikembb": "Arsenal 🏴󠁧󠁢󠁥󠁮󠁧󠁿",
    "pheluix23": "Empoli 🇮🇹",
    "eoupapa": "Albacete 🇪🇸",
    "nurikbro20145": "Zenit 🇷🇺",
    "mbappe_677": "Fiorentina 🇮🇹",
    "o17_misty": "Ac Milan 🇮🇹",
    "suleyman1453638": "Juventus 🇮🇹"
}

bot = telebot.TeleBot(TOKEN)
DATA_FILE = "tm_pro_v5_database.json"

logging.basicConfig(level=logging.INFO)

# =================================================================
# СИСТЕМА ДАННЫХ (JSON)
# =================================================================

def load_db():
    """Загрузка базы данных с проверкой на существование"""
    if not os.path.exists(DATA_FILE):
        return {
            "users": {},
            "admins": [SUPER_ADMIN.lower()],
            "config": {
                "top_clubs_text": "🏆 ТОП КЛУБОВ\n(Настройте через админ-панель)",
                "clubs_list_text": "📋 СПИСОК КЛУБОВ\n(Настройте через админ-панель)"
            }
        }
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {"users": {}, "admins": [SUPER_ADMIN.lower()], "config": {}}

def save_db(data):
    """Сохранение базы данных"""
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# =================================================================
# СИСТЕМА ТАЙМЕРОВ (КД)
# =================================================================

def check_cooldown(user_id, username, action, seconds):
    """
    Проверка кулдауна.
    ДЛЯ ВЛАДЕЛЬЦА (@Nazikrrk) И АДМИНОВ КД ВСЕГДА 0.
    """
    db = load_db()
    uname_low = (username or "").lower()
    
    # Если ты или админ — ограничений нет
    if uname_low in db["admins"]:
        return False, 0
    
    uid_str = str(user_id)
    if uid_str not in db["users"]:
        return False, 0
    
    last_time = db["users"][uid_str].get("cooldowns", {}).get(action, 0)
    diff = time.time() - last_time
    
    if diff < seconds:
        return True, int(seconds - diff)
    return False, 0

def set_cooldown(user_id, action):
    """Запись времени последнего действия"""
    db = load_db()
    uid_str = str(user_id)
    if "cooldowns" not in db["users"][uid_str]:
        db["users"][uid_str]["cooldowns"] = {}
    db["users"][uid_str]["cooldowns"][action] = time.time()
    save_db(db)

# =================================================================
# ИНТЕРФЕЙС (КЛАВИАТУРЫ)
# =================================================================

def get_main_kb(user_id, username):
    db = load_db()
    uid_str = str(user_id)
    u_info = db["users"].get(uid_str, {})
    uname_low = (username or "").lower()
    is_admin = uname_low in db["admins"]

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    
    if is_admin:
        markup.add(types.KeyboardButton("👑 Админ Панель"))

    if u_info.get("is_retired"):
        markup.add(types.KeyboardButton("Возвращение карьеры 🔙"))
        markup.add(types.KeyboardButton("Написать админам 📩"))
        markup.add(types.KeyboardButton("Список клубов 📋"), types.KeyboardButton("Топ клубов 🏆"))
        markup.add(types.KeyboardButton("Профиль 👤"))
        return markup

    markup.add(types.KeyboardButton("Свободный агент 🆓"), types.KeyboardButton("Свой текст 📝"))
    
    # Проверка прав на трансферы (Владельцы, Личные влд, Админы)
    is_owner = (uname_low in CLUB_OWNERS_LIST or u_info.get("owned_club") or is_admin)
    if is_owner:
        markup.add(types.KeyboardButton("Предложить трансфер 🤝"))

    markup.add(types.KeyboardButton("Список клубов 📋"), types.KeyboardButton("Топ клубов 🏆"))
    markup.add(types.KeyboardButton("Профиль 👤"), types.KeyboardButton("Изменить ник ✏️"))
    markup.add(types.KeyboardButton("Написать админам 📩"), types.KeyboardButton("Завершение карьеры 🚫"))
    
    return markup

def get_admin_kb(username):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("🚫 Забанить", "✅ Разбанить")
    markup.add("🔑 Дать влд", "🗑 Снять влд")
    
    if username.lower() == SUPER_ADMIN.lower():
        markup.add("⭐ Дать админку", "❌ Снять админку")
        
    markup.add("📝 Изменить список", "🔥 Изменить ТОП")
    markup.add("🔙 Назад в меню")
    return markup

def get_cancel_kb():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("Отмена 🔙")
    return markup

# =================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# =================================================================

def find_user_by_username(target_username):
    target_username = target_username.replace("@", "").lower().strip()
    db = load_db()
    for uid, info in db["users"].items():
        if info.get("username") == target_username:
            return uid
    return None

# =================================================================
# ОБРАБОТЧИКИ ШАГОВ (NEXT STEP)
# =================================================================

def step_register_nickname(message):
    if message.text == "Отмена 🔙":
        bot.send_message(message.chat.id, "❌ Регистрация прервана. Напишите /start снова.", reply_markup=types.ReplyKeyboardRemove())
        return
    if not message.text:
        msg = bot.send_message(message.chat.id, "⚠️ Введите текст ника:")
        bot.register_next_step_handler(msg, step_register_nickname)
        return
        
    db = load_db()
    db["users"][str(message.from_user.id)]["rb_nick"] = message.text.strip()
    save_db(db)
    bot.send_message(message.chat.id, f"✅ Ник {message.text} сохранен!", reply_markup=get_main_kb(message.from_user.id, message.from_user.username))

def step_change_nickname(message):
    if message.text == "Отмена 🔙":
        bot.send_message(message.chat.id, "🏠 Отмена.", reply_markup=get_main_kb(message.from_user.id, message.from_user.username))
        return
    
    on_cd, wait = check_cooldown(message.from_user.id, message.from_user.username, "nick_change", 604800) # 7 дней
    if on_cd:
        bot.send_message(message.chat.id, f"⚠️ Лимит смены ника! Осталось ждать: {wait // 3600} часов.")
        return

    db = load_db()
    db["users"][str(message.from_user.id)]["rb_nick"] = message.text.strip()
    save_db(db)
    set_cooldown(message.from_user.id, "nick_change")
    bot.send_message(message.chat.id, "✅ Ник успешно изменен!", reply_markup=get_main_kb(message.from_user.id, message.from_user.username))

def step_send_report(message):
    if message.text == "Отмена 🔙":
        bot.send_message(message.chat.id, "🏠 Отмена.", reply_markup=get_main_kb(message.from_user.id, message.from_user.username))
        return
    
    on_cd, wait = check_cooldown(message.from_user.id, message.from_user.username, "report", 1200) # 20 мин
    if on_cd:
        bot.send_message(message.chat.id, f"⚠️ Слишком часто! Ждите {wait // 60} мин.")
        return

    db = load_db()
    sender = f"@{message.from_user.username}" if message.from_user.username else f"ID: {message.from_user.id}"
    alert = f"📩 **ОБРАЩЕНИЕ К АДМИНАМ**\n👤 От: {sender}\n💬 Текст: {message.text}"
    
    sent = False
    for adm_name in db["admins"]:
        adm_id = find_user_by_username(adm_name)
        if adm_id:
            try:
                bot.send_message(adm_id, alert, parse_mode="Markdown")
                sent = True
            except: pass
    
    if sent:
        set_cooldown(message.from_user.id, "report")
        bot.send_message(message.chat.id, "✅ Ваше сообщение отправлено админам!", reply_markup=get_main_kb(message.from_user.id, message.from_user.username))
    else:
        bot.send_message(message.chat.id, "❌ Сейчас нет активных админов.")

def step_custom_announcement(message):
    if message.text == "Отмена 🔙":
        bot.send_message(message.chat.id, "🏠 Отмена.", reply_markup=get_main_kb(message.from_user.id, message.from_user.username))
        return
    
    # КД 12 часов
    on_cd, wait = check_cooldown(message.from_user.id, message.from_user.username, "announcement", 43200)
    if on_cd:
        bot.send_message(message.chat.id, f"⚠️ Вы сможете написать через {wait // 3600} ч. { (wait % 3600) // 60 } мин.")
        return

    db = load_db()
    nick = db["users"][str(message.from_user.id)].get("rb_nick", "Игрок")
    tag = f"@{message.from_user.username}" if message.from_user.username else "Скрыт"
    
    try:
        # Отправляем БЕЗ Markdown чтобы не ловить ошибку 400 на спецсимволах пользователя
        final_msg = f"📝 НОВОЕ СООБЩЕНИЕ\n👤 От: {nick} ({tag})\n💬 Текст: {message.text}"
        bot.send_message(CHANNEL_ID, final_msg)
        set_cooldown(message.from_user.id, "announcement")
        bot.send_message(message.chat.id, "✅ Опубликовано в канале!", reply_markup=get_main_kb(message.from_user.id, message.from_user.username))
    except Exception as e:
        bot.send_message(message.chat.id, "❌ Бот не может отправить сообщение в канал. Проверьте права.")

def step_send_contract(message, club):
    if message.text == "Отмена 🔙":
        bot.send_message(message.chat.id, "🏠 Отмена.", reply_markup=get_main_kb(message.from_user.id, message.from_user.username))
        return
    
    target_uid = find_user_by_username(message.text)
    if not target_uid:
        bot.send_message(message.chat.id, "❌ Пользователь не найден в базе бота.")
        return

    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("✅ Принять", callback_data=f"tr_yes_{message.from_user.id}"),
           types.InlineKeyboardButton("❌ Отклонить", callback_data=f"tr_no_{message.from_user.id}"))
    
    try:
        bot.send_message(target_uid, f"⚽️ **ВАМ ПРЕДЛОЖИЛИ КОНТРАКТ!**\n🏢 Клуб: {club}\n👤 Отправитель: @{message.from_user.username}", reply_markup=kb, parse_mode="Markdown")
        bot.send_message(message.chat.id, "✅ Запрос отправлен игроку!", reply_markup=get_main_kb(message.from_user.id, message.from_user.username))
    except:
        bot.send_message(message.chat.id, "❌ Не удалось отправить сообщение игроку.")

# =================================================================
# АДМИНИСТРАТИВНЫЕ ФУНКЦИИ (ПОДРОБНО)
# =================================================================

def step_admin_ban(message):
    if message.text == "Отмена 🔙":
        bot.send_message(message.chat.id, "🏠 Отмена.", reply_markup=get_admin_kb(message.from_user.username))
        return
    uid = find_user_by_username(message.text)
    if uid:
        db = load_db()
        db["users"][uid]["is_banned"] = True
        save_db(db)
        bot.send_message(message.chat.id, f"✅ @{message.text} забанен!")
    else:
        bot.send_message(message.chat.id, "❌ Не найден.")

def step_admin_unban(message):
    if message.text == "Отмена 🔙":
        bot.send_message(message.chat.id, "🏠 Отмена.", reply_markup=get_admin_kb(message.from_user.username))
        return
    uid = find_user_by_username(message.text)
    if uid:
        db = load_db()
        db["users"][uid]["is_banned"] = False
        save_db(db)
        bot.send_message(message.chat.id, f"✅ @{message.text} разбанен!")
    else:
        bot.send_message(message.chat.id, "❌ Не найден.")

def step_admin_add_admin(message):
    if message.text == "Отмена 🔙":
        bot.send_message(message.chat.id, "🏠 Отмена.", reply_markup=get_admin_kb(SUPER_ADMIN))
        return
    tag = message.text.replace("@", "").lower().strip()
    db = load_db()
    if tag not in db["admins"]:
        db["admins"].append(tag)
        save_db(db)
        bot.send_message(message.chat.id, f"✅ @{tag} теперь администратор!")
    else:
        bot.send_message(message.chat.id, "⚠️ Уже в списке.")

def step_admin_edit_list(message):
    if message.text == "Отмена 🔙":
        bot.send_message(message.chat.id, "🏠 Отмена.", reply_markup=get_admin_kb(message.from_user.username))
        return
    db = load_db()
    db["config"]["clubs_list_text"] = message.text
    save_db(db)
    bot.send_message(message.chat.id, "✅ Список клубов обновлен!")

def step_admin_edit_top(message):
    if message.text == "Отмена 🔙":
        bot.send_message(message.chat.id, "🏠 Отмена.", reply_markup=get_admin_kb(message.from_user.username))
        return
    db = load_db()
    db["config"]["top_clubs_text"] = message.text
    save_db(db)
    bot.send_message(message.chat.id, "✅ ТОП обновлен!")

# =================================================================
# ОСНОВНОЙ ЦИКЛ ОБРАБОТКИ
# =================================================================

@bot.message_handler(commands=['start'])
def cmd_start_handler(message):
    bot.clear_step_handler_by_chat_id(message.chat.id)
    db = load_db()
    uid = str(message.from_user.id)
    uname = (message.from_user.username or "нет").lower()
    
    if uid not in db["users"]:
        db["users"][uid] = {
            "username": uname,
            "rb_nick": None,
            "is_retired": False,
            "is_banned": False,
            "owned_club": None,
            "cooldowns": {}
        }
    else:
        db["users"][uid]["username"] = uname
    
    save_db(db)

    # Проверка на бан
    if db["users"][uid].get("is_banned") and uname != SUPER_ADMIN.lower():
        bot.send_message(message.chat.id, "🚫 Вы заблокированы администрацией.")
        return

    # Если ник не введен
    if not db["users"][uid].get("rb_nick"):
        msg = bot.send_message(message.chat.id, "👋 Привет! Для работы с ботом введи свой ник в Roblox:", reply_markup=get_cancel_kb())
        bot.register_next_step_handler(msg, step_register_nickname)
    else:
        bot.send_message(message.chat.id, "🔘 Выберите нужный раздел:", reply_markup=get_main_kb(message.from_user.id, uname))

@bot.message_handler(content_types=['text'])
def text_handler(message):
    uid = str(message.from_user.id)
    uname = (message.from_user.username or "").lower()
    db = load_db()
    
    if uid not in db["users"]: return
    u_info = db["users"][uid]
    is_admin = uname in db["admins"]

    # Блок забаненных
    if u_info.get("is_banned") and uname != SUPER_ADMIN.lower(): return

    # --- КНОПКИ АДМИНА ---
    if message.text == "👑 Админ Панель" and is_admin:
        bot.send_message(message.chat.id, "🛠 Режим администратора:", reply_markup=get_admin_kb(uname))
        return

    if message.text == "🔙 Назад в меню":
        bot.send_message(message.chat.id, "🏠 Главное меню:", reply_markup=get_main_kb(message.from_user.id, uname))
        return

    if is_admin:
        if message.text == "🚫 Забанить":
            m = bot.send_message(message.chat.id, "Введите @username для бана:", reply_markup=get_cancel_kb())
            bot.register_next_step_handler(m, step_admin_ban)
            return
        elif message.text == "✅ Разбанить":
            m = bot.send_message(message.chat.id, "Введите @username для разбана:", reply_markup=get_cancel_kb())
            bot.register_next_step_handler(m, step_admin_unban)
            return
        elif message.text == "⭐ Дать админку" and uname == SUPER_ADMIN.lower():
            m = bot.send_message(message.chat.id, "Введите @username:", reply_markup=get_cancel_kb())
            bot.register_next_step_handler(m, step_admin_add_admin)
            return
        elif message.text == "📝 Изменить список":
            m = bot.send_message(message.chat.id, "Введите новый текст списка клубов:", reply_markup=get_cancel_kb())
            bot.register_next_step_handler(m, step_admin_edit_list)
            return
        elif message.text == "🔥 Изменить ТОП":
            m = bot.send_message(message.chat.id, "Введите новый текст ТОПа:", reply_markup=get_cancel_kb())
            bot.register_next_step_handler(m, step_admin_edit_top)
            return

    # --- КНОПКИ ИГРОКА ---
    if message.text == "Свободный агент 🆓":
        # КД 12 часов для обычных, 0 для админов
        on_cd, wait = check_cooldown(message.from_user.id, uname, "fa_status", 43200)
        if on_cd:
            bot.send_message(message.chat.id, f"⚠️ Подождите еще {wait // 3600} ч.")
            return
        
        nick = u_info.get("rb_nick", "Игрок")
        tag = f"@{uname}" if uname else "Юзер скрыт"
        try:
            bot.send_message(CHANNEL_ID, f"🆓 **СВОБОДНЫЙ АГЕНТ**\n👤 Игрок: {nick}\n🔗 Связь: {tag}\n⚽️ Готов к предложениям!")
            set_cooldown(message.from_user.id, "fa_status")
            bot.send_message(message.chat.id, "✅ Статус отправлен в канал!")
        except:
            bot.send_message(message.chat.id, "❌ Ошибка публикации.")

    elif message.text == "Свой текст 📝":
        m = bot.send_message(message.chat.id, "💬 Введите текст для канала (Без КД для админов):", reply_markup=get_cancel_kb())
        bot.register_next_step_handler(m, step_custom_announcement)

    elif message.text == "Предложить трансфер 🤝":
        owner_club = CLUB_OWNERS_LIST.get(uname) or u_info.get("owned_club") or (is_admin and "Администрация")
        if owner_club:
            m = bot.send_message(message.chat.id, "🎯 Введите @username игрока:", reply_markup=get_cancel_kb())
            bot.register_next_step_handler(m, step_send_contract, owner_club)

    elif message.text == "Профиль 👤":
        st = "Пенсия ❌" if u_info.get("is_retired") else "Актив ✅"
        cl = CLUB_OWNERS_LIST.get(uname) or u_info.get("owned_club") or "Нет"
        bot.send_message(message.chat.id, f"👤 **ПРОФИЛЬ**\n🎮 Roblox: {u_info.get('rb_nick')}\n📊 Статус: {st}\n🏢 Клуб: {cl}")

    elif message.text == "Список клубов 📋":
        bot.send_message(message.chat.id, db["config"].get("clubs_list_text", "Пусто"))

    elif message.text == "Топ клубов 🏆":
        bot.send_message(message.chat.id, db["config"].get("top_clubs_text", "Пусто"))

    elif message.text == "Написать админам 📩":
        m = bot.send_message(message.chat.id, "✍️ Опишите проблему:", reply_markup=get_cancel_kb())
        bot.register_next_step_handler(m, step_send_report)

    elif message.text == "Завершение карьеры 🚫":
        db["users"][uid]["is_retired"] = True
        save_db(db)
        bot.send_message(message.chat.id, "🚫 Карьера завершена. Вы больше не в поиске клубов.", reply_markup=get_main_kb(message.from_user.id, uname))

    elif message.text == "Возвращение карьеры 🔙":
        db["users"][uid]["is_retired"] = False
        save_db(db)
        bot.send_message(message.chat.id, "✅ Вы вернулись в строй!", reply_markup=get_main_kb(message.from_user.id, uname))

    elif message.text == "Изменить ник ✏️":
        m = bot.send_message(message.chat.id, "✏️ Введите новый ник:", reply_markup=get_cancel_kb())
        bot.register_next_step_handler(m, step_change_nickname)

# =================================================================
# ОБРАБОТКА ТРАНСФЕРОВ
# =================================================================

@bot.callback_query_handler(func=lambda call: call.data.startswith("tr_"))
def tr_callback_handler(call):
    db = load_db()
    action = call.data.split("_")[1] # yes/no
    sender_id = str(call.data.split("_")[2])
    player_id = str(call.from_user.id)
    
    player_nick = db["users"].get(player_id, {}).get("rb_nick", "Игрок")
    sender_uname = db["users"].get(sender_id, {}).get("username", "").lower()
    club = CLUB_OWNERS_LIST.get(sender_uname) or db["users"].get(sender_id, {}).get("owned_club", "Клуб")

    if action == "yes":
        bot.edit_message_text(f"✅ Вы приняли контракт от {club}!", call.message.chat.id, call.message.message_id)
        bot.send_message(sender_id, f"🔥 {player_nick} ПРИНЯЛ контракт!")
        bot.send_message(CHANNEL_ID, f"🏠 **ТРАНСФЕР СОСТОЯЛСЯ**\n🎮 Игрок: {player_nick}\n🏢 Клуб: {club}")
    else:
        bot.edit_message_text("❌ Вы отклонили предложение.", call.message.chat.id, call.message.message_id)
        bot.send_message(sender_id, f"❌ {player_nick} отклонил запрос.")

# =================================================================
# ЗАПУСК
# =================================================================

if __name__ == "__main__":
    print("Бот Nazikrrk успешно запущен и готов к работе...")
    bot.infinity_polling()
