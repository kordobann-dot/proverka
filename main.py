import asyncio
import sqlite3
import random
import logging
import sys
import os
from datetime import datetime

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
    Message,
    ContentType,
    BotCommandScopeDefault
)

# ==============================================================================
# БЛОК ГЛОБАЛЬНЫХ ПЕРЕМЕННЫХ И КОНФИГУРАЦИИ
# ==============================================================================
TOKEN = "8633419537:AAF6r1H1YtfI2whTHVdKzF2JVQnxgu9XfU4"
CHANNEL_ID = "@pistonCUPsls"
SUPER_ADMINS = [5845609895, 6740071266]
BOT_USERNAME = "@TernatLeague_Bot"

# Настройка логирования для отладки на сервере Railway
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] - %(name)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

bot = Bot(token=TOKEN)
dp = Dispatcher()

# ==============================================================================
# БЛОК РАБОТЫ С БАЗОЙ ДАННЫХ (SQLITE3)
# ==============================================================================
def db_query(query, params=(), fetchone=False, commit=False):
    """
    Функция для выполнения SQL-запросов. 
    Использует блокировку и увеличенный таймаут для избежания ошибок 'database is locked'.
    """
    db_path = 'league_data.db'
    connection = sqlite3.connect(db_path, timeout=60)
    cursor = connection.cursor()
    result = None
    try:
        cursor.execute(query, params)
        if commit:
            connection.commit()
        if fetchone:
            result = cursor.fetchone()
        else:
            result = cursor.fetchall()
    except Exception as e:
        logger.error(f"Критическая ошибка базы данных: {e}")
        logger.error(f"Запрос: {query}")
    finally:
        connection.close()
    return result

def init_db():
    """Инициализация таблиц базы данных при первом запуске."""
    logger.info("Начало инициализации базы данных...")
    
    # Таблица пользователей
    db_query("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        role TEXT DEFAULT 'user'
    )""", commit=True)
    
    # Таблица клубов
    db_query("""
    CREATE TABLE IF NOT EXISTS clubs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        vld_id INTEGER,
        zams TEXT DEFAULT ''
    )""", commit=True)
    
    # Таблица матчей
    db_query("""
    CREATE TABLE IF NOT EXISTS matches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        t1_id INTEGER,
        t2_id INTEGER,
        time TEXT,
        otpis1 INTEGER DEFAULT 0,
        otpis2 INTEGER DEFAULT 0,
        msg_id INTEGER,
        vip_waiter INTEGER,
        status TEXT DEFAULT 'active'
    )""", commit=True)
    
    # Таблица настроек
    db_query("""
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )""", commit=True)
    
    # Проверка наличия записи расписания
    existing_sched = db_query("SELECT value FROM settings WHERE key='schedule'", fetchone=True)
    if not existing_sched:
        db_query("INSERT INTO settings (key, value) VALUES ('schedule', 'Расписание на данный момент пусто.')", commit=True)
    
    logger.info("База данных успешно проинициализирована.")

# ==============================================================================
# БЛОК СОСТОЯНИЙ (FSM)
# ==============================================================================
class Form(StatesGroup):
    # Добавление клуба
    add_club_name = State()
    add_club_vld = State()
    
    # Расписание
    edit_schedule_text = State()
    
    # Создание матча
    m_t1 = State()
    m_t2 = State()
    m_time = State()
    
    # Изменение матча (поля)
    match_edit_select = State()
    match_edit_menu = State()
    match_edit_new_time = State()
    match_edit_new_t1 = State()
    match_edit_new_t2 = State()
    
    # Редактирование клуба
    edit_club_select = State()
    edit_club_choice = State()
    edit_club_new_name = State()
    edit_club_new_vld = State()
    edit_club_new_zam = State()
    
    # Табы
    tab_match_select = State()
    tab_photo1 = State()
    tab_photo2 = State()
    
    # Права
    give_admin_id = State()
    remove_admin_id = State()

# ==============================================================================
# КЛАВИАТУРЫ И ИНТЕРФЕЙС
# ==============================================================================
def get_main_keyboard(user_id):
    """Главное меню бота (Reply)"""
    builder = ReplyKeyboardBuilder()
    builder.button(text="📅 Расписание матчей")
    builder.button(text="📝 Дать отпись")
    builder.button(text="📸 Дать табы")
    
    # Проверка прав админа для отображения кнопки
    user_data = db_query("SELECT role FROM users WHERE user_id=?", (user_id,), fetchone=True)
    if user_id in SUPER_ADMINS or (user_data and user_data[0] == 'admin'):
        builder.button(text="⚙️ Админ панель")
    
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)

def get_admin_main_keyboard(user_id):
    """Главное меню админки (Inline)"""
    builder = InlineKeyboardBuilder()
    
    # Управление клубами
    builder.button(text="➕ Добавить клуб", callback_data="admin_add_club")
    builder.button(text="📝 Изменить клуб", callback_data="admin_edit_club")
    builder.button(text="❌ Удалить клуб", callback_data="admin_del_club")
    
    # Управление матчами
    builder.button(text="⚽ Создать матч", callback_data="admin_make_match")
    builder.button(text="🔄 Изменить матч", callback_data="admin_edit_match_list")
    builder.button(text="🗑 Удалить матч", callback_data="admin_del_match_list")
    
    # Настройки
    builder.button(text="📅 Изменить расписание", callback_data="admin_edit_sched")
    
    # Управление ролями (только для SuperAdmins)
    if user_id in SUPER_ADMINS:
        builder.button(text="👑 Дать админку", callback_data="admin_give_role")
        builder.button(text="🔌 Убрать админа", callback_data="admin_remove_role")
    
    builder.adjust(1)
    return builder.as_markup()

def get_back_to_admin_keyboard():
    """Кнопка возврата в админку"""
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 Назад в меню", callback_data="back_to_admin_root")
    return builder.as_markup()

# ==============================================================================
# БАЗОВЫЕ ОБРАБОТЧИКИ (START, BACK, CANCEL)
# ==============================================================================
@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    """Обработчик команды /start"""
    await state.clear()
    init_db()
    
    user_id = message.from_user.id
    # Регистрация пользователя
    db_query("INSERT OR IGNORE INTO users (user_id, role) VALUES (?, 'user')", (user_id,), commit=True)
    
    welcome_text = (
        "👋 **Добро пожаловать в систему Лиги!**\n\n"
        "Я — ваш автоматизированный помощник для управления клубами и матчами.\n\n"
        "Используйте кнопки меню для взаимодействия."
    )
    await message.answer(welcome_text, reply_markup=get_main_keyboard(user_id), parse_mode="Markdown")

@dp.callback_query(F.data == "back_to_admin_root")
async def back_to_admin_root(callback: CallbackQuery, state: FSMContext):
    """Возврат в корень админки"""
    await state.clear()
    await callback.message.edit_text(
        "⚙️ **Панель управления администратора**\n\nВыберите раздел для работы:",
        reply_markup=get_admin_main_keyboard(callback.from_user.id),
        parse_mode="Markdown"
    )
    await callback.answer()

@dp.message(F.text == "⚙️ Админ панель")
async def open_admin_panel(message: Message, state: FSMContext):
    """Открытие админ-панели через кнопку меню"""
    await state.clear()
    user_id = message.from_user.id
    user_data = db_query("SELECT role FROM users WHERE user_id=?", (user_id,), fetchone=True)
    
    if user_id in SUPER_ADMINS or (user_data and user_data[0] == 'admin'):
        await message.answer(
            "⚙️ **Панель управления администратора**\n\nВыберите раздел для работы:",
            reply_markup=get_admin_main_keyboard(user_id),
            parse_mode="Markdown"
        )
    else:
        await message.answer("🚫 У вас нет прав для доступа к админ-панели.")

# ==============================================================================
# УПРАВЛЕНИЕ КЛУБАМИ (ДОБАВЛЕНИЕ)
# ==============================================================================
@dp.callback_query(F.data == "admin_add_club")
async def add_club_init(callback: CallbackQuery, state: FSMContext):
    """Инициализация добавления клуба"""
    await state.clear()
    await callback.message.edit_text(
        "📝 **Добавление нового клуба**\n\nВведите название команды:",
        reply_markup=get_back_to_admin_keyboard(),
        parse_mode="Markdown"
    )
    await state.set_state(Form.add_club_name)
    await callback.answer()

@dp.message(Form.add_club_name)
async def add_club_process_name(message: Message, state: FSMContext):
    """Сохранение названия клуба во временное хранилище"""
    club_name = message.text.strip()
    if len(club_name) < 2:
        return await message.answer("❌ Название слишком короткое. Введите еще раз:")
    
    await state.update_data(temp_club_name=club_name)
    await message.answer(
        f"✅ Название команды: **{club_name}**\n\nТеперь отправьте **Telegram ID** владельца (ВЛД) клуба:",
        reply_markup=get_back_to_admin_keyboard(),
        parse_mode="Markdown"
    )
    await state.set_state(Form.add_club_vld)

@dp.message(Form.add_club_vld)
async def add_club_final(message: Message, state: FSMContext):
    """Сохранение клуба в базу данных"""
    if not message.text.isdigit():
        return await message.answer("❌ ID должен состоять только из цифр. Попробуйте снова:")
    
    vld_id = int(message.text)
    data = await state.get_data()
    club_name = data.get('temp_club_name')
    
    # Физическое сохранение в БД
    db_query("INSERT INTO clubs (name, vld_id) VALUES (?, ?)", (club_name, vld_id), commit=True)
    
    await message.answer(
        f"🎉 **Клуб успешно добавлен!**\n\n🏷 Название: {club_name}\n👤 ВЛД ID: `{vld_id}`",
        reply_markup=get_main_keyboard(message.from_user.id),
        parse_mode="Markdown"
    )
    await state.clear()

# ==============================================================================
# УПРАВЛЕНИЕ КЛУБАМИ (ИЗМЕНЕНИЕ)
# ==============================================================================
@dp.callback_query(F.data == "admin_edit_club")
async def edit_club_list(callback: CallbackQuery, state: FSMContext):
    """Выбор клуба для редактирования"""
    await state.clear()
    clubs = db_query("SELECT id, name FROM clubs")
    
    if not clubs:
        return await callback.message.edit_text(
            "❌ В базе данных нет ни одного клуба.",
            reply_markup=get_back_to_admin_keyboard()
        )
    
    builder = InlineKeyboardBuilder()
    for club in clubs:
        builder.button(text=f"⚙️ {club[1]}", callback_data=f"target_club_edit_{club[0]}")
    
    builder.button(text="🔙 Назад", callback_data="back_to_admin_root")
    builder.adjust(1)
    
    await callback.message.edit_text(
        "🛠 **Редактирование клуба**\n\nВыберите команду из списка:",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )
    await state.set_state(Form.edit_club_select)
    await callback.answer()

@dp.callback_query(F.data.startswith("target_club_edit_"), Form.edit_club_select)
async def edit_club_menu(callback: CallbackQuery, state: FSMContext):
    """Меню действий над выбранным клубом"""
    club_id = callback.data.split("_")[3]
    await state.update_data(active_club_id=club_id)
    
    club_data = db_query("SELECT name, vld_id, zams FROM clubs WHERE id=?", (club_id,), fetchone=True)
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🏷 Сменить название", callback_data="club_field_name")
    builder.button(text="👤 Сменить ВЛД (ID)", callback_data="club_field_vld")
    builder.button(text="➕ Добавить зама", callback_data="club_field_addzam")
    builder.button(text="🧹 Очистить замов", callback_data="club_field_clearzams")
    builder.button(text="🔙 К списку клубов", callback_data="admin_edit_club")
    builder.adjust(2)
    
    zams_text = club_data[2] if club_data[2] else "нет"
    await callback.message.edit_text(
        f"📊 **Клуб: {club_data[0]}**\n\n"
        f"🆔 ВЛД: `{club_data[1]}`\n"
        f"👥 Замы: `{zams_text}`\n\n"
        "Выберите поле для изменения:",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )
    await state.set_state(Form.edit_club_choice)
    await callback.answer()

@dp.callback_query(F.data.startswith("club_field_"), Form.edit_club_choice)
async def edit_club_field_router(callback: CallbackQuery, state: FSMContext):
    """Маршрутизатор полей клуба"""
    field = callback.data.split("_")[2]
    
    if field == "clearzams":
        data = await state.get_data()
        db_query("UPDATE clubs SET zams='' WHERE id=?", (data['active_club_id'],), commit=True)
        await callback.answer("✅ Замы очищены")
        return await edit_club_list(callback, state)
    
    await state.update_data(target_field=field)
    
    prompts = {
        "name": "Введите новое название клуба:",
        "vld": "Введите новый ID владельца клуба:",
        "addzam": "Введите ID нового заместителя:"
    }
    
    states = {
        "name": Form.edit_club_new_name,
        "vld": Form.edit_club_new_vld,
        "addzam": Form.edit_club_new_zam
    }
    
    await callback.message.edit_text(
        prompts[field],
        reply_markup=get_back_to_admin_keyboard()
    )
    await state.set_state(states[field])
    await callback.answer()

@dp.message(Form.edit_club_new_name)
async def save_club_new_name(message: Message, state: FSMContext):
    data = await state.get_data()
    db_query("UPDATE clubs SET name=? WHERE id=?", (message.text, data['active_club_id']), commit=True)
    await message.answer("✅ Название клуба успешно изменено!", reply_markup=get_main_keyboard(message.from_user.id))
    await state.clear()

@dp.message(Form.edit_club_new_vld)
async def save_club_new_vld(message: Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer("❌ Введите числовой ID:")
    data = await state.get_data()
    db_query("UPDATE clubs SET vld_id=? WHERE id=?", (int(message.text), data['active_club_id']), commit=True)
    await message.answer("✅ Владелец клуба изменен!", reply_markup=get_main_keyboard(message.from_user.id))
    await state.clear()

@dp.message(Form.edit_club_new_zam)
async def save_club_new_zam(message: Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer("❌ Введите числовой ID:")
    data = await state.get_data()
    
    current_zams = db_query("SELECT zams FROM clubs WHERE id=?", (data['active_club_id'],), fetchone=True)[0]
    updated_zams = f"{current_zams},{message.text}" if current_zams else message.text
    
    db_query("UPDATE clubs SET zams=? WHERE id=?", (updated_zams, data['active_club_id']), commit=True)
    await message.answer("✅ Заместитель добавлен!", reply_markup=get_main_keyboard(message.from_user.id))
    await state.clear()

# ==============================================================================
# УПРАВЛЕНИЕ МАТЧАМИ (СОЗДАНИЕ)
# ==============================================================================
@dp.callback_query(F.data == "admin_make_match")
async def make_match_t1_select(callback: CallbackQuery, state: FSMContext):
    """Создание матча - Выбор команды 1"""
    await state.clear()
    clubs = db_query("SELECT id, name FROM clubs")
    
    if len(clubs) < 2:
        return await callback.message.edit_text(
            "❌ Для создания матча нужно минимум 2 клуба в базе.",
            reply_markup=get_back_to_admin_keyboard()
        )
    
    builder = InlineKeyboardBuilder()
    for club in clubs:
        builder.button(text=club[1], callback_data=f"sel_m_t1_{club[0]}")
    
    builder.button(text="🔙 Назад", callback_data="back_to_admin_root")
    builder.adjust(2)
    
    await callback.message.edit_text(
        "⚽ **Создание матча**\n\nВыберите **первую** команду (хозяева):",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )
    await state.set_state(Form.m_t1)
    await callback.answer()

@dp.callback_query(F.data.startswith("sel_m_t1_"), Form.m_t1)
async def make_match_t2_select(callback: CallbackQuery, state: FSMContext):
    """Создание матча - Выбор команды 2"""
    t1_id = callback.data.split("_")[3]
    await state.update_data(match_t1_id=t1_id)
    
    clubs = db_query("SELECT id, name FROM clubs WHERE id != ?", (t1_id,))
    
    builder = InlineKeyboardBuilder()
    for club in clubs:
        builder.button(text=club[1], callback_data=f"sel_m_t2_{club[0]}")
    
    builder.button(text="🔙 Отмена", callback_data="admin_make_match")
    builder.adjust(2)
    
    await callback.message.edit_text(
        "⚽ **Создание матча**\n\nВыберите **вторую** команду (гости):",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )
    await state.set_state(Form.m_t2)
    await callback.answer()

@dp.callback_query(F.data.startswith("sel_m_t2_"), Form.m_t2)
async def make_match_time_input(callback: CallbackQuery, state: FSMContext):
    """Ввод времени для матча"""
    t2_id = callback.data.split("_")[3]
    await state.update_data(match_t2_id=t2_id)
    
    await callback.message.edit_text(
        "⏰ **Введите время матча**\n\nПример: `19:00` или `Сегодня 21:30`",
        reply_markup=get_back_to_admin_keyboard(),
        parse_mode="Markdown"
    )
    await state.set_state(Form.m_time)
    await callback.answer()

@dp.message(Form.m_time)
async def make_match_final(message: Message, state: FSMContext):
    """Завершение создания матча и публикация"""
    match_time = message.text.strip()
    data = await state.get_data()
    
    t1_id = data['match_t1_id']
    t2_id = data['match_t2_id']
    
    n1 = db_query("SELECT name FROM clubs WHERE id=?", (t1_id,), fetchone=True)[0]
    n2 = db_query("SELECT name FROM clubs WHERE id=?", (t2_id,), fetchone=True)[0]
    
    post_text = (
        f"🏟 **ЗАПЛАНИРОВАН НОВЫЙ МАТЧ!**\n\n"
        f"⚽ **{n1}** vs **{n2}**\n"
        f"📅 Время начала: `{match_time}`\n\n"
        f"📊 Статус отписи:\n"
        f"1️⃣ {n1} — ❌\n"
        f"2️⃣ {n2} — ❌\n\n"
        f"Отписаться на матч: {BOT_USERNAME}"
    )
    
    try:
        sent_message = await bot.send_message(CHANNEL_ID, post_text, parse_mode="Markdown")
        db_query(
            "INSERT INTO matches (t1_id, t2_id, time, msg_id) VALUES (?, ?, ?, ?)",
            (t1_id, t2_id, match_time, sent_message.message_id),
            commit=True
        )
        await message.answer("✅ Матч успешно создан и отправлен в канал!", reply_markup=get_main_keyboard(message.from_user.id))
    except Exception as e:
        await message.answer(f"❌ Ошибка публикации: {e}\n\nМатч не сохранен.")
    
    await state.clear()

# ==============================================================================
# УПРАВЛЕНИЕ МАТЧАМИ (ИЗМЕНЕНИЕ - ПОЛНЫЙ ФУНКЦИОНАЛ)
# ==============================================================================
@dp.callback_query(F.data == "admin_edit_match_list")
async def edit_match_list(callback: CallbackQuery, state: FSMContext):
    """Выбор существующего матча для редактирования"""
    await state.clear()
    matches = db_query("SELECT id, t1_id, t2_id, time FROM matches WHERE status='active' ORDER BY id DESC LIMIT 15")
    
    if not matches:
        return await callback.message.edit_text("❌ Активных матчей не найдено.", reply_markup=get_back_to_admin_keyboard())
    
    builder = InlineKeyboardBuilder()
    for m in matches:
        n1 = db_query("SELECT name FROM clubs WHERE id=?", (m[1],), fetchone=True)[0]
        n2 = db_query("SELECT name FROM clubs WHERE id=?", (m[2],), fetchone=True)[0]
        builder.button(text=f"⚙️ {n1} - {n2} ({m[3]})", callback_data=f"edit_match_target_{m[0]}")
    
    builder.button(text="🔙 Назад", callback_data="back_to_admin_root")
    builder.adjust(1)
    
    await callback.message.edit_text(
        "📝 **Редактирование матча**\n\nВыберите матч из списка:",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )
    await state.set_state(Form.match_edit_select)
    await callback.answer()

@dp.callback_query(F.data.startswith("edit_match_target_"), Form.match_edit_select)
async def edit_match_menu(callback: CallbackQuery, state: FSMContext):
    """Меню изменения конкретных полей матча"""
    match_id = callback.data.split("_")[3]
    await state.update_data(active_match_id=match_id)
    
    m_data = db_query("SELECT t1_id, t2_id, time FROM matches WHERE id=?", (match_id,), fetchone=True)
    n1 = db_query("SELECT name FROM clubs WHERE id=?", (m_data[0],), fetchone=True)[0]
    n2 = db_query("SELECT name FROM clubs WHERE id=?", (m_data[1],), fetchone=True)[0]
    
    builder = InlineKeyboardBuilder()
    builder.button(text="⏰ Изменить время", callback_data="edit_m_field_time")
    builder.button(text="👕 Сменить Команду 1", callback_data="edit_m_field_t1")
    builder.button(text="👕 Сменить Команду 2", callback_data="edit_m_field_t2")
    builder.button(text="🔙 К списку матчей", callback_data="admin_edit_match_list")
    builder.adjust(1)
    
    await callback.message.edit_text(
        f"🔄 **Матч #{match_id}**\n\n"
        f"⚔️ {n1} vs {n2}\n"
        f"📅 Время: `{m_data[2]}`\n\n"
        "Выберите поле для изменения:",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )
    await state.set_state(Form.match_edit_menu)
    await callback.answer()

@dp.callback_query(F.data == "edit_m_field_time", Form.match_edit_menu)
async def edit_match_time_init(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("⏰ Введите новое время для матча:", reply_markup=get_back_to_admin_keyboard())
    await state.set_state(Form.match_edit_new_time)
    await callback.answer()

@dp.message(Form.match_edit_new_time)
async def edit_match_time_save(message: Message, state: FSMContext):
    data = await state.get_data()
    db_query("UPDATE matches SET time=? WHERE id=?", (message.text, data['active_match_id']), commit=True)
    await message.answer("✅ Время матча обновлено!", reply_markup=get_main_keyboard(message.from_user.id))
    await state.clear()

@dp.callback_query(F.data == "edit_m_field_t1", Form.match_edit_menu)
async def edit_match_t1_init(callback: CallbackQuery, state: FSMContext):
    clubs = db_query("SELECT id, name FROM clubs")
    builder = InlineKeyboardBuilder()
    for c in clubs:
        builder.button(text=c[1], callback_data=f"save_m_new_t1_{c[0]}")
    builder.adjust(2)
    await callback.message.edit_text("Выберите новую Команду 1:", reply_markup=builder.as_markup())
    await state.set_state(Form.match_edit_new_t1)
    await callback.answer()

@dp.callback_query(F.data.startswith("save_m_new_t1_"), Form.match_edit_new_t1)
async def edit_match_t1_save(callback: CallbackQuery, state: FSMContext):
    new_id = callback.data.split("_")[4]
    data = await state.get_data()
    db_query("UPDATE matches SET t1_id=? WHERE id=?", (new_id, data['active_match_id']), commit=True)
    await callback.message.answer("✅ Команда 1 в матче изменена!")
    await state.clear()
    await callback.answer()

@dp.callback_query(F.data == "edit_m_field_t2", Form.match_edit_menu)
async def edit_match_t2_init(callback: CallbackQuery, state: FSMContext):
    clubs = db_query("SELECT id, name FROM clubs")
    builder = InlineKeyboardBuilder()
    for c in clubs:
        builder.button(text=c[1], callback_data=f"save_m_new_t2_{c[0]}")
    builder.adjust(2)
    await callback.message.edit_text("Выберите новую Команду 2:", reply_markup=builder.as_markup())
    await state.set_state(Form.match_edit_new_t2)
    await callback.answer()

@dp.callback_query(F.data.startswith("save_m_new_t2_"), Form.match_edit_new_t2)
async def edit_match_t2_save(callback: CallbackQuery, state: FSMContext):
    new_id = callback.data.split("_")[4]
    data = await state.get_data()
    db_query("UPDATE matches SET t2_id=? WHERE id=?", (new_id, data['active_match_id']), commit=True)
    await callback.message.answer("✅ Команда 2 в матче изменена!")
    await state.clear()
    await callback.answer()

# ==============================================================================
# УДАЛЕНИЕ КЛУБОВ И МАТЧЕЙ
# ==============================================================================
@dp.callback_query(F.data == "admin_del_club")
async def delete_club_select(callback: CallbackQuery):
    clubs = db_query("SELECT id, name FROM clubs")
    builder = InlineKeyboardBuilder()
    for c in clubs:
        builder.button(text=f"🗑 {c[1]}", callback_data=f"exec_del_club_{c[0]}")
    builder.button(text="🔙 Назад", callback_data="back_to_admin_root")
    builder.adjust(1)
    await callback.message.edit_text("Выберите клуб для БЕЗВОЗВРАТНОГО удаления:", reply_markup=builder.as_markup())
    await callback.answer()

@dp.callback_query(F.data.startswith("exec_del_club_"))
async def delete_club_execute(callback: CallbackQuery):
    club_id = callback.data.split("_")[3]
    db_query("DELETE FROM clubs WHERE id=?", (club_id,), commit=True)
    await callback.answer("Клуб удален")
    await delete_club_select(callback)

@dp.callback_query(F.data == "admin_del_match_list")
async def delete_match_select(callback: CallbackQuery):
    matches = db_query("SELECT id, t1_id, t2_id, time FROM matches ORDER BY id DESC LIMIT 10")
    builder = InlineKeyboardBuilder()
    for m in matches:
        n1 = db_query("SELECT name FROM clubs WHERE id=?", (m[1],), fetchone=True)[0]
        n2 = db_query("SELECT name FROM clubs WHERE id=?", (m[2],), fetchone=True)[0]
        builder.button(text=f"🗑 {n1}-{n2} ({m[3]})", callback_data=f"exec_del_match_{m[0]}")
    builder.button(text="🔙 Назад", callback_data="back_to_admin_root")
    builder.adjust(1)
    await callback.message.edit_text("Выберите матч для удаления:", reply_markup=builder.as_markup())
    await callback.answer()

@dp.callback_query(F.data.startswith("exec_del_match_"))
async def delete_match_execute(callback: CallbackQuery):
    mid = callback.data.split("_")[3]
    db_query("DELETE FROM matches WHERE id=?", (mid,), commit=True)
    await callback.answer("Матч удален")
    await delete_match_select(callback)

# ==============================================================================
# РАСПИСАНИЕ И РОЛИ
# ==============================================================================
@dp.message(F.text == "📅 Расписание матчей")
async def show_schedule_user(message: Message):
    data = db_query("SELECT value FROM settings WHERE key='schedule'", fetchone=True)
    await message.answer(f"📅 **Актуальное расписание:**\n\n{data[0]}", parse_mode="Markdown")

@dp.callback_query(F.data == "admin_edit_sched")
async def edit_schedule_init(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("📅 Отправьте новый текст расписания:", reply_markup=get_back_to_admin_keyboard())
    await state.set_state(Form.edit_schedule_text)
    await callback.answer()

@dp.message(Form.edit_schedule_text)
async def edit_schedule_save(message: Message, state: FSMContext):
    db_query("UPDATE settings SET value=? WHERE key='schedule'", (message.text, ), commit=True)
    await message.answer("✅ Расписание обновлено!", reply_markup=get_main_keyboard(message.from_user.id))
    await state.clear()

@dp.callback_query(F.data == "admin_give_role")
async def give_role_init(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("👑 Введите Telegram ID для назначения админом:", reply_markup=get_back_to_admin_keyboard())
    await state.set_state(Form.give_admin_id)

@dp.message(Form.give_admin_id)
async def give_role_save(message: Message, state: FSMContext):
    if not message.text.isdigit(): return await message.answer("Числовой ID!")
    db_query("INSERT OR REPLACE INTO users (user_id, role) VALUES (?, 'admin')", (int(message.text),), commit=True)
    await message.answer("✅ Админ назначен!")
    await state.clear()

@dp.callback_query(F.data == "admin_remove_role")
async def remove_role_init(callback: CallbackQuery, state: FSMContext):
    admins = db_query("SELECT user_id FROM users WHERE role='admin'")
    txt = "Текущие админы:\n" + "\n".join([f"`{a[0]}`" for a in admins])
    await callback.message.edit_text(f"{txt}\n\nВведите ID для удаления прав:", reply_markup=get_back_to_admin_keyboard())
    await state.set_state(Form.remove_admin_id)

@dp.message(Form.remove_admin_id)
async def remove_role_save(message: Message, state: FSMContext):
    db_query("UPDATE users SET role='user' WHERE user_id=?", (int(message.text),), commit=True)
    await message.answer("✅ Права отозваны!")
    await state.clear()

# ==============================================================================
# ОТПИСЬ И ТАБЫ
# ==============================================================================
@dp.message(F.text == "📝 Дать отпись")
async def process_otpis_list(message: Message):
    matches = db_query("SELECT id, t1_id, t2_id FROM matches WHERE otpis1=0 OR otpis2=0")
    if not matches: return await message.answer("❌ Нет активных отписей.")
    
    builder = InlineKeyboardBuilder()
    for m in matches:
        n1 = db_query("SELECT name FROM clubs WHERE id=?", (m[1],), fetchone=True)[0]
        n2 = db_query("SELECT name FROM clubs WHERE id=?", (m[2],), fetchone=True)[0]
        builder.button(text=f"{n1} - {n2}", callback_data=f"otpis_exec_{m[0]}")
    builder.adjust(1)
    await message.answer("Выберите матч для отписи за ваш клуб:", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("otpis_exec_"))
async def process_otpis_action(callback: CallbackQuery):
    mid = callback.data.split("_")[2]
    m = db_query("SELECT * FROM matches WHERE id=?", (mid,), fetchone=True)
    uid = str(callback.from_user.id)
    
    c1 = db_query("SELECT vld_id, zams, name FROM clubs WHERE id=?", (m[1],), fetchone=True)
    c2 = db_query("SELECT vld_id, zams, name FROM clubs WHERE id=?", (m[2],), fetchone=True)
    
    target = None
    if uid == str(c1[0]) or uid in str(c1[1]).split(","): target = "otpis1"
    elif uid == str(c2[0]) or uid in str(c2[1]).split(","): target = "otpis2"
    
    if not target: return await callback.answer("🚫 У вас нет прав!", show_alert=True)
    
    db_query(f"UPDATE matches SET {target}=1 WHERE id=?", (mid,), commit=True)
    await callback.answer("✅ Отпись принята!")
    
    m_new = db_query("SELECT * FROM matches WHERE id=?", (mid,), fetchone=True)
    s1 = "✅" if m_new[4] else "❌"
    s2 = "✅" if m_new[5] else "❌"
    
    upd_text = f"🏟 **ОБНОВЛЕНИЕ МАТЧА**\n\n⚽ {c1[2]} vs {c2[2]}\n📅 Время: `{m_new[3]}`\n\nСтатус отписи:\n1️⃣ {c1[2]} — {s1}\n2️⃣ {c2[2]} — {s2}"
    try: await bot.edit_message_text(upd_text, CHANNEL_ID, m_new[6], parse_mode="Markdown")
    except: pass
    
    if m_new[4] and m_new[5]:
        vld = random.choice([c1[0], c2[0]])
        db_query("UPDATE matches SET vip_waiter=? WHERE id=?", (vld, mid), commit=True)
        await bot.send_message(vld, "🎲 **Жребий выпал вам!**\nВы создаете VIP. Пришлите данные в формате `вип:Текст`.")

@dp.message(F.text == "📸 Дать табы")
async def process_tabs_list(message: Message, state: FSMContext):
    matches = db_query("SELECT id, t1_id, t2_id FROM matches WHERE otpis1=1 AND otpis2=1")
    if not matches: return await message.answer("❌ Нет матчей для сдачи табов.")
    
    builder = InlineKeyboardBuilder()
    for m in matches:
        n1 = db_query("SELECT name FROM clubs WHERE id=?", (m[1],), fetchone=True)[0]
        n2 = db_query("SELECT name FROM clubs WHERE id=?", (m[2],), fetchone=True)[0]
        builder.button(text=f"{n1} - {n2}", callback_data=f"tabs_for_{m[0]}")
    builder.adjust(1)
    await message.answer("Выберите ваш матч:", reply_markup=builder.as_markup())
    await state.set_state(Form.tab_match_select)

@dp.callback_query(F.data.startswith("tabs_for_"), Form.tab_match_select)
async def process_tabs_p1(callback: CallbackQuery, state: FSMContext):
    mid = callback.data.split("_")[2]
    m = db_query("SELECT t1_id, t2_id FROM matches WHERE id=?", (mid,), fetchone=True)
    uid = str(callback.from_user.id)
    
    c1 = db_query("SELECT vld_id, zams, name FROM clubs WHERE id=?", (m[0],), fetchone=True)
    c2 = db_query("SELECT vld_id, zams, name FROM clubs WHERE id=?", (m[1],), fetchone=True)
    
    club_name = None
    if uid == str(c1[0]) or uid in str(c1[1]).split(","): club_name = c1[2]
    elif uid == str(c2[0]) or uid in str(c2[1]).split(","): club_name = c2[2]
    
    if not club_name: return await callback.answer("🚫 Нет прав!", show_alert=True)
    
    await state.update_data(active_club=club_name)
    await callback.message.answer(f"📤 Команда: {club_name}. Пришлите скриншот 1 тайма:")
    await state.set_state(Form.tab_photo1)
    await callback.answer()

@dp.message(Form.tab_photo1, F.photo)
async def process_tabs_p2(message: Message, state: FSMContext):
    await state.update_data(photo1=message.photo[-1].file_id)
    await message.answer("Пришлите скриншот 2 тайма:")
    await state.set_state(Form.tab_photo2)

@dp.message(Form.tab_photo2, F.photo)
async def process_tabs_final(message: Message, state: FSMContext):
    data = await state.get_data()
    p2 = message.photo[-1].file_id
    
    for adm in SUPER_ADMINS:
        await bot.send_message(adm, f"📸 **ТАБЫ** от {data['active_club']}")
        await bot.send_photo(adm, data['photo1'], caption="Тайм 1")
        await bot.send_photo(adm, p2, caption="Тайм 2")
    
    await message.answer("✅ Табы отправлены администрации!", reply_markup=get_main_keyboard(message.from_user.id))
    await state.clear()

@dp.message(F.text.startswith("вип:"))
async def process_vip_send(message: Message):
    user_id = message.from_user.id
    m = db_query("SELECT t1_id, t2_id FROM matches WHERE vip_waiter=? ORDER BY id DESC LIMIT 1", (user_id,), fetchone=True)
    if m:
        c1_vld = db_query("SELECT vld_id FROM clubs WHERE id=?", (m[0],), fetchone=True)[0]
        c2_vld = db_query("SELECT vld_id FROM clubs WHERE id=?", (m[1],), fetchone=True)[0]
        target = c1_vld if user_id == c2_vld else c2_vld
        await bot.send_message(target, f"📩 **ДАННЫЕ VIP:**\n\n`{message.text}`", parse_mode="Markdown")
        await message.answer("✅ Данные переданы сопернику.")

# ==============================================================================
# ЗАПУСК БОТА
# ==============================================================================
async def main():
    init_db()
    await bot.set_my_commands([BotCommand(command="start", description="Перезапуск бота")], scope=BotCommandScopeDefault())
    logger.info("Бот запущен и готов к работе.")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен.")
