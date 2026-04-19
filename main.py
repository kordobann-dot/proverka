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
# БЛОК КОНФИГУРАЦИИ И НАСТРОЕК
# ==============================================================================
TOKEN = "8633419537:AAF6r1H1YtfI2whTHVdKzF2JVQnxgu9XfU4"
CHANNEL_ID = "@pistonCUPsls"
# Основные администраторы с полным доступом
SUPER_ADMINS = [5845609895, 6740071266]
BOT_USERNAME = "@TernatLeague_Bot"

# Настройка подробного логирования для мониторинга в Railway
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] - %(name)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Инициализация объектов бота и диспетчера
bot = Bot(token=TOKEN)
dp = Dispatcher()

# ==============================================================================
# ГЛОБАЛЬНЫЕ СОСТОЯНИЯ (FSM) - МАКСИМАЛЬНО ДЕТАЛЬНО
# ==============================================================================
class Form(StatesGroup):
    """Класс состояний для управления всеми процессами бота"""
    
    # Состояния для добавления нового клуба
    adding_club_name = State()
    adding_club_vld = State()
    
    # Состояния для управления расписанием
    editing_schedule_text = State()
    
    # Состояния для создания матча (Исправлено!)
    match_creating_step_1 = State() # Выбор команды 1
    match_creating_step_2 = State() # Выбор команды 2
    match_creating_step_3 = State() # Ввод времени
    
    # Состояния для глубокого редактирования матча
    match_edit_select_id = State()
    match_edit_main_menu = State()
    match_edit_update_time = State()
    match_edit_update_t1 = State()
    match_edit_update_t2 = State()
    
    # Состояния для редактирования данных о клубе
    club_edit_select_id = State()
    club_edit_main_menu = State()
    club_edit_update_name = State()
    club_edit_update_vld = State()
    club_edit_update_zam = State()
    
    # Состояния для процесса сдачи табов (скриншотов)
    tabs_selecting_match = State()
    tabs_upload_photo_1 = State()
    tabs_upload_photo_2 = State()
    
    # Состояния для управления правами доступа (Админка)
    admin_grant_id = State()
    admin_revoke_id = State()

# ==============================================================================
# БЛОК РАБОТЫ С БАЗОЙ ДАННЫХ (SQLITE3)
# ==============================================================================
def execute_db_query(query, params=(), fetchone=False, commit=False):
    """
    Универсальная функция для выполнения запросов к БД.
    Включает обработку исключений и логирование ошибок.
    """
    db_name = 'league_data.db'
    # Увеличен timeout для стабильной работы на облачных серверах
    conn = sqlite3.connect(db_name, timeout=60)
    cursor = conn.cursor()
    result = None
    
    try:
        cursor.execute(query, params)
        if commit:
            conn.commit()
            logger.info(f"Запрос выполнен успешно (COMMIT): {query[:50]}...")
        
        if fetchone:
            result = cursor.fetchone()
        else:
            result = cursor.fetchall()
            
    except Exception as error:
        logger.error(f"Критическая ошибка при работе с SQLite: {error}")
        logger.error(f"Проблемный запрос: {query}")
    finally:
        conn.close()
    return result

def initialize_database_structure():
    """Создание всех необходимых таблиц при старте бота"""
    logger.info("Проверка и инициализация структуры базы данных...")
    
    # Таблица для хранения пользователей и их ролей
    execute_db_query("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        role TEXT DEFAULT 'user'
    )""", commit=True)
    
    # Таблица клубов (команд)
    execute_db_query("""
    CREATE TABLE IF NOT EXISTS clubs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        vld_id INTEGER NOT NULL,
        zams TEXT DEFAULT ''
    )""", commit=True)
    
    # Таблица матчей и их состояний
    execute_db_query("""
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
    
    # Таблица общих настроек (например, текст расписания)
    execute_db_query("""
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )""", commit=True)
    
    # Проверка начальных настроек расписания
    check_sched = execute_db_query("SELECT value FROM settings WHERE key='schedule'", fetchone=True)
    if not check_sched:
        execute_db_query("INSERT INTO settings (key, value) VALUES ('schedule', 'На текущий момент расписание отсутствует.')", commit=True)
        logger.info("Создана дефолтная запись расписания.")

# ==============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ (КЛАВИАТУРЫ И ПРОВЕРКИ)
# ==============================================================================
async def check_is_admin(user_id: int):
    """Проверка наличия прав администратора у пользователя"""
    if user_id in SUPER_ADMINS:
        return True
    data = execute_db_query("SELECT role FROM users WHERE user_id=?", (user_id,), fetchone=True)
    return data and data[0] == 'admin'

def ui_main_menu_keyboard(user_id: int):
    """Формирование главного меню бота (Reply кнопки)"""
    builder = ReplyKeyboardBuilder()
    builder.button(text="📅 Расписание матчей")
    builder.button(text="📝 Дать отпись")
    builder.button(text="📸 Дать табы")
    
    # Динамическая кнопка админки
    user_role_data = execute_db_query("SELECT role FROM users WHERE user_id=?", (user_id,), fetchone=True)
    if user_id in SUPER_ADMINS or (user_role_data and user_role_data[0] == 'admin'):
        builder.button(text="⚙️ Админ панель")
    
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)

def ui_admin_root_keyboard(user_id: int):
    """Главная панель администратора (Inline кнопки)"""
    builder = InlineKeyboardBuilder()
    
    # Секция управления клубами
    builder.button(text="➕ Создать клуб", callback_data="btn_adm_club_add")
    builder.button(text="📝 Изменить данные клуба", callback_data="btn_adm_club_edit_list")
    builder.button(text="❌ Удалить клуб", callback_data="btn_adm_club_del_list")
    
    # Секция управления матчами
    builder.button(text="⚽ Назначить матч", callback_data="btn_adm_match_create_start")
    builder.button(text="🔄 Редактировать матч", callback_data="btn_adm_match_edit_list")
    builder.button(text="🗑 Удалить матч", callback_data="btn_adm_match_del_list")
    
    # Глобальные настройки
    builder.button(text="📅 Текст расписания", callback_data="btn_adm_sched_edit")
    
    # Секция супер-админа
    if user_id in SUPER_ADMINS:
        builder.button(text="👑 Назначить админа", callback_data="btn_adm_role_give")
        builder.button(text="🔌 Снять админа", callback_data="btn_adm_role_revoke")
    
    builder.adjust(1)
    return builder.as_markup()

def ui_back_to_admin_button():
    """Универсальная кнопка возврата в корень админки"""
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 Вернуться в меню", callback_data="nav_to_admin_main")
    return builder.as_markup()

# ==============================================================================
# ОБРАБОТЧИКИ БАЗОВЫХ КОМАНД (START, CANCEL)
# ==============================================================================
@dp.message(Command("start"))
async def handler_command_start(message: Message, state: FSMContext):
    """Обработка команды /start и регистрация пользователя"""
    await state.clear()
    uid = message.from_user.id
    
    # Регистрация пользователя в БД, если его нет
    execute_db_query("INSERT OR IGNORE INTO users (user_id, role) VALUES (?, 'user')", (uid,), commit=True)
    
    welcome_msg = (
        "👋 **Приветствуем в системе управления лигой!**\n\n"
        "Этот бот поможет вам следить за расписанием, сдавать табы и управлять матчами.\n\n"
        "Используйте кнопки меню ниже:"
    )
    await message.answer(welcome_msg, reply_markup=ui_main_menu_keyboard(uid), parse_mode="Markdown")
    logger.info(f"Пользователь {uid} нажал старт.")

@dp.callback_query(F.data == "nav_to_admin_main")
async def handler_nav_admin_main(callback: CallbackQuery, state: FSMContext):
    """Возврат в главное меню админки из любого состояния"""
    await state.clear()
    if not await check_is_admin(callback.from_user.id):
        return await callback.answer("🚫 У вас нет прав доступа!", show_alert=True)
        
    await callback.message.edit_text(
        "⚙️ **Панель управления администратора**\nВыберите нужный раздел:",
        reply_markup=ui_admin_root_keyboard(callback.from_user.id),
        parse_mode="Markdown"
    )
    await callback.answer()

@dp.message(F.text == "⚙️ Админ панель")
async def handler_open_admin_panel(message: Message, state: FSMContext):
    """Открытие админки через кнопку Reply меню"""
    await state.clear()
    if not await check_is_admin(message.from_user.id):
        return await message.answer("🚫 У вас нет доступа к этому разделу.")
        
    await message.answer(
        "⚙️ **Панель управления администратора**\nВыберите нужный раздел:",
        reply_markup=ui_admin_root_keyboard(message.from_user.id),
        parse_mode="Markdown"
    )

# ==============================================================================
# БЛОК ДОБАВЛЕНИЯ КЛУБА
# ==============================================================================
@dp.callback_query(F.data == "btn_adm_club_add")
async def handler_club_add_step_1(callback: CallbackQuery, state: FSMContext):
    """Запрос названия нового клуба"""
    await state.set_state(Form.adding_club_name)
    await callback.message.edit_text(
        "📝 **Добавление нового клуба**\n\nВведите полное название команды:",
        reply_markup=ui_back_to_admin_button(),
        parse_mode="Markdown"
    )
    await callback.answer()

@dp.message(Form.adding_club_name)
async def handler_club_add_step_2(message: Message, state: FSMContext):
    """Сохранение названия и запрос ID владельца"""
    club_name = message.text.strip()
    if len(club_name) < 2:
        return await message.answer("❌ Название слишком короткое. Введите еще раз:")
        
    await state.update_data(temp_club_name=club_name)
    await state.set_state(Form.adding_club_vld)
    await message.answer(
        f"✅ Название: **{club_name}**\n\nТеперь введите Telegram ID владельца клуба (ВЛД):",
        reply_markup=ui_back_to_admin_button(),
        parse_mode="Markdown"
    )

@dp.message(Form.adding_club_vld)
async def handler_club_add_step_3(message: Message, state: FSMContext):
    """Финальное сохранение клуба в базу данных"""
    if not message.text.isdigit():
        return await message.answer("❌ ID должен содержать только цифры. Повторите ввод:")
        
    vld_id = int(message.text)
    data = await state.get_data()
    c_name = data.get('temp_club_name')
    
    execute_db_query("INSERT INTO clubs (name, vld_id) VALUES (?, ?)", (c_name, vld_id), commit=True)
    
    await message.answer(
        f"🎉 **Клуб успешно зарегистрирован!**\n\n🏷 Имя: {c_name}\n👤 ВЛД ID: `{vld_id}`",
        reply_markup=ui_main_menu_keyboard(message.from_user.id),
        parse_mode="Markdown"
    )
    await state.clear()
    logger.info(f"Создан новый клуб: {c_name}")

# ==============================================================================
# БЛОК РЕДАКТИРОВАНИЯ КЛУБА (РАСШИРЕННЫЙ)
# ==============================================================================
@dp.callback_query(F.data == "btn_adm_club_edit_list")
async def handler_club_edit_list(callback: CallbackQuery, state: FSMContext):
    """Отображение списка всех клубов для редактирования"""
    clubs = execute_db_query("SELECT id, name FROM clubs")
    if not clubs:
        return await callback.message.edit_text("❌ В базе данных пока нет клубов.", reply_markup=ui_back_to_admin_button())
        
    builder = InlineKeyboardBuilder()
    for c in clubs:
        builder.button(text=f"🛠 {c[1]}", callback_data=f"club_edit_id_{c[0]}")
    
    builder.button(text="🔙 Назад", callback_data="nav_to_admin_main")
    builder.adjust(1)
    
    await state.set_state(Form.club_edit_select_id)
    await callback.message.edit_text("Выберите клуб для изменения параметров:", reply_markup=builder.as_markup())
    await callback.answer()

@dp.callback_query(F.data.startswith("club_edit_id_"), Form.club_edit_select_id)
async def handler_club_edit_menu(callback: CallbackQuery, state: FSMContext):
    """Меню действий над выбранным клубом"""
    club_id = callback.data.split("_")[3]
    await state.update_data(current_edit_club_id=club_id)
    
    club_info = execute_db_query("SELECT name, vld_id, zams FROM clubs WHERE id=?", (club_id,), fetchone=True)
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🏷 Изменить имя", callback_data="field_club_name")
    builder.button(text="👤 Изменить ВЛД", callback_data="field_club_vld")
    builder.button(text="➕ Добавить зама", callback_data="field_club_addzam")
    builder.button(text="🧹 Очистить замов", callback_data="field_club_clear")
    builder.button(text="🔙 К списку", callback_data="btn_adm_club_edit_list")
    builder.adjust(2)
    
    zams_display = club_info[2] if club_info[2] else "Список пуст"
    await callback.message.edit_text(
        f"📊 **Карточка клуба: {club_info[0]}**\n\n"
        f"🆔 ВЛД ID: `{club_info[1]}`\n"
        f"👥 Заместители: `{zams_display}`\n\n"
        "Что именно вы хотите изменить?",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )
    await state.set_state(Form.club_edit_main_menu)
    await callback.answer()

@dp.callback_query(F.data == "field_club_name", Form.club_edit_main_menu)
async def handler_club_edit_name_init(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Введите новое название для клуба:", reply_markup=ui_back_to_admin_button())
    await state.set_state(Form.club_edit_update_name)

@dp.message(Form.club_edit_update_name)
async def handler_club_edit_name_save(message: Message, state: FSMContext):
    data = await state.get_data()
    cid = data.get('current_edit_club_id')
    execute_db_query("UPDATE clubs SET name=? WHERE id=?", (message.text, cid), commit=True)
    await message.answer(f"✅ Новое название **{message.text}** сохранено!", reply_markup=ui_main_menu_keyboard(message.from_user.id))
    await state.clear()

@dp.callback_query(F.data == "field_club_vld", Form.club_edit_main_menu)
async def handler_club_edit_vld_init(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Введите новый ID владельца (только цифры):", reply_markup=ui_back_to_admin_button())
    await state.set_state(Form.club_edit_update_vld)

@dp.message(Form.club_edit_update_vld)
async def handler_club_edit_vld_save(message: Message, state: FSMContext):
    if not message.text.isdigit(): return await message.answer("❌ Ошибка: Введите числовой ID.")
    data = await state.get_data()
    cid = data.get('current_edit_club_id')
    execute_db_query("UPDATE clubs SET vld_id=? WHERE id=?", (int(message.text), cid), commit=True)
    await message.answer("✅ Новый владелец успешно назначен!", reply_markup=ui_main_menu_keyboard(message.from_user.id))
    await state.clear()

@dp.callback_query(F.data == "field_club_addzam", Form.club_edit_main_menu)
async def handler_club_edit_zam_init(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Введите ID заместителя для добавления в список:", reply_markup=ui_back_to_admin_button())
    await state.set_state(Form.club_edit_update_zam)

@dp.message(Form.club_edit_update_zam)
async def handler_club_edit_zam_save(message: Message, state: FSMContext):
    if not message.text.isdigit(): return await message.answer("❌ Ошибка: Введите числовой ID.")
    data = await state.get_data()
    cid = data.get('current_edit_club_id')
    
    current_zams_data = execute_db_query("SELECT zams FROM clubs WHERE id=?", (cid,), fetchone=True)[0]
    new_zams_string = f"{current_zams_data},{message.text}" if current_zams_data else message.text
    
    execute_db_query("UPDATE clubs SET zams=? WHERE id=?", (new_zams_string, cid), commit=True)
    await message.answer("✅ Заместитель добавлен в список!", reply_markup=ui_main_menu_keyboard(message.from_user.id))
    await state.clear()

@dp.callback_query(F.data == "field_club_clear", Form.club_edit_main_menu)
async def handler_club_edit_zam_clear(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    cid = data.get('current_edit_club_id')
    execute_db_query("UPDATE clubs SET zams='' WHERE id=?", (cid,), commit=True)
    await callback.answer("🧹 Список заместителей очищен!", show_alert=True)
    await handler_club_edit_list(callback, state)

# ==============================================================================
# БЛОК УДАЛЕНИЯ КЛУБА
# ==============================================================================
@dp.callback_query(F.data == "btn_adm_club_del_list")
async def handler_club_delete_list(callback: CallbackQuery):
    """Выбор клуба для безвозвратного удаления"""
    clubs = execute_db_query("SELECT id, name FROM clubs")
    if not clubs:
        return await callback.message.edit_text("❌ База пуста, удалять нечего.", reply_markup=ui_back_to_admin_button())
        
    builder = InlineKeyboardBuilder()
    for c in clubs:
        builder.button(text=f"🗑 Удалить {c[1]}", callback_data=f"club_delete_exec_{c[0]}")
    
    builder.button(text="🔙 Назад", callback_data="nav_to_admin_main")
    builder.adjust(1)
    await callback.message.edit_text("⚠️ **ВНИМАНИЕ!**\nВыбранный клуб будет удален навсегда:", reply_markup=builder.as_markup(), parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(F.data.startswith("club_delete_exec_"))
async def handler_club_delete_execute(callback: CallbackQuery):
    cid = callback.data.split("_")[3]
    execute_db_query("DELETE FROM clubs WHERE id=?", (cid,), commit=True)
    await callback.answer("✅ Клуб успешно удален из системы.")
    await handler_club_delete_list(callback)

# ==============================================================================
# БЛОК СОЗДАНИЯ МАТЧА (ИСПРАВЛЕННЫЙ И РАЗДУТЫЙ)
# ==============================================================================
@dp.callback_query(F.data == "btn_adm_match_create_start")
async def handler_match_create_step_1(callback: CallbackQuery, state: FSMContext):
    """Выбор Команды 1 (Хозяева)"""
    await state.clear()
    clubs_list = execute_db_query("SELECT id, name FROM clubs")
    
    if len(clubs_list) < 2:
        return await callback.message.edit_text(
            "❌ Для создания матча нужно хотя бы 2 клуба в базе!",
            reply_markup=ui_back_to_admin_button()
        )
        
    builder = InlineKeyboardBuilder()
    for c in clubs_list:
        # Важно: префикс f_t1_ помогает отличить выбор первой команды
        builder.button(text=f"🏠 {c[1]}", callback_data=f"f_t1_{c[0]}")
    
    builder.button(text="🔙 Отмена", callback_data="nav_to_admin_main")
    builder.adjust(2)
    
    await callback.message.edit_text(
        "⚽ **Создание матча: Шаг 1**\n\nВыберите **ПЕРВУЮ** команду (Хозяева):",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )
    await state.set_state(Form.match_creating_step_1)
    await callback.answer()

@dp.callback_query(F.data.startswith("f_t1_"), Form.match_creating_step_1)
async def handler_match_create_step_2(callback: CallbackQuery, state: FSMContext):
    """Выбор Команды 2 (Гости)"""
    t1_id = callback.data.split("_")[2]
    await state.update_data(created_match_t1=t1_id)
    
    # Исключаем из списка уже выбранную команду
    clubs_for_t2 = execute_db_query("SELECT id, name FROM clubs WHERE id != ?", (t1_id,))
    
    builder = InlineKeyboardBuilder()
    for c in clubs_for_t2:
        # Важно: префикс f_t2_ помогает отличить выбор второй команды
        builder.button(text=f"✈️ {c[1]}", callback_data=f"f_t2_{c[0]}")
    
    builder.button(text="🔙 Назад к выбору команды 1", callback_data="btn_adm_match_create_start")
    builder.adjust(2)
    
    await callback.message.edit_text(
        "⚽ **Создание матча: Шаг 2**\n\nВыберите **ВТОРУЮ** команду (Гости):",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )
    await state.set_state(Form.match_creating_step_2)
    await callback.answer()

@dp.callback_query(F.data.startswith("f_t2_"), Form.match_creating_step_2)
async def handler_match_create_step_3(callback: CallbackQuery, state: FSMContext):
    """Запрос времени матча"""
    t2_id = callback.data.split("_")[2]
    await state.update_data(created_match_t2=t2_id)
    
    await callback.message.edit_text(
        "⏰ **Создание матча: Шаг 3**\n\nВведите время и дату матча текстом:\n_(Пример: Сегодня в 21:00)_",
        reply_markup=ui_back_to_admin_button(),
        parse_mode="Markdown"
    )
    await state.set_state(Form.match_creating_step_3)
    await callback.answer()

@dp.message(Form.match_creating_step_3)
async def handler_match_create_final(message: Message, state: FSMContext):
    """Публикация матча в канал и запись в БД"""
    match_time_string = message.text.strip()
    data = await state.get_data()
    
    t1_id = data.get('created_match_t1')
    t2_id = data.get('created_match_t2')
    
    # Получаем названия для поста
    name_1 = execute_db_query("SELECT name FROM clubs WHERE id=?", (t1_id,), fetchone=True)[0]
    name_2 = execute_db_query("SELECT name FROM clubs WHERE id=?", (t2_id,), fetchone=True)[0]
    
    post_content = (
        f"🏟 **ЗАПЛАНИРОВАН МАТЧ ТУРА**\n\n"
        f"⚽ **{name_1}** VS **{name_2}**\n"
        f"📅 Начало: `{match_time_string}`\n\n"
        f"📊 **Статус подтверждения:**\n"
        f"1️⃣ {name_1}: ❌\n"
        f"2️⃣ {name_2}: ❌\n\n"
        f"Регистрация на матч через: {BOT_USERNAME}"
    )
    
    try:
        # Отправляем сообщение в основной канал лиги
        sent_msg = await bot.send_message(CHANNEL_ID, post_content, parse_mode="Markdown")
        
        # Записываем матч в базу
        execute_db_query(
            "INSERT INTO matches (t1_id, t2_id, time, msg_id) VALUES (?, ?, ?, ?)",
            (t1_id, t2_id, match_time_string, sent_msg.message_id),
            commit=True
        )
        
        await message.answer(
            "✅ **Матч успешно опубликован в канале!**",
            reply_markup=ui_main_menu_keyboard(message.from_user.id),
            parse_mode="Markdown"
        )
        logger.info(f"Матч {name_1} - {name_2} создан.")
        
    except Exception as e:
        await message.answer(f"❌ Ошибка при публикации матча: {e}")
        logger.error(f"Ошибка публикации: {e}")
        
    await state.clear()

# ==============================================================================
# БЛОК РЕДАКТИРОВАНИЯ И УДАЛЕНИЯ МАТЧЕЙ
# ==============================================================================
@dp.callback_query(F.data == "btn_adm_match_edit_list")
async def handler_match_edit_list(callback: CallbackQuery, state: FSMContext):
    """Выбор активного матча для редактирования"""
    matches = execute_db_query("SELECT id, t1_id, t2_id, time FROM matches WHERE status='active' ORDER BY id DESC LIMIT 15")
    if not matches:
        return await callback.message.edit_text("❌ Активных матчей не найдено.", reply_markup=ui_back_to_admin_button())
        
    builder = InlineKeyboardBuilder()
    for m in matches:
        n1 = execute_db_query("SELECT name FROM clubs WHERE id=?", (m[1],), fetchone=True)[0]
        n2 = execute_db_query("SELECT name FROM clubs WHERE id=?", (m[2],), fetchone=True)[0]
        builder.button(text=f"⚙️ {n1}-{n2} ({m[3]})", callback_data=f"match_edit_id_{m[0]}")
    
    builder.button(text="🔙 Назад", callback_data="nav_to_admin_main")
    builder.adjust(1)
    
    await state.set_state(Form.match_edit_select_id)
    await callback.message.edit_text("Выберите матч для внесения изменений:", reply_markup=builder.as_markup())
    await callback.answer()

@dp.callback_query(F.data.startswith("match_edit_id_"), Form.match_edit_select_id)
async def handler_match_edit_menu(callback: CallbackQuery, state: FSMContext):
    """Меню управления полями матча"""
    mid = callback.data.split("_")[3]
    await state.update_data(current_edit_match_id=mid)
    
    m_data = execute_db_query("SELECT t1_id, t2_id, time FROM matches WHERE id=?", (mid,), fetchone=True)
    n1 = execute_db_query("SELECT name FROM clubs WHERE id=?", (m_data[0],), fetchone=True)[0]
    n2 = execute_db_query("SELECT name FROM clubs WHERE id=?", (m_data[1],), fetchone=True)[0]
    
    builder = InlineKeyboardBuilder()
    builder.button(text="⏰ Время начала", callback_data="field_match_time")
    builder.button(text="👕 Команда 1", callback_data="field_match_t1")
    builder.button(text="👕 Команда 2", callback_data="field_match_t2")
    builder.button(text="🔙 К списку", callback_data="btn_adm_match_edit_list")
    builder.adjust(1)
    
    await callback.message.edit_text(
        f"🔄 **Матч #{mid}**\n\n⚔️ {n1} VS {n2}\n⏰ Время: `{m_data[2]}`\n\nЧто изменить?",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )
    await state.set_state(Form.match_edit_main_menu)
    await callback.answer()

@dp.callback_query(F.data == "field_match_time", Form.match_edit_main_menu)
async def handler_match_edit_time_init(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Введите новое время для этого матча:", reply_markup=ui_back_to_admin_button())
    await state.set_state(Form.match_edit_update_time)

@dp.message(Form.match_edit_update_time)
async def handler_match_edit_time_save(message: Message, state: FSMContext):
    data = await state.get_data()
    mid = data.get('current_edit_match_id')
    execute_db_query("UPDATE matches SET time=? WHERE id=?", (message.text, mid), commit=True)
    await message.answer("✅ Время матча обновлено!", reply_markup=ui_main_menu_keyboard(message.from_user.id))
    await state.clear()

@dp.callback_query(F.data == "btn_adm_match_del_list")
async def handler_match_delete_list(callback: CallbackQuery):
    """Список матчей для быстрого удаления"""
    matches = execute_db_query("SELECT id, t1_id, t2_id, time FROM matches ORDER BY id DESC LIMIT 10")
    if not matches:
        return await callback.message.edit_text("❌ Матчей нет.", reply_markup=ui_back_to_admin_button())
        
    builder = InlineKeyboardBuilder()
    for m in matches:
        n1 = execute_db_query("SELECT name FROM clubs WHERE id=?", (m[1],), fetchone=True)[0]
        n2 = execute_db_query("SELECT name FROM clubs WHERE id=?", (m[2],), fetchone=True)[0]
        builder.button(text=f"🗑 Удалить {n1}-{n2}", callback_data=f"match_del_exec_{m[0]}")
    
    builder.button(text="🔙 Назад", callback_data="nav_to_admin_main")
    builder.adjust(1)
    await callback.message.edit_text("Выберите матч для удаления:", reply_markup=builder.as_markup())
    await callback.answer()

@dp.callback_query(F.data.startswith("match_del_exec_"))
async def handler_match_delete_execute(callback: CallbackQuery):
    mid = callback.data.split("_")[3]
    execute_db_query("DELETE FROM matches WHERE id=?", (mid,), commit=True)
    await callback.answer("✅ Матч удален.")
    await handler_match_delete_list(callback)

# ==============================================================================
# БЛОК РАСПИСАНИЯ И УПРАВЛЕНИЯ ПРАВАМИ
# ==============================================================================
@dp.message(F.text == "📅 Расписание матчей")
async def handler_user_show_schedule(message: Message):
    """Показ актуального расписания любому пользователю"""
    sched_data = execute_db_query("SELECT value FROM settings WHERE key='schedule'", fetchone=True)
    await message.answer(
        f"📅 **Актуальное расписание лиги:**\n\n{sched_data[0]}",
        parse_mode="Markdown"
    )

@dp.callback_query(F.data == "btn_adm_sched_edit")
async def handler_admin_edit_sched_init(callback: CallbackQuery, state: FSMContext):
    """Инициализация смены текста расписания"""
    await callback.message.edit_text(
        "Введите новый текст для раздела расписания.\nМожно использовать Markdown разметку:",
        reply_markup=ui_back_to_admin_button()
    )
    await state.set_state(Form.editing_schedule_text)
    await callback.answer()

@dp.message(Form.editing_schedule_text)
async def handler_admin_edit_sched_save(message: Message, state: FSMContext):
    execute_db_query("UPDATE settings SET value=? WHERE key='schedule'", (message.text,), commit=True)
    await message.answer("✅ Текст расписания успешно обновлен!", reply_markup=ui_main_menu_keyboard(message.from_user.id))
    await state.clear()

@dp.callback_query(F.data == "btn_adm_role_give")
async def handler_admin_grant_init(callback: CallbackQuery, state: FSMContext):
    """Назначение нового админа по ID"""
    await callback.message.edit_text("Введите Telegram ID человека, которому нужно выдать админ-права:", reply_markup=ui_back_to_admin_button())
    await state.set_state(Form.admin_grant_id)
    await callback.answer()

@dp.message(Form.admin_grant_id)
async def handler_admin_grant_save(message: Message, state: FSMContext):
    if not message.text.isdigit(): return await message.answer("❌ Введите числовой ID:")
    execute_db_query("INSERT OR REPLACE INTO users (user_id, role) VALUES (?, 'admin')", (int(message.text),), commit=True)
    await message.answer(f"✅ Пользователь `{message.text}` теперь администратор!", reply_markup=ui_main_menu_keyboard(message.from_user.id), parse_mode="Markdown")
    await state.clear()

@dp.callback_query(F.data == "btn_adm_role_revoke")
async def handler_admin_revoke_init(callback: CallbackQuery, state: FSMContext):
    """Список текущих админов для снятия прав"""
    admins_list = execute_db_query("SELECT user_id FROM users WHERE role='admin'")
    if not admins_list:
        return await callback.message.edit_text("❌ Дополнительных администраторов не найдено.", reply_markup=ui_back_to_admin_button())
        
    text_list = "\n".join([f"• `{a[0]}`" for a in admins_list])
    await callback.message.edit_text(f"**Список текущих админов:**\n{text_list}\n\nВведите ID для снятия прав:", reply_markup=ui_back_to_admin_button(), parse_mode="Markdown")
    await state.set_state(Form.admin_revoke_id)
    await callback.answer()

@dp.message(Form.admin_revoke_id)
async def handler_admin_revoke_save(message: Message, state: FSMContext):
    execute_db_query("UPDATE users SET role='user' WHERE user_id=?", (int(message.text),), commit=True)
    await message.answer(f"✅ Права у пользователя `{message.text}` отозваны.", reply_markup=ui_main_menu_keyboard(message.from_user.id), parse_mode="Markdown")
    await state.clear()

# ==============================================================================
# БЛОК ОТПИСИ НА МАТЧ (ЛОГИКА ДЛЯ ВЛД И ЗАМОВ)
# ==============================================================================
@dp.message(F.text == "📝 Дать отпись")
async def handler_user_otpis_start(message: Message):
    """Список матчей, где еще не подтверждено участие команды игрока"""
    # Ищем матчи, где хотя бы одна команда не отписалась
    active_otpis_matches = execute_db_query("SELECT id, t1_id, t2_id FROM matches WHERE otpis1=0 OR otpis2=0")
    if not active_otpis_matches:
        return await message.answer("❌ На текущий момент нет активных отписей.")
        
    builder = InlineKeyboardBuilder()
    for m in active_otpis_matches:
        n1 = execute_db_query("SELECT name FROM clubs WHERE id=?", (m[1],), fetchone=True)[0]
        n2 = execute_db_query("SELECT name FROM clubs WHERE id=?", (m[2],), fetchone=True)[0]
        builder.button(text=f"📝 {n1} VS {n2}", callback_data=f"otpis_action_{m[0]}")
    
    builder.adjust(1)
    await message.answer("Выберите матч, за который ваш клуб должен отписаться:", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("otpis_action_"))
async def handler_user_otpis_execute(callback: CallbackQuery):
    """Проверка прав и фиксация отписи"""
    mid = callback.data.split("_")[2]
    match = execute_db_query("SELECT * FROM matches WHERE id=?", (mid,), fetchone=True)
    uid = str(callback.from_user.id)
    
    # Данные о командах в матче
    club1 = execute_db_query("SELECT vld_id, zams, name FROM clubs WHERE id=?", (match[1],), fetchone=True)
    club2 = execute_db_query("SELECT vld_id, zams, name FROM clubs WHERE id=?", (match[2],), fetchone=True)
    
    # Проверяем, к какому клубу относится пользователь
    target_side = None
    if uid == str(club1[0]) or uid in str(club1[1]).split(","):
        target_side = "otpis1"
    elif uid == str(club2[0]) or uid in str(club2[1]).split(","):
        target_side = "otpis2"
        
    if not target_side:
        return await callback.answer("🚫 Ошибка: Вы не являетесь ВЛД или замом этих команд!", show_alert=True)
        
    # Обновляем статус в БД
    execute_db_query(f"UPDATE matches SET {target_side}=1 WHERE id=?", (mid,), commit=True)
    await callback.answer("✅ Вы успешно отписались за свой клуб!")
    
    # Обновляем пост в канале
    updated_match = execute_db_query("SELECT * FROM matches WHERE id=?", (mid,), fetchone=True)
    s1 = "✅" if updated_match[4] else "❌"
    s2 = "✅" if updated_match[5] else "❌"
    
    upd_content = (
        f"🏟 **ОБНОВЛЕНИЕ МАТЧА**\n\n"
        f"⚽ **{club1[2]}** VS **{club2[2]}**\n"
        f"📅 Время: `{updated_match[3]}`\n\n"
        f"📊 **Статус подтверждения:**\n"
        f"1️⃣ {club1[2]}: {s1}\n"
        f"2️⃣ {club2[2]}: {s2}"
    )
    
    try:
        await bot.edit_message_text(upd_content, CHANNEL_ID, updated_match[6], parse_mode="Markdown")
    except:
        pass # Если сообщение уже удалено или не изменилось
        
    # Если отписались обе стороны - выбираем, кто создает VIP
    if updated_match[4] == 1 and updated_match[5] == 1:
        winner_id = random.choice([club1[0], club2[0]])
        execute_db_query("UPDATE matches SET vip_waiter=? WHERE id=?", (winner_id, mid), commit=True)
        await bot.send_message(winner_id, "🎲 **Жребий выпал вам!**\nВы должны создать VIP матч. Когда создадите, пришлите данные в бот сообщением вида:\n`вип:Текст данных`")

# ==============================================================================
# БЛОК СДАЧИ ТАБОВ (СКРИНШОТОВ)
# ==============================================================================
@dp.message(F.text == "📸 Дать табы")
async def handler_tabs_start(message: Message, state: FSMContext):
    """Начало процесса сдачи скриншотов"""
    # Выбираем матчи, где отписались оба
    matches = execute_db_query("SELECT id, t1_id, t2_id FROM matches WHERE otpis1=1 AND otpis2=1")
    if not matches:
        return await message.answer("❌ На данный момент нет матчей для сдачи табов.")
        
    builder = InlineKeyboardBuilder()
    for m in matches:
        n1 = execute_db_query("SELECT name FROM clubs WHERE id=?", (m[1],), fetchone=True)[0]
        n2 = execute_db_query("SELECT name FROM clubs WHERE id=?", (m[2],), fetchone=True)[0]
        builder.button(text=f"📸 {n1} - {n2}", callback_data=f"tabs_match_id_{m[0]}")
    
    builder.adjust(1)
    await message.answer("Выберите ваш матч из списка:", reply_markup=builder.as_markup())
    await state.set_state(Form.tabs_selecting_match)

@dp.callback_query(F.data.startswith("tabs_match_id_"), Form.tabs_selecting_match)
async def handler_tabs_photo_1_init(callback: CallbackQuery, state: FSMContext):
    mid = callback.data.split("_")[3]
    m_info = execute_db_query("SELECT t1_id, t2_id FROM matches WHERE id=?", (mid,), fetchone=True)
    uid = str(callback.from_user.id)
    
    c1 = execute_db_query("SELECT vld_id, zams, name FROM clubs WHERE id=?", (m_info[0],), fetchone=True)
    c2 = execute_db_query("SELECT vld_id, zams, name FROM clubs WHERE id=?", (m_info[1],), fetchone=True)
    
    acting_club = None
    if uid == str(c1[0]) or uid in str(c1[1]).split(","): acting_club = c1[2]
    elif uid == str(c2[0]) or uid in str(c2[1]).split(","): acting_club = c2[2]
    
    if not acting_club:
        return await callback.answer("🚫 У вас нет прав для сдачи табов этого матча!", show_alert=True)
        
    await state.update_data(tabs_active_club=acting_club)
    await callback.message.answer(f"📤 Команда: **{acting_club}**\nПожалуйста, отправьте скриншот **1 тайма**:", parse_mode="Markdown")
    await state.set_state(Form.tabs_upload_photo_1)
    await callback.answer()

@dp.message(Form.tabs_upload_photo_1, F.photo)
async def handler_tabs_photo_2_init(message: Message, state: FSMContext):
    """Прием первого фото и запрос второго"""
    file_id_1 = message.photo[-1].file_id
    await state.update_data(tabs_file_1=file_id_1)
    await message.answer("✅ Получено. Теперь отправьте скриншот **2 тайма**:", parse_mode="Markdown")
    await state.set_state(Form.tabs_upload_photo_2)

@dp.message(Form.tabs_upload_photo_2, F.photo)
async def handler_tabs_finish(message: Message, state: FSMContext):
    """Финальная отправка табов админам"""
    file_id_2 = message.photo[-1].file_id
    data = await state.get_data()
    club_name = data.get('tabs_active_club')
    file_1 = data.get('tabs_file_1')
    
    # Рассылка админам
    for admin in SUPER_ADMINS:
        try:
            await bot.send_message(admin, f"📸 **НОВЫЕ ТАБЫ**\nКоманда: {club_name}\nОтправил: @{message.from_user.username}")
            await bot.send_photo(admin, file_1, caption="Тайм 1")
            await bot.send_photo(admin, file_id_2, caption="Тайм 2")
        except:
            pass
            
    await message.answer("✅ Табы успешно отправлены администрации!", reply_markup=ui_main_menu_keyboard(message.from_user.id))
    await state.clear()

# ==============================================================================
# БЛОК ПЕРЕДАЧИ ДАННЫХ VIP
# ==============================================================================
@dp.message(F.text.startswith("вип:"))
async def handler_vip_transfer(message: Message):
    """Передача VIP данных сопернику"""
    uid = message.from_user.id
    # Ищем последний матч пользователя, где он назначен создателем VIP
    active_m = execute_db_query("SELECT t1_id, t2_id FROM matches WHERE vip_waiter=? ORDER BY id DESC LIMIT 1", (uid,), fetchone=True)
    
    if not active_m:
        return await message.answer("❌ Вы сейчас не должны создавать VIP или данные уже переданы.")
        
    # Вычисляем соперника
    vld_1 = execute_db_query("SELECT vld_id FROM clubs WHERE id=?", (active_m[0],), fetchone=True)[0]
    vld_2 = execute_db_query("SELECT vld_id FROM clubs WHERE id=?", (active_m[1],), fetchone=True)[0]
    
    opponent_id = vld_1 if uid == vld_2 else vld_2
    
    vip_text = message.text.replace("вип:", "").strip()
    
    try:
        await bot.send_message(opponent_id, f"📩 **ДАННЫЕ VIP ОТ СОПЕРНИКА:**\n\n`{vip_text}`", parse_mode="Markdown")
        await message.answer("✅ Данные успешно переданы вашему сопернику!")
        # Сбрасываем ожидание
        execute_db_query("UPDATE matches SET vip_waiter=0 WHERE vip_waiter=?", (uid,), commit=True)
    except Exception as e:
        await message.answer("❌ Не удалось отправить данные сопернику (возможно, он заблокировал бота).")

# ==============================================================================
# ЗАПУСК БОТА (ENTRY POINT)
# ==============================================================================
async def main_execution_loop():
    """Главная функция запуска бота"""
    # Сначала база
    initialize_database_structure()
    
    # Настройка команд в меню
    await bot.set_my_commands(
        [BotCommand(command="start", description="Перезапустить бота и обновить меню")], 
        scope=BotCommandScopeDefault()
    )
    
    logger.info("--- БОТ ЗАПУЩЕН И ГОТОВ К РАБОТЕ ---")
    
    # Запуск поллинга
    try:
        await dp.start_polling(bot)
    except Exception as poll_error:
        logger.error(f"Ошибка поллинга: {poll_error}")
    finally:
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main_execution_loop())
    except KeyboardInterrupt:
        logger.info("Бот остановлен вручную.")
    except Exception as fatal_error:
        logger.critical(f"ФАТАЛЬНАЯ ОШИБКА: {fatal_error}")
