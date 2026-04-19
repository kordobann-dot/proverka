import asyncio
import sqlite3
import random
import logging
import sys
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
    ContentType
)

# ==============================================================================
# КОНФИГУРАЦИЯ
# ==============================================================================
TOKEN = "8633419537:AAF6r1H1YtfI2whTHVdKzF2JVQnxgu9XfU4"
CHANNEL_ID = "@pistonCUPsls"
# Владельцы с полным доступом
SUPER_ADMINS = [5845609895, 6740071266]
BOT_USERNAME = "@TernatLeague_Bot"

# Настройка подробного логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] - %(name)s - (%(filename)s).%(funcName)s(%(lineno)d) - %(message)s",
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

bot = Bot(token=TOKEN)
dp = Dispatcher()

# ==============================================================================
# УПРАВЛЕНИЕ БАЗОЙ ДАННЫХ
# ==============================================================================
def db_query(query, params=(), fetchone=False, commit=False):
    """
    Безопасное выполнение SQL-запросов с обработкой блокировок.
    """
    conn = sqlite3.connect('league_data.db', timeout=35)
    cur = conn.cursor()
    try:
        cur.execute(query, params)
        if commit:
            conn.commit()
        if fetchone:
            return cur.fetchone()
        return cur.fetchall()
    except Exception as e:
        logger.error(f"SQL Error: {e} | Query: {query}")
        return None
    finally:
        conn.close()

def init_db():
    """Создание таблиц, если они не существуют"""
    logger.info("Проверка и инициализация таблиц базы данных...")
    
    # Таблица пользователей и админов
    db_query("""CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY, 
        role TEXT DEFAULT 'user'
    )""", commit=True)
    
    # Таблица футбольных клубов
    db_query("""CREATE TABLE IF NOT EXISTS clubs (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        name TEXT NOT NULL, 
        vld_id INTEGER NOT NULL, 
        zams TEXT DEFAULT ''
    )""", commit=True)
    
    # Таблица матчей
    db_query("""CREATE TABLE IF NOT EXISTS matches (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        t1_id INTEGER, 
        t2_id INTEGER, 
        time TEXT, 
        otpis1 INTEGER DEFAULT 0, 
        otpis2 INTEGER DEFAULT 0, 
        msg_id INTEGER, 
        vip_waiter INTEGER
    )""", commit=True)
    
    # Таблица общих настроек (расписание и т.д.)
    db_query("""CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY, 
        value TEXT
    )""", commit=True)
    
    # Начальное расписание
    check_sched = db_query("SELECT value FROM settings WHERE key='schedule'", fetchone=True)
    if not check_sched:
        db_query("INSERT INTO settings (key, value) VALUES ('schedule', 'На текущий момент расписание пусто.')", commit=True)
    
    logger.info("База данных готова к работе.")

# ==============================================================================
# СОСТОЯНИЯ (FSM)
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
    
    # Система табов
    tab_match_select = State()
    tab_photo1 = State()
    tab_photo2 = State()
    
    # Редактирование клуба
    edit_club_select = State()
    edit_club_choice = State()
    edit_club_input = State()
    
    # Админка
    give_admin_id = State()
    remove_admin_id = State()

# ==============================================================================
# ВСПОМОГАТЕЛЬНЫЕ КЛАВИАТУРЫ
# ==============================================================================
def main_menu_kb(user_id):
    """Главное меню бота"""
    kb = ReplyKeyboardBuilder()
    kb.button(text="📅 Расписание матчей")
    kb.button(text="📝 Дать отпись")
    kb.button(text="📸 Дать табы")
    
    # Проверка на админа
    is_adm = db_query("SELECT role FROM users WHERE user_id=?", (user_id,), fetchone=True)
    if user_id in SUPER_ADMINS or (is_adm and is_adm[0] == 'admin'):
        kb.button(text="⚙️ Админ панель")
    
    kb.adjust(2)
    return kb.as_markup(resize_keyboard=True)

def admin_panel_kb(user_id):
    """Инлайн меню управления"""
    kb = InlineKeyboardBuilder()
    kb.button(text="🏠 Добавить новый клуб", callback_data="adm_add_club")
    kb.button(text="✏️ Редактировать клуб", callback_data="adm_edit_club")
    kb.button(text="⚽ Создать новый матч", callback_data="adm_make_match")
    kb.button(text="📅 Обновить расписание", callback_data="adm_edit_sched")
    kb.button(text="🗑 Удалить клуб", callback_data="adm_del_club")
    
    if user_id in SUPER_ADMINS:
        kb.button(text="👑 Назначить администратора", callback_data="adm_give_role")
        kb.button(text="❌ Удалить администратора", callback_data="adm_remove_role")
    
    kb.adjust(1)
    return kb.as_markup()

def back_to_admin_kb():
    """Кнопка отмены/возврата"""
    kb = InlineKeyboardBuilder()
    kb.button(text="🔙 Отменить и Назад", callback_data="cancel_to_admin")
    return kb.as_markup()

# ==============================================================================
# ОБРАБОТЧИКИ ОТМЕНЫ И СТАРТА
# ==============================================================================
@dp.callback_query(F.data == "cancel_to_admin")
async def process_cancel_to_admin(callback: CallbackQuery, state: FSMContext):
    """Универсальная кнопка отмены любого действия"""
    await state.clear()
    await callback.message.edit_text(
        "❌ Действие отменено.\n\nВы вернулись в админ панель:", 
        reply_markup=admin_panel_kb(callback.from_user.id)
    )
    await callback.answer()

@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    """Запуск бота"""
    await state.clear()
    init_db()
    
    # Автоматическая регистрация пользователя в БД
    db_query("INSERT OR IGNORE INTO users (user_id, role) VALUES (?, 'user')", (message.from_user.id,), commit=True)
    
    welcome_text = (
        "👋 **Добро пожаловать в систему автоматизации Лиги!**\n\n"
        "Я помогу вам управлять матчами, собирать табы и следить за расписанием.\n\n"
        "Воспользуйтесь кнопками ниже для навигации."
    )
    await message.answer(welcome_text, reply_markup=main_menu_kb(message.from_user.id), parse_mode="Markdown")

# ==============================================================================
# РАСПИСАНИЕ
# ==============================================================================
@dp.message(F.text == "📅 Расписание матчей")
async def show_schedule(message: Message):
    """Показ текущего расписания"""
    data = db_query("SELECT value FROM settings WHERE key='schedule'", fetchone=True)
    text = data[0] if data else "Расписание не заполнено."
    await message.answer(f"📋 **ТЕКУЩЕЕ РАСПИСАНИЕ:**\n\n{text}", parse_mode="Markdown")

@dp.callback_query(F.data == "adm_edit_sched")
async def admin_edit_sched_start(callback: CallbackQuery, state: FSMContext):
    """Начало изменения расписания"""
    await callback.message.edit_text(
        "📝 **Введите новый текст для расписания.**\n\n"
        "Вы можете использовать эмодзи и форматирование.\n"
        "Чтобы отменить, нажмите кнопку ниже.",
        reply_markup=back_to_admin_kb(),
        parse_mode="Markdown"
    )
    await state.set_state(Form.edit_schedule_text)
    await callback.answer()

@dp.message(Form.edit_schedule_text)
async def admin_edit_sched_finish(message: Message, state: FSMContext):
    """Сохранение расписания"""
    db_query("UPDATE settings SET value=? WHERE key='schedule'", (message.text,), commit=True)
    await message.answer(
        "✅ **Расписание успешно обновлено!**", 
        reply_markup=main_menu_kb(message.from_user.id),
        parse_mode="Markdown"
    )
    await state.clear()

# ==============================================================================
# УПРАВЛЕНИЕ АДМИНИСТРАТОРАМИ
# ==============================================================================
@dp.callback_query(F.data == "adm_remove_role")
async def admin_remove_start(callback: CallbackQuery, state: FSMContext):
    """Процесс удаления админа"""
    admins = db_query("SELECT user_id FROM users WHERE role='admin'")
    if not admins:
        return await callback.message.edit_text("В системе нет администраторов.", reply_markup=back_to_admin_kb())
    
    text = "🛑 **Список администраторов:**\n\n"
    for a in admins:
        text += f"• `{a[0]}`\n"
    
    text += "\nВведите Telegram ID для удаления из списка:"
    await callback.message.edit_text(text, reply_markup=back_to_admin_kb(), parse_mode="Markdown")
    await state.set_state(Form.remove_admin_id)
    await callback.answer()

@dp.message(Form.remove_admin_id)
async def admin_remove_finish(message: Message, state: FSMContext):
    """Финализация удаления админа"""
    if not message.text.isdigit():
        return await message.answer("❌ Ошибка: ID должен состоять только из цифр. Попробуйте еще раз или отмените действие.")
    
    db_query("UPDATE users SET role='user' WHERE user_id=?", (int(message.text),), commit=True)
    await message.answer(f"✅ Пользователь `{message.text}` разжалован до обычного игрока.", reply_markup=main_menu_kb(message.from_user.id), parse_mode="Markdown")
    await state.clear()

@dp.callback_query(F.data == "adm_give_role")
async def admin_give_start(callback: CallbackQuery, state: FSMContext):
    """Назначение нового админа"""
    await callback.message.edit_text(
        "👑 **Назначение администратора**\n\nВведите Telegram ID пользователя:", 
        reply_markup=back_to_admin_kb(),
        parse_mode="Markdown"
    )
    await state.set_state(Form.give_admin_id)
    await callback.answer()

@dp.message(Form.give_admin_id)
async def admin_give_finish(message: Message, state: FSMContext):
    """Финализация назначения"""
    if not message.text.isdigit():
        return await message.answer("❌ Ошибка: ID должен быть числовым.")
    
    db_query("INSERT OR REPLACE INTO users (user_id, role) VALUES (?, 'admin')", (int(message.text),), commit=True)
    await message.answer(f"✅ Пользователь `{message.text}` теперь администратор лиги.", reply_markup=main_menu_kb(message.from_user.id), parse_mode="Markdown")
    await state.clear()

# ==============================================================================
# УПРАВЛЕНИЕ КЛУБАМИ (ДОБАВЛЕНИЕ И РЕДАКТИРОВАНИЕ)
# ==============================================================================
@dp.callback_query(F.data == "adm_add_club")
async def add_club_name_start(callback: CallbackQuery, state: FSMContext):
    """Добавление клуба - Шаг 1: Название"""
    await callback.message.edit_text(
        "📝 **Создание нового клуба**\n\nВведите официальное название команды:", 
        reply_markup=back_to_admin_kb(),
        parse_mode="Markdown"
    )
    await state.set_state(Form.add_club_name)
    await callback.answer()

@dp.message(Form.add_club_name)
async def add_club_vld_start(message: Message, state: FSMContext):
    """Добавление клуба - Шаг 2: ВЛД"""
    await state.update_data(new_club_name=message.text)
    await message.answer(
        f"Клуб: **{message.text}**\n\nТеперь введите Telegram ID владельца (ВЛД):", 
        reply_markup=back_to_admin_kb(),
        parse_mode="Markdown"
    )
    await state.set_state(Form.add_club_vld)

@dp.message(Form.add_club_vld)
async def add_club_finish(message: Message, state: FSMContext):
    """Добавление клуба - Завершение"""
    if not message.text.isdigit():
        return await message.answer("❌ Ошибка: ID ВЛД должен состоять только из цифр.")
    
    data = await state.get_data()
    club_name = data['new_club_name']
    vld_id = int(message.text)
    
    res = db_query("INSERT INTO clubs (name, vld_id) VALUES (?, ?)", (club_name, vld_id), commit=True)
    
    if res is not None:
        await message.answer(
            f"✅ **Клуб успешно зарегистрирован!**\n\nНазвание: {club_name}\nID ВЛД: `{vld_id}`", 
            reply_markup=main_menu_kb(message.from_user.id),
            parse_mode="Markdown"
        )
    else:
        await message.answer("❌ Произошла ошибка базы данных. Попробуйте снова.")
    
    await state.clear()

@dp.callback_query(F.data == "adm_edit_club")
async def edit_club_selection(callback: CallbackQuery, state: FSMContext):
    """Редактирование клуба - Выбор цели"""
    clubs = db_query("SELECT id, name FROM clubs")
    if not clubs:
        return await callback.answer("Клубы не найдены в базе!", show_alert=True)
    
    kb = InlineKeyboardBuilder()
    for cid, name in clubs:
        kb.button(text=f"⚙️ {name}", callback_data=f"target_cl_{cid}")
    kb.button(text="🔙 Назад", callback_data="cancel_to_admin")
    kb.adjust(1)
    
    await callback.message.edit_text("Выберите команду для редактирования:", reply_markup=kb.as_markup())
    await state.set_state(Form.edit_club_select)
    await callback.answer()

@dp.callback_query(F.data.startswith("target_cl_"), Form.edit_club_select)
async def edit_club_menu(callback: CallbackQuery, state: FSMContext):
    """Меню опций редактирования клуба"""
    club_id = callback.data.split("_")[2]
    await state.update_data(editing_club_id=club_id)
    
    c_info = db_query("SELECT name, vld_id, zams FROM clubs WHERE id=?", (club_id,), fetchone=True)
    
    kb = InlineKeyboardBuilder()
    kb.button(text="📝 Сменить название", callback_data="act_name")
    kb.button(text="👤 Сменить ВЛД (ID)", callback_data="act_vld")
    kb.button(text="➕ Добавить зама", callback_data="act_addz")
    kb.button(text="🧹 Очистить замов", callback_data="act_clearz")
    kb.button(text="🔙 Назад", callback_data="adm_edit_club")
    kb.adjust(2)
    
    detail_text = (
        f"📊 **Карточка клуба:**\n\n"
        f"🆔 ID: `{club_id}`\n"
        f"Команда: **{c_info[0]}**\n"
        f"Владелец: `{c_info[1]}`\n"
        f"Замы: `{c_info[2] if c_info[2] else 'не назначены'}`"
    )
    await callback.message.edit_text(detail_text, reply_markup=kb.as_markup(), parse_mode="Markdown")
    await state.set_state(Form.edit_club_choice)
    await callback.answer()

@dp.callback_query(F.data.startswith("act_"), Form.edit_club_choice)
async def edit_club_action_router(callback: CallbackQuery, state: FSMContext):
    """Роутер действий редактирования"""
    action = callback.data
    
    if action == "act_clearz":
        data = await state.get_data()
        db_query("UPDATE clubs SET zams='' WHERE id=?", (data['editing_club_id'],), commit=True)
        await callback.answer("Замы успешно удалены")
        return await edit_club_selection(callback, state)
    
    await state.update_data(current_action=action)
    
    prompts = {
        "act_name": "Введите новое название клуба:",
        "act_vld": "Введите новый ID владельца:",
        "act_addz": "Введите ID зама, которого нужно добавить:"
    }
    
    await callback.message.edit_text(prompts[action], reply_markup=back_to_admin_kb())
    await state.set_state(Form.edit_club_input)
    await callback.answer()

@dp.message(Form.edit_club_input)
async def edit_club_final_save(message: Message, state: FSMContext):
    """Сохранение изменений клуба"""
    state_data = await state.get_data()
    cid = state_data['editing_club_id']
    act = state_data['current_action']
    val = message.text
    
    try:
        if act == "act_name":
            db_query("UPDATE clubs SET name=? WHERE id=?", (val, cid), commit=True)
        elif act == "act_vld":
            db_query("UPDATE clubs SET vld_id=? WHERE id=?", (int(val), cid), commit=True)
        elif act == "act_addz":
            old_zams = db_query("SELECT zams FROM clubs WHERE id=?", (cid,), fetchone=True)[0]
            updated_zams = f"{old_zams},{val}" if old_zams else val
            db_query("UPDATE clubs SET zams=? WHERE id=?", (updated_zams, cid), commit=True)
        
        await message.answer("✅ **Данные клуба обновлены!**", reply_markup=main_menu_kb(message.from_user.id), parse_mode="Markdown")
        await state.clear()
    except Exception as e:
        logger.error(f"Save error: {e}")
        await message.answer("❌ Ошибка при сохранении. Убедитесь, что вводите корректные данные.")

# ==============================================================================
# СОЗДАНИЕ МАТЧА
# ==============================================================================
@dp.callback_query(F.data == "adm_make_match")
async def match_create_t1(callback: CallbackQuery, state: FSMContext):
    """Создание матча - Выбор 1 команды"""
    clubs = db_query("SELECT id, name FROM clubs")
    if len(clubs) < 2:
        return await callback.answer("Ошибка: для матча нужно минимум 2 клуба!", show_alert=True)
    
    kb = InlineKeyboardBuilder()
    for cid, name in clubs:
        kb.button(text=name, callback_data=f"sett1_{cid}")
    kb.button(text="🔙 Отмена", callback_data="cancel_to_admin")
    kb.adjust(2)
    
    await callback.message.edit_text("⚽ **Создание матча**\n\nВыберите ХОЗЯЕВ поля:", reply_markup=kb.as_markup(), parse_mode="Markdown")
    await state.set_state(Form.m_t1)
    await callback.answer()

@dp.callback_query(F.data.startswith("sett1_"), Form.m_t1)
async def match_create_t2(callback: CallbackQuery, state: FSMContext):
    """Создание матча - Выбор 2 команды"""
    t1_id = callback.data.split("_")[1]
    await state.update_data(match_t1=t1_id)
    
    clubs = db_query("SELECT id, name FROM clubs WHERE id != ?", (t1_id,))
    kb = InlineKeyboardBuilder()
    for cid, name in clubs:
        kb.button(text=name, callback_data=f"sett2_{cid}")
    kb.button(text="🔙 Назад", callback_data="adm_make_match")
    kb.adjust(2)
    
    await callback.message.edit_text("⚽ **Создание матча**\n\nВыберите ГОСТЕЙ поля:", reply_markup=kb.as_markup(), parse_mode="Markdown")
    await state.set_state(Form.m_t2)
    await callback.answer()

@dp.callback_query(F.data.startswith("sett2_"), Form.m_t2)
async def match_create_time(callback: CallbackQuery, state: FSMContext):
    """Создание матча - Ввод времени"""
    t2_id = callback.data.split("_")[1]
    await state.update_data(match_t2=t2_id)
    
    await callback.message.edit_text(
        "⏰ **Введите время начала матча**\n\nПример: `20:00` или `15.04 18:30`", 
        reply_markup=back_to_admin_kb(),
        parse_mode="Markdown"
    )
    await state.set_state(Form.m_time)
    await callback.answer()

@dp.message(Form.m_time)
async def match_create_finish(message: Message, state: FSMContext):
    """Публикация матча в канал и запись в БД"""
    data = await state.get_data()
    t1_id, t2_id, time_val = data['match_t1'], data['match_t2'], message.text
    
    n1 = db_query("SELECT name FROM clubs WHERE id=?", (t1_id,), fetchone=True)[0]
    n2 = db_query("SELECT name FROM clubs WHERE id=?", (t2_id,), fetchone=True)[0]
    
    post = (
        f"🏟 **ОБЪЯВЛЕН МАТЧ ТУРА!**\n\n"
        f"⚽ **{n1}** — **{n2}**\n"
        f"⏰ Начало: `{time_val}`\n\n"
        f"📌 Статус отписи:\n"
        f"1️⃣ {n1}: ❌\n"
        f"2️⃣ {n2}: ❌\n\n"
        f"Регистрация на матч через бота: {BOT_USERNAME}"
    )
    
    try:
        sent = await bot.send_message(CHANNEL_ID, post, parse_mode="Markdown")
        db_query(
            "INSERT INTO matches (t1_id, t2_id, time, msg_id) VALUES (?, ?, ?, ?)", 
            (t1_id, t2_id, time_val, sent.message_id), 
            commit=True
        )
        await message.answer("✅ Матч создан и опубликован в канале!", reply_markup=main_menu_kb(message.from_user.id))
    except Exception as e:
        await message.answer(f"❌ Ошибка при публикации в канал: {e}")
    
    await state.clear()

# ==============================================================================
# ОТПИСЬ НА МАТЧ
# ==============================================================================
@dp.message(F.text == "📝 Дать отпись")
async def otpis_select_match(message: Message):
    """Выбор матча для отписи пользователем"""
    active = db_query("SELECT id, t1_id, t2_id FROM matches WHERE otpis1=0 OR otpis2=0")
    if not active:
        return await message.answer("❌ В данный момент нет активных отписей.")
    
    kb = InlineKeyboardBuilder()
    for mid, t1, t2 in active:
        name1 = db_query("SELECT name FROM clubs WHERE id=?", (t1,), fetchone=True)[0]
        name2 = db_query("SELECT name FROM clubs WHERE id=?", (t2,), fetchone=True)[0]
        kb.button(text=f"{name1} vs {name2}", callback_data=f"sign_{mid}")
    kb.adjust(1)
    
    await message.answer("Выберите матч для подтверждения участия вашей команды:", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("sign_"))
async def otpis_execute(callback: CallbackQuery):
    """Логика нажатия кнопки отписи"""
    mid = callback.data.split("_")[1]
    m_info = db_query("SELECT * FROM matches WHERE id=?", (mid,), fetchone=True)
    uid = str(callback.from_user.id)
    
    # Клубы
    club1 = db_query("SELECT vld_id, zams, name FROM clubs WHERE id=?", (m_info[1],), fetchone=True)
    club2 = db_query("SELECT vld_id, zams, name FROM clubs WHERE id=?", (m_info[2],), fetchone=True)
    
    target = None
    if uid == str(club1[0]) or uid in str(club1[1]).split(","): target = "otpis1"
    elif uid == str(club2[0]) or uid in str(club2[1]).split(","): target = "otpis2"
    
    if not target:
        return await callback.answer("🚫 У вас нет прав для отписи за эти команды!", show_alert=True)
    
    db_query(f"UPDATE matches SET {target}=1 WHERE id=?", (mid,), commit=True)
    await callback.answer("✅ Отпись успешно подтверждена!")
    
    # Обновляем сообщение в канале
    m_upd = db_query("SELECT * FROM matches WHERE id=?", (mid,), fetchone=True)
    n1 = db_query("SELECT name FROM clubs WHERE id=?", (m_upd[1],), fetchone=True)[0]
    n2 = db_query("SELECT name FROM clubs WHERE id=?", (m_upd[2],), fetchone=True)[0]
    s1, s2 = ("✅" if m_upd[4] else "❌"), ("✅" if m_upd[5] else "❌")
    
    upd_post = (
        f"🏟 **ОБНОВЛЕНИЕ СТАТУСА МАТЧА**\n\n"
        f"⚽ **{n1}** — **{n2}**\n"
        f"⏰ Начало: `{m_upd[3]}`\n\n"
        f"📌 Статус отписи:\n"
        f"1️⃣ {n1}: {s1}\n"
        f"2️⃣ {n2}: {s2}\n\n"
        f"Бот лиги: {BOT_USERNAME}"
    )
    
    try:
        await bot.edit_message_text(upd_post, CHANNEL_ID, m_upd[6], parse_mode="Markdown")
    except: pass
    
    # Жребий на VIP
    if m_upd[4] == 1 and m_upd[5] == 1:
        winner = random.choice([club1[0], club2[0]])
        db_query("UPDATE matches SET vip_waiter=? WHERE id=?", (winner, mid), commit=True)
        await bot.send_message(winner, "🎰 **Жребий!**\nВаша команда создает VIP на этот матч.\nНапишите в ответ: `вип:Текст`", parse_mode="Markdown")

# ==============================================================================
# СИСТЕМА ТАБОВ (СКРИНШОТОВ)
# ==============================================================================
@dp.message(F.text == "📸 Дать табы")
async def tabs_start(message: Message, state: FSMContext):
    """Поиск матча для сдачи табов"""
    # Ищем матчи, где отписались оба
    matches = db_query("SELECT id, t1_id, t2_id FROM matches WHERE otpis1=1 AND otpis2=1")
    if not matches:
        return await message.answer("❌ Нет активных матчей для сдачи табов.")
    
    kb = InlineKeyboardBuilder()
    for mid, t1, t2 in matches:
        n1 = db_query("SELECT name FROM clubs WHERE id=?", (t1,), fetchone=True)[0]
        n2 = db_query("SELECT name FROM clubs WHERE id=?", (t2,), fetchone=True)[0]
        kb.button(text=f"{n1} vs {n2}", callback_data=f"dotab_{mid}")
    kb.adjust(1)
    
    await message.answer("Выберите ваш матч для сдачи табов:", reply_markup=kb.as_markup())
    await state.set_state(Form.tab_match_select)

@dp.callback_query(F.data.startswith("dotab_"), Form.tab_match_select)
async def tabs_verification(callback: CallbackQuery, state: FSMContext):
    """Проверка прав доступа к сдаче табов"""
    mid = callback.data.split("_")[1]
    m_info = db_query("SELECT t1_id, t2_id FROM matches WHERE id=?", (mid,), fetchone=True)
    uid = str(callback.from_user.id)
    
    t1 = db_query("SELECT vld_id, zams, name FROM clubs WHERE id=?", (m_info[0],), fetchone=True)
    t2 = db_query("SELECT vld_id, zams, name FROM clubs WHERE id=?", (m_info[1],), fetchone=True)
    
    active_club = None
    if uid == str(t1[0]) or uid in str(t1[1]).split(","): active_club = t1[2]
    elif uid == str(t2[0]) or uid in str(t2[1]).split(","): active_club = t2[2]
    
    if not active_club:
        return await callback.answer("🚫 Вы не ВЛД/Зам ни одной из команд!", show_alert=True)
    
    await state.update_data(tab_match_id=mid, tab_club_name=active_club)
    await callback.message.answer(f"Команда: **{active_club}**\nОтправьте скриншот **1 ТАЙМА**:", parse_mode="Markdown")
    await state.set_state(Form.tab_photo1)
    await callback.answer()

@dp.message(Form.tab_photo1, F.photo)
async def tabs_p1_save(message: Message, state: FSMContext):
    """Получение первого скрина"""
    await state.update_data(file_p1=message.photo[-1].file_id)
    await message.answer("Скриншот получен! Теперь отправьте скриншот **2 ТАЙМА**:")
    await state.set_state(Form.tab_photo2)

@dp.message(Form.tab_photo2, F.photo)
async def tabs_p2_save(message: Message, state: FSMContext):
    """Отправка табов админам"""
    data = await state.get_data()
    f1, f2 = data['file_p1'], message.photo[-1].file_id
    team = data['tab_club_name']
    
    for adm in SUPER_ADMINS:
        try:
            await bot.send_message(adm, f"📥 **НОВЫЕ ТАБЫ**\nКоманда: {team}\nОт: {message.from_user.full_name}")
            await bot.send_photo(adm, f1, caption="Тайм #1")
            await bot.send_photo(adm, f2, caption="Тайм #2")
        except: pass
    
    await message.answer("✅ Табы успешно доставлены администрации!", reply_markup=main_menu_kb(message.from_user.id))
    await state.clear()

# ==============================================================================
# ВСПОМОГАТЕЛЬНОЕ: VIP И УДАЛЕНИЕ
# ==============================================================================
@dp.message(F.text == "⚙️ Админ панель")
async def show_admin_panel(message: Message):
    """Вход в админку"""
    is_adm = db_query("SELECT role FROM users WHERE user_id=?", (message.from_user.id,), fetchone=True)
    if message.from_user.id in SUPER_ADMINS or (is_adm and is_adm[0] == 'admin'):
        await message.answer("🛠 **Панель управления Лигой**", reply_markup=admin_panel_kb(message.from_user.id), parse_mode="Markdown")

@dp.message(F.text.startswith("вип:"))
async def handle_vip_transfer(message: Message):
    """Передача данных ВИПА"""
    # Ищем последний активный матч
    m = db_query("SELECT t1_id, t2_id, vip_waiter FROM matches WHERE vip_waiter IS NOT NULL ORDER BY id DESC LIMIT 1", fetchone=True)
    if m:
        v1 = db_query("SELECT vld_id FROM clubs WHERE id=?", (m[0],), fetchone=True)[0]
        v2 = db_query("SELECT vld_id FROM clubs WHERE id=?", (m[1],), fetchone=True)[0]
        
        target = v1 if str(message.from_user.id) == str(v2) else v2
        kb = InlineKeyboardBuilder().button(text="Принял! ✅", callback_data="vip_received").as_markup()
        await bot.send_message(target, f"📩 **ДАННЫЕ VIP:**\n\n`{message.text}`", parse_mode="Markdown", reply_markup=kb)
        await message.answer("✅ Данные переданы сопернику.")

@dp.callback_query(F.data == "vip_received")
async def vip_received_confirm(callback: CallbackQuery):
    await callback.message.edit_text(callback.message.text + "\n\n🚀 **Матч запущен! Удачной игры.**")

@dp.callback_query(F.data == "adm_del_club")
async def delete_club_list(callback: CallbackQuery):
    """Удаление клуба - выбор"""
    clubs = db_query("SELECT id, name FROM clubs")
    kb = InlineKeyboardBuilder()
    for cid, name in clubs:
        kb.button(text=f"🗑 {name}", callback_data=f"drop_club_{cid}")
    kb.button(text="🔙 Назад", callback_data="cancel_to_admin")
    kb.adjust(1)
    await callback.message.edit_text("Выберите команду для **УДАЛЕНИЯ** из системы:", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("drop_club_"))
async def delete_club_confirm(callback: CallbackQuery):
    """Удаление клуба - финиш"""
    cid = callback.data.split("_")[2]
    db_query("DELETE FROM clubs WHERE id=?", (cid,), commit=True)
    await callback.answer("Клуб успешно удален")
    await delete_club_list(callback)

# ==============================================================================
# ТОЧКА ВХОДА И ЗАПУСК
# ==============================================================================
async def main():
    logger.info("Запуск бота...")
    init_db()
    
    # Установка подсказок команд
    await bot.set_my_commands([
        BotCommand(command="start", description="Перезапуск и меню"),
    ])
    
    # Запуск опроса серверов
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот выключен.")
