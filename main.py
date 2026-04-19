import asyncio
import sqlite3
import random
import logging
import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from aiogram.types import (
    InlineKeyboardButton, 
    ReplyKeyboardRemove, 
    BotCommand, 
    CallbackQuery, 
    Message
)

# ==============================================================================
# КОНФИГУРАЦИЯ И НАСТРОЙКИ
# ==============================================================================
TOKEN = "8633419537:AAF6r1H1YtfI2whTHVdKzF2JVQnxgu9XfU4"
CHANNEL_ID = "@pistonCUPsls"
# Твои ID админов, которые имеют полный доступ
SUPER_ADMINS = [5845609895, 6740071266]
BOT_USERNAME = "@TernatLeague_Bot"

# Настройка логирования для отслеживания ошибок в консоли Railway
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)

bot = Bot(token=TOKEN)
dp = Dispatcher()

# ==============================================================================
# РАБОТА С БАЗОЙ ДАННЫХ (SQLITE)
# ==============================================================================
def db_query(query, params=(), fetchone=False, commit=False):
    """
    Универсальная функция для работы с БД. 
    Использует большой таймаут, чтобы избежать блокировок на сервере.
    """
    conn = sqlite3.connect('league_data.db', timeout=30)
    cur = conn.cursor()
    try:
        cur.execute(query, params)
        if commit:
            conn.commit()
        if fetchone:
            return cur.fetchone()
        return cur.fetchall()
    except Exception as e:
        logger.error(f"Критическая ошибка базы данных: {e}")
        return None
    finally:
        conn.close()

def init_db():
    """Инициализация структуры таблиц при запуске бота"""
    logger.info("Инициализация базы данных...")
    db_query("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, role TEXT)", commit=True)
    db_query("CREATE TABLE IF NOT EXISTS clubs (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, vld_id INTEGER, zams TEXT DEFAULT '')", commit=True)
    db_query("""CREATE TABLE IF NOT EXISTS matches (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        t1_id INTEGER, t2_id INTEGER, 
        time TEXT, otpis1 INTEGER DEFAULT 0, 
        otpis2 INTEGER DEFAULT 0, msg_id INTEGER, vip_waiter INTEGER)""", commit=True)
    db_query("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)", commit=True)
    
    # Создаем запись для расписания, если её нет
    existing_sched = db_query("SELECT value FROM settings WHERE key='schedule'", fetchone=True)
    if not existing_sched:
        db_query("INSERT INTO settings (key, value) VALUES ('schedule', 'Расписание пока не установлено')", commit=True)

# ==============================================================================
# СОСТОЯНИЯ КОНЕЧНОГО АВТОМАТА (FSM)
# ==============================================================================
class Form(StatesGroup):
    # Состояния для клубов
    add_club_name = State()
    add_club_vld = State()
    
    # Состояния для расписания
    edit_schedule_text = State()
    
    # Состояния для создания матча
    m_t1 = State()
    m_t2 = State()
    m_time = State()
    
    # Состояния для табов
    tab_match_select = State()
    tab_photo1 = State()
    tab_photo2 = State()
    
    # Состояния для редактирования клуба
    edit_club_select = State()
    edit_club_choice = State()
    edit_club_input = State()
    
    # Администрирование ролей
    give_admin_id = State()
    remove_admin_id = State()

# ==============================================================================
# КЛАВИАТУРЫ (ИНТЕРФЕЙС)
# ==============================================================================
def get_main_kb(user_id):
    """Главное меню (Reply-кнопки)"""
    builder = ReplyKeyboardBuilder()
    builder.button(text="📅 Расписание матчей")
    builder.button(text="📝 Дать отпись")
    builder.button(text="📸 Дать табы")
    
    # Проверка прав пользователя
    is_admin = db_query("SELECT role FROM users WHERE user_id=?", (user_id,), fetchone=True)
    if user_id in SUPER_ADMINS or is_admin:
        builder.button(text="⚙️ Админ панель")
    
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)

def get_admin_kb(user_id):
    """Кнопки управления (Inline-кнопки)"""
    builder = InlineKeyboardBuilder()
    builder.button(text="🏠 Добавить клуб", callback_data="adm_add_club")
    builder.button(text="✏️ Изменить клуб", callback_data="adm_edit_club")
    builder.button(text="⚽ Создать матч", callback_data="adm_make_match")
    builder.button(text="📅 Изменить расписание", callback_data="adm_edit_sched")
    builder.button(text="🗑 Удалить клуб", callback_data="adm_del_club")
    
    # Специфические кнопки для супер-админов
    if user_id in SUPER_ADMINS:
        builder.button(text="👑 Дать админку", callback_data="adm_give_role")
        builder.button(text="❌ Убрать админа", callback_data="adm_remove_role")
    
    builder.adjust(1)
    return builder.as_markup()

# ==============================================================================
# ОБЩИЕ КОМАНДЫ
# ==============================================================================
@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    """Команда /start - сброс всех состояний и запуск"""
    await state.clear()
    init_db()
    logger.info(f"Пользователь {message.from_user.id} запустил бота.")
    await message.answer(
        "⚽ **Добро пожаловать в систему управления футбольной лигой!**\n\n"
        "Здесь вы можете отписываться на матчи, передавать табы и следить за расписанием.",
        reply_markup=get_main_kb(message.from_user.id),
        parse_mode="Markdown"
    )

@dp.message(F.text == "📅 Расписание матчей")
async def show_schedule(message: Message):
    """Показ текущего расписания из базы данных"""
    sched_data = db_query("SELECT value FROM settings WHERE key='schedule'", fetchone=True)
    text = sched_data[0] if sched_data else "Расписание не найдено."
    await message.answer(f"📅 **Актуальное расписание:**\n\n{text}", parse_mode="Markdown")

# ==============================================================================
# АДМИН-ПАНЕЛЬ: УПРАВЛЕНИЕ РАСПИСАНИЕМ
# ==============================================================================
@dp.callback_query(F.data == "adm_edit_sched")
async def edit_sched_start(callback: CallbackQuery, state: FSMContext):
    """Начало процесса изменения расписания"""
    await callback.message.answer("Отправьте новый текст для расписания:")
    await state.set_state(Form.edit_schedule_text)
    await callback.answer()

@dp.message(Form.edit_schedule_text)
async def edit_sched_finish(message: Message, state: FSMContext):
    """Сохранение нового расписания в БД"""
    new_text = message.text
    db_query("UPDATE settings SET value=? WHERE key='schedule'", (new_text,), commit=True)
    await message.answer("✅ **Расписание успешно обновлено!**", reply_markup=get_main_kb(message.from_user.id))
    await state.clear()

# ==============================================================================
# АДМИН-ПАНЕЛЬ: УПРАВЛЕНИЕ РОЛЯМИ (УБРАТЬ АДМИНА)
# ==============================================================================
@dp.callback_query(F.data == "adm_remove_role")
async def remove_role_start(callback: CallbackQuery, state: FSMContext):
    """Запрос списка или ID для удаления админа"""
    admins = db_query("SELECT user_id FROM users WHERE role='admin'")
    if not admins:
        return await callback.message.answer("Список администраторов пуст.")
    
    text = "Список текущих админов:\n"
    for adm in admins:
        text += f"- `{adm[0]}`\n"
    
    await callback.message.answer(f"{text}\nВведите Telegram ID пользователя, которого нужно разжаловать:")
    await state.set_state(Form.remove_admin_id)
    await callback.answer()

@dp.message(Form.remove_admin_id)
async def remove_role_finish(message: Message, state: FSMContext):
    """Удаление прав админа"""
    try:
        target_id = int(message.text)
        db_query("DELETE FROM users WHERE user_id=?", (target_id,), commit=True)
        await message.answer(f"❌ Пользователь `{target_id}` больше не является админом.", parse_mode="Markdown")
        await state.clear()
    except ValueError:
        await message.answer("Ошибка! Введите корректный числовой ID.")

@dp.callback_query(F.data == "adm_give_role")
async def give_role_start(callback: CallbackQuery, state: FSMContext):
    """Запрос ID для назначения нового админа"""
    await callback.message.answer("Введите Telegram ID пользователя, которому нужно дать права админа:")
    await state.set_state(Form.give_admin_id)
    await callback.answer()

@dp.message(Form.give_admin_id)
async def give_role_finish(message: Message, state: FSMContext):
    """Назначение админа"""
    try:
        target_id = int(message.text)
        db_query("INSERT OR IGNORE INTO users (user_id, role) VALUES (?, 'admin')", (target_id,), commit=True)
        await message.answer(f"👑 Пользователь `{target_id}` назначен администратором.", parse_mode="Markdown")
        await state.clear()
    except ValueError:
        await message.answer("Ошибка! Введите корректный числовой ID.")

# ==============================================================================
# АДМИН-ПАНЕЛЬ: ИЗМЕНЕНИЕ КЛУБА (ИСПРАВЛЕННЫЙ ЗАМ)
# ==============================================================================
@dp.callback_query(F.data == "adm_edit_club")
async def edit_club_list(callback: CallbackQuery, state: FSMContext):
    """Выбор клуба для редактирования"""
    clubs = db_query("SELECT id, name FROM clubs")
    if not clubs:
        return await callback.answer("Клубы не созданы!", show_alert=True)
    
    builder = InlineKeyboardBuilder()
    for cid, name in clubs:
        builder.button(text=f"⚙️ {name}", callback_data=f"edit_cl_{cid}")
    builder.adjust(2)
    await callback.message.edit_text("Выберите клуб для внесения изменений:", reply_markup=builder.as_markup())
    await state.set_state(Form.edit_club_select)

@dp.callback_query(F.data.startswith("edit_cl_"), Form.edit_club_select)
async def edit_club_options(callback: CallbackQuery, state: FSMContext):
    """Меню опций редактирования конкретного клуба"""
    club_id = callback.data.split("_")[2]
    await state.update_data(target_cid=club_id)
    
    club_info = db_query("SELECT name, vld_id, zams FROM clubs WHERE id=?", (club_id,), fetchone=True)
    
    builder = InlineKeyboardBuilder()
    builder.button(text="📝 Сменить название", callback_data="upd_name")
    builder.button(text="👤 Сменить ВЛД (ID)", callback_data="upd_vld")
    builder.button(text="➕ Добавить зама (ID)", callback_data="upd_addzam")
    builder.button(text="➖ Удалить всех замов", callback_data="upd_clearzams")
    builder.button(text="⬅️ Назад", callback_data="adm_edit_club")
    builder.adjust(1)
    
    await callback.message.edit_text(
        f"**Редактирование клуба:** {club_info[0]}\n"
        f"**Текущий ВЛД:** `{club_info[1]}`\n"
        f"**Текущие замы:** `{club_info[2] if club_info[2] else 'нет'}`\n\n"
        "Что именно вы хотите изменить?",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )
    await state.set_state(Form.edit_club_choice)

@dp.callback_query(F.data.startswith("upd_"), Form.edit_club_choice)
async def edit_club_input_request(callback: CallbackQuery, state: FSMContext):
    """Запрос нового значения в зависимости от выбора"""
    action = callback.data
    
    if action == "upd_clearzams":
        data = await state.get_data()
        db_query("UPDATE clubs SET zams='' WHERE id=?", (data['target_cid'],), commit=True)
        await callback.answer("Замы удалены")
        return await edit_club_list(callback, state)

    await state.update_data(edit_action=action)
    prompt = {
        "upd_name": "Введите новое название клуба:",
        "upd_vld": "Введите новый Telegram ID владельца:",
        "upd_addzam": "Введите Telegram ID нового зама для добавления:"
    }
    await callback.message.answer(prompt[action])
    await state.set_state(Form.edit_club_input)
    await callback.answer()

@dp.message(Form.edit_club_input)
async def edit_club_save(message: Message, state: FSMContext):
    """Сохранение изменений клуба (Название, ВЛД или Зам)"""
    data = await state.get_data()
    cid = data['target_cid']
    action = data['edit_action']
    val = message.text
    
    try:
        if action == "upd_name":
            db_query("UPDATE clubs SET name=? WHERE id=?", (val, cid), commit=True)
        elif action == "upd_vld":
            db_query("UPDATE clubs SET vld_id=? WHERE id=?", (int(val), cid), commit=True)
        elif action == "upd_addzam":
            # Важная часть: добавление зама без удаления старых
            current_zams = db_query("SELECT zams FROM clubs WHERE id=?", (cid,), fetchone=True)[0]
            new_zams_list = f"{current_zams},{val}" if current_zams else val
            db_query("UPDATE clubs SET zams=? WHERE id=?", (new_zams_list, cid), commit=True)
        
        await message.answer("✅ **Данные успешно обновлены!**", reply_markup=get_main_kb(message.from_user.id))
        await state.clear()
    except Exception as e:
        await message.answer(f"Произошла ошибка при сохранении: {e}")

# ==============================================================================
# ЛОГИКА СОЗДАНИЯ МАТЧА
# ==============================================================================
@dp.callback_query(F.data == "adm_make_match")
async def create_match_t1(callback: CallbackQuery, state: FSMContext):
    """Выбор первой команды для матча"""
    clubs = db_query("SELECT id, name FROM clubs")
    if len(clubs) < 2:
        return await callback.answer("Недостаточно клубов (минимум 2)!", show_alert=True)
    
    builder = InlineKeyboardBuilder()
    for cid, name in clubs:
        builder.button(text=name, callback_data=f"matcht1_{cid}")
    builder.adjust(2)
    await callback.message.edit_text("Выберите **ПЕРВУЮ** команду (Хозяева):", reply_markup=builder.as_markup(), parse_mode="Markdown")
    await state.set_state(Form.m_t1)

@dp.callback_query(F.data.startswith("matcht1_"), Form.m_t1)
async def create_match_t2(callback: CallbackQuery, state: FSMContext):
    """Выбор второй команды для матча"""
    t1_id = callback.data.split("_")[1]
    await state.update_data(team1=t1_id)
    
    clubs = db_query("SELECT id, name FROM clubs WHERE id != ?", (t1_id,))
    builder = InlineKeyboardBuilder()
    for cid, name in clubs:
        builder.button(text=name, callback_data=f"matcht2_{cid}")
    builder.adjust(2)
    await callback.message.edit_text("Выберите **ВТОРУЮ** команду (Гости):", reply_markup=builder.as_markup(), parse_mode="Markdown")
    await state.set_state(Form.m_t2)

@dp.callback_query(F.data.startswith("matcht2_"), Form.m_t2)
async def create_match_time(callback: CallbackQuery, state: FSMContext):
    """Запрос времени начала матча"""
    t2_id = callback.data.split("_")[1]
    await state.update_data(team2=t2_id)
    await callback.message.answer("Укажите время начала матча (например, 15:30):")
    await state.set_state(Form.m_time)

@dp.message(Form.m_time)
async def create_match_finish(message: Message, state: FSMContext):
    """Создание записи о матче и публикация поста"""
    data = await state.get_data()
    t1_id, t2_id, m_time = data['team1'], data['team2'], message.text
    
    t1_name = db_query("SELECT name FROM clubs WHERE id=?", (t1_id,), fetchone=True)[0]
    t2_name = db_query("SELECT name FROM clubs WHERE id=?", (t2_id,), fetchone=True)[0]
    
    post_text = (
        f"🏟 **НОВЫЙ МАТЧ НАЗНАЧЕН**\n\n"
        f"⚽ {t1_name} vs {t2_name}\n"
        f"⏰ Время: {m_time}\n\n"
        f"Статус отписи:\n"
        f"{t1_name} — ❌\n"
        f"{t2_name} — ❌\n\n"
        f"Отпись производить здесь: {BOT_USERNAME}"
    )
    
    try:
        sent_msg = await bot.send_message(CHANNEL_ID, post_text, parse_mode="Markdown")
        db_query(
            "INSERT INTO matches (t1_id, t2_id, time, msg_id) VALUES (?, ?, ?, ?)", 
            (t1_id, t2_id, m_time, sent_msg.message_id), 
            commit=True
        )
        await message.answer("✅ Матч успешно создан и опубликован!", reply_markup=get_main_kb(message.from_user.id))
    except Exception as e:
        await message.answer(f"Ошибка публикации: {e}. Проверьте права бота в канале.")
    
    await state.clear()

# ==============================================================================
# СИСТЕМА ТАБОВ (СКРИНШОТОВ)
# ==============================================================================
@dp.message(F.text == "📸 Дать табы")
async def process_tabs_start(message: Message, state: FSMContext):
    """Начало процесса сдачи табов"""
    active_matches = db_query("SELECT id, t1_id, t2_id FROM matches WHERE otpis1=1 AND otpis2=1")
    if not active_matches:
        return await message.answer("Нет завершенных по отписи матчей.")
    
    builder = InlineKeyboardBuilder()
    for mid, t1, t2 in active_matches:
        n1 = db_query("SELECT name FROM clubs WHERE id=?", (t1,), fetchone=True)[0]
        n2 = db_query("SELECT name FROM clubs WHERE id=?", (t2,), fetchone=True)[0]
        builder.button(text=f"{n1} - {n2}", callback_data=f"seltab_{mid}")
    builder.adjust(1)
    
    await message.answer("Выберите матч для сдачи табов:", reply_markup=builder.as_markup())
    await state.set_state(Form.tab_match_select)

@dp.callback_query(F.data.startswith("seltab_"), Form.tab_match_select)
async def process_tabs_auth(callback: CallbackQuery, state: FSMContext):
    """Проверка прав на сдачу табов (ВЛД или Зам)"""
    mid = callback.data.split("_")[1]
    match = db_query("SELECT t1_id, t2_id FROM matches WHERE id=?", (mid,), fetchone=True)
    uid = str(callback.from_user.id)
    
    # Получаем инфо о командах
    team1 = db_query("SELECT vld_id, zams, name FROM clubs WHERE id=?", (match[0],), fetchone=True)
    team2 = db_query("SELECT vld_id, zams, name FROM clubs WHERE id=?", (match[1],), fetchone=True)
    
    allowed = False
    current_team_name = ""
    
    # Проверка команды 1
    if uid == str(team1[0]) or uid in str(team1[1]).split(","):
        allowed, current_team_name = True, team1[2]
    # Проверка команды 2
    elif uid == str(team2[0]) or uid in str(team2[1]).split(","):
        allowed, current_team_name = True, team2[2]
        
    if not allowed:
        return await callback.answer("Вы не являетесь ВЛД/Замом команд этого матча!", show_alert=True)
    
    await state.update_data(active_mid=mid, active_team=current_team_name)
    await callback.message.answer(f"Вы сдаете табы за команду: **{current_team_name}**\nПришлите скриншот 1-го тайма:")
    await state.set_state(Form.tab_photo1)
    await callback.answer()

@dp.message(Form.tab_photo1, F.photo)
async def process_tabs_p1(message: Message, state: FSMContext):
    """Получение первого скриншота"""
    await state.update_data(file1=message.photo[-1].file_id)
    await message.answer("Отлично! Теперь пришлите скриншот 2-го тайма:")
    await state.set_state(Form.tab_photo2)

@dp.message(Form.tab_photo2, F.photo)
async def process_tabs_p2(message: Message, state: FSMContext):
    """Получение второго скриншота и отправка админам"""
    data = await state.get_data()
    f1 = data['file1']
    f2 = message.photo[-1].file_id
    team = data['active_team']
    
    for admin_id in SUPER_ADMINS:
        try:
            await bot.send_message(admin_id, f"📸 **НОВЫЕ ТАБЫ**\nКоманда: {team}\nОтправил: {message.from_user.id}")
            await bot.send_photo(admin_id, f1, caption="1-й Тайм")
            await bot.send_photo(admin_id, f2, caption="2-й Тайм")
        except:
            pass
            
    await message.answer("✅ Табы успешно переданы администрации!", reply_markup=get_main_kb(message.from_user.id))
    await state.clear()

# ==============================================================================
# СИСТЕМА ОТПИСЕЙ
# ==============================================================================
@dp.message(F.text == "📝 Дать отпись")
async def otpis_start(message: Message):
    """Выбор матча для отписи"""
    pending = db_query("SELECT id, t1_id, t2_id FROM matches WHERE otpis1=0 OR otpis2=0")
    if not pending:
        return await message.answer("На данный момент нет активных отписей.")
    
    builder = InlineKeyboardBuilder()
    for mid, t1, t2 in pending:
        n1 = db_query("SELECT name FROM clubs WHERE id=?", (t1,), fetchone=True)[0]
        n2 = db_query("SELECT name FROM clubs WHERE id=?", (t2,), fetchone=True)[0]
        builder.button(text=f"{n1} vs {n2}", callback_data=f"do_otp_{mid}")
    builder.adjust(1)
    await message.answer("Выберите матч для подтверждения участия:", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("do_otp_"))
async def otpis_process(callback: CallbackQuery):
    """Логика нажатия на отпись"""
    mid = callback.data.split("_")[2]
    match = db_query("SELECT * FROM matches WHERE id=?", (mid,), fetchone=True)
    uid = callback.from_user.id
    
    # Данные клубов
    c1_info = db_query("SELECT vld_id, zams, name FROM clubs WHERE id=?", (match[1],), fetchone=True)
    c2_info = db_query("SELECT vld_id, zams, name FROM clubs WHERE id=?", (match[2],), fetchone=True)
    
    target_column = ""
    if str(uid) == str(c1_info[0]) or str(uid) in str(c1_info[1]):
        target_column = "otpis1"
    elif str(uid) == str(c2_info[0]) or str(uid) in str(c2_info[1]):
        target_column = "otpis2"
    
    if not target_column:
        return await callback.answer("Вы не входите в состав этих команд!", show_alert=True)
    
    db_query(f"UPDATE matches SET {target_column}=1 WHERE id=?", (mid,), commit=True)
    await callback.answer("✅ Ваше участие подтверждено!")
    
    # Обновление поста
    m = db_query("SELECT * FROM matches WHERE id=?", (mid,), fetchone=True)
    n1 = db_query("SELECT name FROM clubs WHERE id=?", (m[1],), fetchone=True)[0]
    n2 = db_query("SELECT name FROM clubs WHERE id=?", (m[2],), fetchone=True)[0]
    s1, s2 = ("✅" if m[4] else "❌"), ("✅" if m[5] else "❌")
    
    upd_text = (
        f"🏟 **ОБНОВЛЕНИЕ ОТПИСИ**\n\n"
        f"⚽ {n1} vs {n2}\n"
        f"⏰ Время: {m[3]}\n\n"
        f"Статус отписи:\n"
        f"{n1} — {s1}\n"
        f"{n2} — {s2}\n\n"
        f"Отпись производить здесь: {BOT_USERNAME}"
    )
    
    try:
        await bot.edit_message_text(upd_text, CHANNEL_ID, m[6], parse_mode="Markdown")
    except:
        pass
        
    # Если оба готовы - жребий VIP
    if m[4] == 1 and m[5] == 1:
        winner_vld = random.choice([c1_info[0], c2_info[0]])
        db_query("UPDATE matches SET vip_waiter=? WHERE id=?", (winner_vld, mid), commit=True)
        await bot.send_message(winner_vld, "🎲 **Жребий пал на вас!**\nВы создаете VIP. Напишите: `вип:ВашНик`", parse_mode="Markdown")

# ==============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ И АДМИН-МЕНЮ
# ==============================================================================
@dp.message(F.text == "⚙️ Админ панель")
async def show_admin_menu(message: Message):
    """Вход в админку"""
    is_admin = db_query("SELECT role FROM users WHERE user_id=?", (message.from_user.id,), fetchone=True)
    if message.from_user.id in SUPER_ADMINS or is_admin:
        await message.answer("🔧 **Управление Лигой:**", reply_markup=get_admin_kb(message.from_user.id))

@dp.callback_query(F.data == "adm_add_club")
async def add_club_init(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите название клуба:")
    await state.set_state(Form.add_club_name)
    await callback.answer()

@dp.message(F.text.startswith("вип:"))
async def handle_vip_data(message: Message):
    """Пересылка данных випа сопернику"""
    match_v = db_query("SELECT t1_id, t2_id, vip_waiter FROM matches WHERE vip_waiter IS NOT NULL ORDER BY id DESC LIMIT 1", fetchone=True)
    if match_v:
        # Определяем, кто соперник
        vld1 = db_query("SELECT vld_id FROM clubs WHERE id=?", (match_v[0],), fetchone=True)[0]
        vld2 = db_query("SELECT vld_id FROM clubs WHERE id=?", (match_v[1],), fetchone=True)[0]
        
        target = vld1 if str(message.from_user.id) == str(vld2) else vld2
        
        kb = InlineKeyboardBuilder().button(text="Матч начат! ✅", callback_data="match_active").as_markup()
        await bot.send_message(target, f"📩 **Данные VIP от соперника:**\n`{message.text}`", parse_mode="Markdown", reply_markup=kb)
        await message.answer("✅ Данные переданы сопернику.")

@dp.callback_query(F.data == "match_active")
async def match_active_notif(callback: CallbackQuery):
    await callback.message.edit_text(callback.message.text + "\n\n🟢 **Игра в процессе!**")

@dp.callback_query(F.data == "adm_del_club")
async def delete_club_process(callback: CallbackQuery):
    clubs = db_query("SELECT id, name FROM clubs")
    builder = InlineKeyboardBuilder()
    for cid, name in clubs:
        builder.button(text=f"🗑 {name}", callback_data=f"dropcl_{cid}")
    builder.adjust(1)
    await callback.message.edit_text("Какой клуб удалить из базы?", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("dropcl_"))
async def delete_club_execute(callback: CallbackQuery):
    cid = callback.data.split("_")[1]
    db_query("DELETE FROM clubs WHERE id=?", (cid,), commit=True)
    await callback.answer("Клуб удален навсегда")
    await delete_club_process(callback)

# ==============================================================================
# ТОЧКА ВХОДА
# ==============================================================================
async def main():
    logger.info("Бот запускается...")
    init_db()
    # Установка команд меню
    await bot.set_my_commands([
        BotCommand(command="start", description="Перезапустить бота"),
    ])
    # Запуск поллинга
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен.")
