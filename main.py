import asyncio
import sqlite3
import random
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from aiogram.types import InlineKeyboardButton, ReplyKeyboardRemove, BotCommand

# ================= НАСТРОЙКИ =================
TOKEN = "8633419537:AAF6r1H1YtfI2whTHVdKzF2JVQnxgu9XfU4"
CHANNEL_ID = "@pistonCUPsls"
# Твои ID админов
SUPER_ADMINS = [5845609895, 6740071266]
BOT_USERNAME = "@TernatLeague_Bot"

bot = Bot(token=TOKEN)
dp = Dispatcher()
logging.basicConfig(level=logging.INFO)

# ================= РАБОТА С БАЗОЙ ДАННЫХ =================
def db_query(query, params=(), fetchone=False, commit=False):
    conn = sqlite3.connect('league_data.db', timeout=20)
    cur = conn.cursor()
    try:
        cur.execute(query, params)
        if commit:
            conn.commit()
        if fetchone:
            return cur.fetchone()
        return cur.fetchall()
    except Exception as e:
        logging.error(f"DATABASE ERROR: {e}")
        return None
    finally:
        conn.close()

def init_db():
    db_query("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, role TEXT)", commit=True)
    db_query("CREATE TABLE IF NOT EXISTS clubs (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, vld_id INTEGER, zams TEXT DEFAULT '')", commit=True)
    db_query("""CREATE TABLE IF NOT EXISTS matches (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        t1_id INTEGER, t2_id INTEGER, 
        time TEXT, otpis1 INTEGER DEFAULT 0, 
        otpis2 INTEGER DEFAULT 0, msg_id INTEGER, vip_waiter INTEGER)""", commit=True)
    db_query("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)", commit=True)

# ================= СОСТОЯНИЯ (FSM) =================
class Form(StatesGroup):
    add_club_name = State()
    add_club_vld = State()
    edit_schedule = State()
    
    # Создание матча
    m_t1 = State()
    m_t2 = State()
    m_time = State()
    
    # Логика ТАБОВ
    tab_match_select = State()
    tab_photo1 = State()
    tab_photo2 = State()
    
    # Редактирование клубов
    edit_club_select = State()
    edit_club_choice = State()
    edit_club_input = State()
    
    # Роли
    give_admin_id = State()
    remove_admin_id = State()

# ================= КЛАВИАТУРЫ =================
def main_kb(uid):
    builder = ReplyKeyboardBuilder()
    builder.button(text="📅 Расписание матчей")
    builder.button(text="📝 Дать отпись")
    builder.button(text="📸 Дать табы")
    
    role = db_query("SELECT role FROM users WHERE user_id=?", (uid,), True)
    if uid in SUPER_ADMINS or role:
        builder.button(text="⚙️ Админ панель")
    
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)

def admin_kb(uid):
    builder = InlineKeyboardBuilder()
    builder.button(text="🏠 Добавить клуб", callback_data="adm_add_club")
    builder.button(text="✏️ Изменить клуб", callback_data="adm_edit_club")
    builder.button(text="⚽ Создать матч", callback_data="adm_make_match")
    builder.button(text="📅 Изменить расписание", callback_data="adm_edit_sched")
    builder.button(text="🗑 Удалить клуб", callback_data="adm_del_club")
    
    if uid in SUPER_ADMINS:
        builder.button(text="👑 Дать админку", callback_data="adm_give_role")
        builder.button(text="❌ Убрать админа", callback_data="adm_remove_role")
    
    builder.adjust(1)
    return builder.as_markup()

# ================= ОБРАБОТЧИКИ =================

@dp.message(Command("start"))
async def cmd_start(m: types.Message, state: FSMContext):
    await state.clear()
    init_db()
    await m.answer("⚽ Привет! Система футбольной лиги запущена.\nИспользуй меню ниже.", reply_markup=main_kb(m.from_user.id))

# --- АДМИН ПАНЕЛЬ ---
@dp.message(F.text == "⚙️ Админ панель")
async def open_admin(m: types.Message):
    role = db_query("SELECT role FROM users WHERE user_id=?", (m.from_user.id,), True)
    if m.from_user.id in SUPER_ADMINS or role:
        await m.answer("⚙️ Вы вошли в панель управления:", reply_markup=admin_kb(m.from_user.id))

# --- ДОБАВЛЕНИЕ КЛУБА ---
@dp.callback_query(F.data == "adm_add_club")
async def add_club_step1(c: types.CallbackQuery, state: FSMContext):
    await c.message.answer("Введите название нового клуба:")
    await state.set_state(Form.add_club_name)

@dp.message(Form.add_club_name)
async def add_club_step2(m: types.Message, state: FSMContext):
    await state.update_data(c_name=m.text)
    await m.answer(f"Название: {m.text}\nТеперь введите Telegram ID владельца (ВЛД):")
    await state.set_state(Form.add_club_vld)

@dp.message(Form.add_club_vld)
async def add_club_step3(m: types.Message, state: FSMContext):
    data = await state.get_data()
    try:
        vld_id = int(m.text)
        db_query("INSERT INTO clubs (name, vld_id) VALUES (?, ?)", (data['c_name'], vld_id), commit=True)
        await m.answer(f"✅ Клуб **{data['c_name']}** успешно добавлен!", reply_markup=main_kb(m.from_user.id))
        await state.clear()
    except ValueError:
        await m.answer("❌ Ошибка! ID должен состоять только из цифр. Попробуйте еще раз:")

# --- ИЗМЕНЕНИЕ КЛУБА (ПОЛНАЯ ЛОГИКА) ---
@dp.callback_query(F.data == "adm_edit_club")
async def edit_club_main(c: types.CallbackQuery, state: FSMContext):
    clubs = db_query("SELECT id, name FROM clubs")
    if not clubs:
        return await c.answer("❌ Сначала добавьте клубы!", show_alert=True)
    
    builder = InlineKeyboardBuilder()
    for cid, name in clubs:
        builder.button(text=f"⚙️ {name}", callback_data=f"edit_target_{cid}")
    builder.adjust(2)
    await c.message.edit_text("Выберите клуб, который хотите изменить:", reply_markup=builder.as_markup())
    await state.set_state(Form.edit_club_select)

@dp.callback_query(F.data.startswith("edit_target_"), Form.edit_club_select)
async def edit_club_menu(c: types.CallbackQuery, state: FSMContext):
    club_id = c.data.split("_")[2]
    await state.update_data(target_cid=club_id)
    
    builder = InlineKeyboardBuilder()
    builder.button(text="📝 Изменить название", callback_data="change_name")
    builder.button(text="👤 Изменить ВЛД (ID)", callback_data="change_vld")
    builder.button(text="➕ Добавить зама (ID)", callback_data="change_addzam")
    builder.button(text="➖ Удалить зама (ID)", callback_data="change_delzam")
    builder.button(text="⬅️ Назад", callback_data="adm_edit_club")
    builder.adjust(1)
    
    club_info = db_query("SELECT name, vld_id, zams FROM clubs WHERE id=?", (club_id,), True)
    await c.message.edit_text(f"Клуб: **{club_info[0]}**\nВЛД: `{club_info[1]}`\nЗамы: `{club_info[2] if club_info[2] else 'Нет'}`\n\nЧто изменить?", reply_markup=builder.as_markup())
    await state.set_state(Form.edit_club_choice)

@dp.callback_query(F.data.startswith("change_"), Form.edit_club_choice)
async def edit_club_input(c: types.CallbackQuery, state: FSMContext):
    action = c.data
    await state.update_data(edit_action=action)
    
    prompts = {
        "change_name": "Введите новое название клуба:",
        "change_vld": "Введите новый ID владельца:",
        "change_addzam": "Введите ID зама, которого нужно ДОБАВИТЬ:",
        "change_delzam": "Введите ID зама, которого нужно УДАЛИТЬ:"
    }
    await c.message.answer(prompts[action])
    await state.set_state(Form.edit_club_input)

@dp.message(Form.edit_club_input)
async def edit_club_final(m: types.Message, state: FSMContext):
    data = await state.get_data()
    cid = data['target_cid']
    action = data['edit_action']
    val = m.text
    
    if action == "change_name":
        db_query("UPDATE clubs SET name=? WHERE id=?", (val, cid), commit=True)
    elif action == "change_vld":
        db_query("UPDATE clubs SET vld_id=? WHERE id=?", (val, cid), commit=True)
    elif action == "change_addzam":
        current = db_query("SELECT zams FROM clubs WHERE id=?", (cid,), True)[0]
        new_zams = f"{current},{val}" if current else val
        db_query("UPDATE clubs SET zams=? WHERE id=?", (new_zams, cid), commit=True)
    elif action == "change_delzam":
        current = db_query("SELECT zams FROM clubs WHERE id=?", (cid,), True)[0]
        z_list = current.split(",") if current else []
        if val in z_list:
            z_list.remove(val)
            db_query("UPDATE clubs SET zams=? WHERE id=?", (",".join(z_list), cid), commit=True)
    
    await m.answer("✅ Изменения сохранены!", reply_markup=main_kb(m.from_user.id))
    await state.clear()

# --- СОЗДАНИЕ МАТЧА (ИСПРАВЛЕНО) ---
@dp.callback_query(F.data == "adm_make_match")
async def make_match_1(c: types.CallbackQuery, state: FSMContext):
    clubs = db_query("SELECT id, name FROM clubs")
    if not clubs or len(clubs) < 2:
        return await c.answer("❌ Нужно минимум 2 клуба в базе!", show_alert=True)
    
    builder = InlineKeyboardBuilder()
    for cid, name in clubs:
        builder.button(text=name, callback_data=f"match1_{cid}")
    builder.adjust(2)
    await c.message.edit_text("Выберите ПЕРВУЮ команду:", reply_markup=builder.as_markup())
    await state.set_state(Form.m_t1)

@dp.callback_query(F.data.startswith("match1_"), Form.m_t1)
async def make_match_2(c: types.CallbackQuery, state: FSMContext):
    t1_id = c.data.split("_")[1]
    await state.update_data(t1=t1_id)
    
    clubs = db_query("SELECT id, name FROM clubs WHERE id != ?", (t1_id,))
    builder = InlineKeyboardBuilder()
    for cid, name in clubs:
        builder.button(text=name, callback_data=f"match2_{cid}")
    builder.adjust(2)
    await c.message.edit_text("Выберите ВТОРУЮ команду:", reply_markup=builder.as_markup())
    await state.set_state(Form.m_t2)

@dp.callback_query(F.data.startswith("match2_"), Form.m_t2)
async def make_match_3(c: types.CallbackQuery, state: FSMContext):
    t2_id = c.data.split("_")[1]
    await state.update_data(t2=t2_id)
    await c.message.answer("Введите время матча (например, 12:05):")
    await state.set_state(Form.m_time)

@dp.message(Form.m_time)
async def make_match_4(m: types.Message, state: FSMContext):
    data = await state.get_data()
    t1_id, t2_id = data['t1'], data['t2']
    
    t1_name = db_query("SELECT name FROM clubs WHERE id=?", (t1_id,), True)[0]
    t2_name = db_query("SELECT name FROM clubs WHERE id=?", (t2_id,), True)[0]
    
    text = f"🏟 • Отпись на матч:\n\n{t1_name} — ❌\n{t2_name} — ❌\n\nОтпись в бота: {BOT_USERNAME}"
    
    try:
        msg = await bot.send_message(CHANNEL_ID, text)
        db_query("INSERT INTO matches (t1_id, t2_id, time, msg_id) VALUES (?, ?, ?, ?)", 
                 (t1_id, t2_id, m.text, msg.message_id), commit=True)
        await m.answer(f"✅ Матч {t1_name} vs {t2_name} создан!", reply_markup=main_kb(m.from_user.id))
    except Exception as e:
        await m.answer(f"❌ Ошибка отправки в канал: {e}")
    await state.clear()

# --- ЛОГИКА ТАБОВ (СТРОГАЯ) ---
@dp.message(F.text == "📸 Дать табы")
async def tabs_start(m: types.Message, state: FSMContext):
    # Показываем только те матчи, где уже была отпись (чтобы не путаться)
    matches = db_query("SELECT id, t1_id, t2_id FROM matches WHERE otpis1=1 AND otpis2=1")
    if not matches:
        return await m.answer("❌ Нет активных матчей, на которые можно дать табы.")
    
    builder = InlineKeyboardBuilder()
    for mid, t1id, t2id in matches:
        t1n = db_query("SELECT name FROM clubs WHERE id=?", (t1id,), True)[0]
        t2n = db_query("SELECT name FROM clubs WHERE id=?", (t2id,), True)[0]
        builder.button(text=f"{t1n} vs {t2n}", callback_data=f"give_tab_{mid}")
    builder.adjust(1)
    await m.answer("Выберите матч для отправки табов:", reply_markup=builder.as_markup())
    await state.set_state(Form.tab_match_select)

@dp.callback_query(F.data.startswith("give_tab_"), Form.tab_match_select)
async def tabs_auth_check(c: types.CallbackQuery, state: FSMContext):
    mid = c.data.split("_")[2]
    m_data = db_query("SELECT t1_id, t2_id FROM matches WHERE id=?", (mid,), True)
    uid = str(c.from_user.id)
    
    # Информация о клубах
    c1 = db_query("SELECT vld_id, zams, name FROM clubs WHERE id=?", (m_data[0],), True)
    c2 = db_query("SELECT vld_id, zams, name FROM clubs WHERE id=?", (m_data[1],), True)
    
    auth, club_name = False, ""
    if uid == str(c1[0]) or uid in str(c1[1]).split(","): 
        auth, club_name = True, c1[2]
    elif uid == str(c2[0]) or uid in str(c2[1]).split(","): 
        auth, club_name = True, c2[2]
        
    if not auth:
        return await c.answer("❌ Вы не являетесь ВЛД или Замом клубов этого матча!", show_alert=True)
    
    await state.update_data(tab_mid=mid, tab_club=club_name)
    await c.message.answer(f"Клуб: **{club_name}**\nПожалуйста, отправьте скриншот **1 ТАЙМА**:")
    await state.set_state(Form.tab_photo1)

@dp.message(Form.tab_photo1, F.photo)
async def tabs_photo1_receive(m: types.Message, state: FSMContext):
    await state.update_data(photo1=m.photo[-1].file_id)
    await m.answer("Скриншот 1 тайма принят. Теперь отправьте скриншот **2 ТАЙМА**:")
    await state.set_state(Form.tab_photo2)

@dp.message(Form.tab_photo2, F.photo)
async def tabs_photo2_receive(m: types.Message, state: FSMContext):
    data = await state.get_data()
    p1 = data['photo1']
    p2 = m.photo[-1].file_id
    club = data['tab_club']
    
    # Отправка админам
    for aid in SUPER_ADMINS:
        try:
            await bot.send_message(aid, f"📸 **НОВЫЕ ТАБЫ**\nКлуб: {club}\nОт: {m.from_user.full_name}")
            await bot.send_photo(aid, p1, caption="1-й Тайм")
            await bot.send_photo(aid, p2, caption="2-й Тайм")
        except: pass
        
    await m.answer("✅ Все табы успешно переданы администрации!", reply_markup=main_kb(m.from_user.id))
    await state.clear()

# --- ОТПИСЬ ---
@dp.message(F.text == "📝 Дать отпись")
async def give_otpis(m: types.Message):
    matches = db_query("SELECT id, t1_id, t2_id FROM matches WHERE otpis1=0 OR otpis2=0")
    if not matches: return await m.answer("На данный момент нет матчей для отписи.")
    
    builder = InlineKeyboardBuilder()
    for mid, t1, t2 in matches:
        t1n = db_query("SELECT name FROM clubs WHERE id=?", (t1,), True)[0]
        t2n = db_query("SELECT name FROM clubs WHERE id=?", (t2,), True)[0]
        builder.button(text=f"{t1n} vs {t2n}", callback_data=f"otp_{mid}")
    builder.adjust(1)
    await m.answer("Выберите ваш матч:", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("otp_"))
async def process_otpis(c: types.CallbackQuery):
    mid = c.data.split("_")[1]
    m_data = db_query("SELECT * FROM matches WHERE id=?", (mid,), True)
    uid = c.from_user.id
    
    c1 = db_query("SELECT vld_id, zams FROM clubs WHERE id=?", (m_data[1],), True)
    c2 = db_query("SELECT vld_id, zams FROM clubs WHERE id=?", (m_data[2],), True)
    
    column = None
    if str(uid) == str(c1[0]) or str(uid) in str(c1[1]): column = "otpis1"
    elif str(uid) == str(c2[0]) or str(uid) in str(c2[1]): column = "otpis2"
    
    if not column: return await c.answer("❌ Вы не имеете прав отписываться за эти команды!", show_alert=True)
    
    db_query(f"UPDATE matches SET {column}=1 WHERE id=?", (mid,), commit=True)
    await c.answer("✅ Отпись принята!")
    
    # Обновление поста в канале
    m_new = db_query("SELECT * FROM matches WHERE id=?", (mid,), True)
    t1n = db_query("SELECT name FROM clubs WHERE id=?", (m_new[1],), True)[0]
    t2n = db_query("SELECT name FROM clubs WHERE id=?", (m_new[2],), True)[0]
    s1, s2 = ("✅" if m_new[4] else "❌"), ("✅" if m_new[5] else "❌")
    
    new_text = f"🏟 • Отпись на матч:\n\n{t1n} — {s1}\n{t2n} — {s2}\n\nОтпись в бота: {BOT_USERNAME}"
    try:
        await bot.edit_message_text(new_text, CHANNEL_ID, m_new[6])
    except: pass
    
    # Если оба отписались — рандомный VIP
    if m_new[4] and m_new[5]:
        v1 = db_query("SELECT vld_id FROM clubs WHERE id=?", (m_new[1],), True)[0]
        v2 = db_query("SELECT vld_id FROM clubs WHERE id=?", (m_new[2],), True)[0]
        winner = random.choice([v1, v2])
        db_query("UPDATE matches SET vip_waiter=? WHERE id=?", (v1 if winner==v2 else v2, mid), commit=True)
        await bot.send_message(winner, "🎲 Выпал ваш жребий! Вы делаете VIP.\nНапишите в чат: вип:ВашНик")

# --- ПРОЧИЕ АДМИН КОМАНДЫ ---
@dp.callback_query(F.data == "adm_del_club")
async def del_club_list(c: types.CallbackQuery):
    clubs = db_query("SELECT id, name FROM clubs")
    builder = InlineKeyboardBuilder()
    for cid, name in clubs:
        builder.button(text=f"🗑 {name}", callback_data=f"final_del_{cid}")
    builder.adjust(1)
    await c.message.edit_text("Выберите клуб для УДАЛЕНИЯ:", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("final_del_"))
async def del_club_finish(c: types.CallbackQuery):
    db_query("DELETE FROM clubs WHERE id=?", (c.data.split("_")[2],), commit=True)
    await c.answer("Клуб удален")
    await c.message.delete()

@dp.callback_query(F.data == "adm_give_role")
async def give_role_1(c: types.CallbackQuery, state: FSMContext):
    await c.message.answer("Введите Telegram ID будущего админа:")
    await state.set_state(Form.give_admin_id)

@dp.message(Form.give_admin_id)
async def give_role_2(m: types.Message, state: FSMContext):
    db_query("INSERT OR IGNORE INTO users (user_id, role) VALUES (?, 'admin')", (m.text,), commit=True)
    await m.answer(f"✅ Пользователь {m.text} теперь админ.")
    await state.clear()

@dp.message(F.text.startswith("вип:"))
async def handle_vip(m: types.Message):
    match = db_query("SELECT vip_waiter FROM matches WHERE vip_waiter IS NOT NULL ORDER BY id DESC LIMIT 1", fetchone=True)
    if match:
        kb = InlineKeyboardBuilder().button(text="Готово ✅", callback_data="ready_go").as_markup()
        await bot.send_message(match[0], f"📩 VIP ПРИШЕЛ:\n{m.text}", reply_markup=kb)
        await m.answer("✅ VIP отправлен сопернику!")

@dp.callback_query(F.data == "ready_go")
async def match_ready(c: types.CallbackQuery):
    await c.message.edit_text(c.message.text + "\n\n🚀 МАТЧ НАЧАЛСЯ!")

# --- ЗАПУСК ---
async def main():
    init_db()
    # Удаляем старые команды и ставим новые
    await bot.set_my_commands([BotCommand(command="start", description="Запустить бота")])
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
