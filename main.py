import asyncio
import sqlite3
import random
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from aiogram.types import InlineKeyboardButton

# ================= НАСТРОЙКИ =================
TOKEN = "8633419537:AAF6r1H1YtfI2whTHVdKzF2JVQnxgu9XfU4"
CHANNEL_ID = "@pistonCUPsls"
SUPER_ADMINS = [5845609895, 6740071266]
BOT_USERNAME = "@TernatLeague_Bot"

bot = Bot(token=TOKEN)
dp = Dispatcher()
logging.basicConfig(level=logging.INFO)

# ================= БАЗА ДАННЫХ =================
def init_db():
    conn = sqlite3.connect('league_data.db')
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, role TEXT)")
    cur.execute("CREATE TABLE IF NOT EXISTS clubs (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, vld_id INTEGER, zams TEXT DEFAULT '')")
    cur.execute("""CREATE TABLE IF NOT EXISTS matches (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        t1_id INTEGER, t2_id INTEGER, 
        time TEXT, otpis1 INTEGER DEFAULT 0, 
        otpis2 INTEGER DEFAULT 0, msg_id INTEGER, vip_waiter INTEGER)""")
    cur.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
    conn.commit()
    conn.close()

def db_query(query, params=(), fetchone=False, commit=False):
    conn = sqlite3.connect('league_data.db')
    cur = conn.cursor()
    cur.execute(query, params)
    if commit: conn.commit()
    res = cur.fetchone() if fetchone else cur.fetchall()
    conn.close()
    return res

# ================= СОСТОЯНИЯ (FSM) =================
class Form(StatesGroup):
    add_club_name = State()
    add_club_vld = State()
    edit_schedule = State()
    m_t1 = State()
    m_t2 = State()
    m_time = State()
    # Табы
    tab_match_select = State()
    tab_photo1 = State()
    tab_photo2 = State()
    # Управление клубами
    edit_club_select = State()
    edit_club_choice = State()
    edit_club_input = State()
    # Админка
    give_admin_id = State()
    remove_admin_id = State()

# ================= КЛАВИАТУРЫ =================
def main_kb(uid):
    b = ReplyKeyboardBuilder()
    b.button(text="📅 Расписание матчей")
    b.button(text="📝 Дать отпись")
    b.button(text="📸 Дать табы")
    role = db_query("SELECT role FROM users WHERE user_id=?", (uid,), True)
    if uid in SUPER_ADMINS or role:
        b.button(text="⚙️ Админ панель")
    b.adjust(2)
    return b.as_markup(resize_keyboard=True)

def admin_kb(uid):
    b = InlineKeyboardBuilder()
    b.button(text="🏠 Добавить клуб", callback_data="adm_add_club")
    b.button(text="✏️ Изменить клуб", callback_data="adm_edit_club")
    b.button(text="⚽ Создать матч", callback_data="adm_make_match")
    b.button(text="📅 Изменить расписание", callback_data="adm_edit_sched")
    b.button(text="🗑 Удалить клуб", callback_data="adm_del_club")
    if uid in SUPER_ADMINS:
        b.button(text="👑 Дать админку", callback_data="adm_give_role")
        b.button(text="❌ Убрать админа", callback_data="adm_remove_role")
    b.adjust(1)
    return b.as_markup()

# ================= ОБРАБОТЧИКИ =================

@dp.message(Command("start"))
async def cmd_start(m: types.Message):
    init_db()
    await m.answer("⚽ Система лиги готова к работе!", reply_markup=main_kb(m.from_user.id))

# --- РАСПИСАНИЕ ---
@dp.message(F.text == "📅 Расписание матчей")
async def show_sched(m: types.Message):
    res = db_query("SELECT value FROM settings WHERE key='schedule'", fetchone=True)
    await m.answer(res[0] if res else "Расписание еще не установлено.")

@dp.callback_query(F.data == "adm_edit_sched")
async def edit_sched_start(c: types.CallbackQuery, state: FSMContext):
    await c.message.answer("Введите новый текст расписания:")
    await state.set_state(Form.edit_schedule)

@dp.message(Form.edit_schedule)
async def edit_sched_finish(m: types.Message, state: FSMContext):
    db_query("INSERT OR REPLACE INTO settings (key, value) VALUES ('schedule', ?)", (m.text,), commit=True)
    await m.answer("✅ Расписание обновлено!", reply_markup=main_kb(m.from_user.id))
    await state.clear()

# --- УПРАВЛЕНИЕ КЛУБАМИ (Изменить клуб) ---
@dp.callback_query(F.data == "adm_edit_club")
async def edit_club_start(c: types.CallbackQuery, state: FSMContext):
    clubs = db_query("SELECT id, name FROM clubs")
    if not clubs: return await c.answer("Клубов нет!")
    kb = InlineKeyboardBuilder()
    for cid, name in clubs: kb.button(text=name, callback_data=f"edcl_{cid}")
    kb.adjust(2)
    await c.message.edit_text("Выберите клуб для редактирования:", reply_markup=kb.as_markup())
    await state.set_state(Form.edit_club_select)

@dp.callback_query(F.data.startswith("edcl_"), Form.edit_club_select)
async def edit_club_menu(c: types.CallbackQuery, state: FSMContext):
    cid = c.data.split("_")[1]
    await state.update_data(edit_cid=cid)
    kb = InlineKeyboardBuilder()
    kb.button(text="Название", callback_data="upd_name")
    kb.button(text="ВЛД (ID)", callback_data="upd_vld")
    kb.button(text="+ Зам (ID)", callback_data="upd_addzam")
    kb.button(text="- Зам (ID)", callback_data="upd_delzam")
    kb.button(text="⬅️ Назад", callback_data="adm_edit_club")
    kb.adjust(2)
    await c.message.edit_text("Что изменить в клубе?", reply_markup=kb.as_markup())
    await state.set_state(Form.edit_club_choice)

@dp.callback_query(F.data.startswith("upd_"), Form.edit_club_choice)
async def edit_club_input_req(c: types.CallbackQuery, state: FSMContext):
    await state.update_data(edit_type=c.data)
    await c.message.answer("Введите новое значение:")
    await state.set_state(Form.edit_club_input)

@dp.message(Form.edit_club_input)
async def edit_club_final(m: types.Message, state: FSMContext):
    data = await state.get_data()
    cid, etype, val = data['edit_cid'], data['edit_type'], m.text
    
    if etype == "upd_name":
        db_query("UPDATE clubs SET name=? WHERE id=?", (val, cid), commit=True)
    elif etype == "upd_vld":
        db_query("UPDATE clubs SET vld_id=? WHERE id=?", (val, cid), commit=True)
    elif etype == "upd_addzam":
        cur = db_query("SELECT zams FROM clubs WHERE id=?", (cid,), True)[0]
        new = f"{cur},{val}" if cur else val
        db_query("UPDATE clubs SET zams=? WHERE id=?", (new, cid), commit=True)
    elif etype == "upd_delzam":
        cur = db_query("SELECT zams FROM clubs WHERE id=?", (cid,), True)[0]
        z_list = cur.split(",") if cur else []
        if val in z_list: z_list.remove(val)
        db_query("UPDATE clubs SET zams=? WHERE id=?", (",".join(z_list), cid), commit=True)
        
    await m.answer("✅ Данные клуба обновлены!", reply_markup=main_kb(m.from_user.id))
    await state.clear()

# --- ЛОГИКА ТАБОВ (СТРОГАЯ) ---
@dp.message(F.text == "📸 Дать табы")
async def tabs_start(m: types.Message, state: FSMContext):
    # Берем матчи, которые уже прошли или идут (где есть отписи)
    matches = db_query("SELECT id, t1_id, t2_id FROM matches WHERE otpis1=1 AND otpis2=1")
    if not matches:
        return await m.answer("❌ Активных матчей с подтвержденной отписью не найдено.")
    
    kb = InlineKeyboardBuilder()
    count = 0
    for mid, t1id, t2id in matches:
        t1n = db_query("SELECT name FROM clubs WHERE id=?", (t1id,), True)[0]
        t2n = db_query("SELECT name FROM clubs WHERE id=?", (t2id,), True)[0]
        kb.button(text=f"{t1n} vs {t2n}", callback_data=f"tabm_{mid}")
        count += 1
    
    if count == 0:
        return await m.answer("❌ Нет подходящих матчей.")
        
    kb.adjust(1)
    await m.answer("Выберите матч, по которому хотите дать табы:", reply_markup=kb.as_markup())
    await state.set_state(Form.tab_match_select)

@dp.callback_query(F.data.startswith("tabm_"), Form.tab_match_select)
async def tabs_check_auth(c: types.CallbackQuery, state: FSMContext):
    mid = c.data.split("_")[1]
    match = db_query("SELECT t1_id, t2_id FROM matches WHERE id=?", (mid,), True)
    uid = str(c.from_user.id)
    
    # Проверка: является ли юзер ВЛД или Замом одной из команд матча
    c1 = db_query("SELECT vld_id, zams, name FROM clubs WHERE id=?", (match[0],), True)
    c2 = db_query("SELECT vld_id, zams, name FROM clubs WHERE id=?", (match[1],), True)
    
    is_auth = False
    club_name = ""
    if uid == str(c1[0]) or uid in c1[1].split(","): 
        is_auth = True
        club_name = c1[2]
    elif uid == str(c2[0]) or uid in c2[1].split(","): 
        is_auth = True
        club_name = c2[2]
        
    if not is_auth:
        await c.answer("❌ Вы не являетесь ВЛД или Замом клубов этого матча!", show_alert=True)
        return

    await state.update_data(tab_mid=mid, tab_club=club_name)
    await c.message.answer(f"Клуб: {club_name}\nОтправьте сначала фото 1 тайма:")
    await state.set_state(Form.tab_photo1)

@dp.message(Form.tab_photo1, F.photo)
async def tabs_p1(m: types.Message, state: FSMContext):
    await state.update_data(p1=m.photo[-1].file_id)
    await m.answer("Отлично. Теперь отправьте фото 2 тайма:")
    await state.set_state(Form.tab_photo2)

@dp.message(Form.tab_photo2, F.photo)
async def tabs_p2(m: types.Message, state: FSMContext):
    data = await state.get_data()
    p1 = data['p1']
    p2 = m.photo[-1].file_id
    club = data['tab_club']
    
    # Отправка админам
    for aid in SUPER_ADMINS:
        try:
            await bot.send_message(aid, f"📸 ТАБЫ: {club}\nОт: {m.from_user.full_name}")
            await bot.send_photo(aid, p1, caption="1 Тайм")
            await bot.send_photo(aid, p2, caption="2 Тайм")
        except: pass
        
    await m.answer("✅ Табы успешно переданы администрации!", reply_markup=main_kb(m.from_user.id))
    await state.clear()

# --- ВСЁ ОСТАЛЬНОЕ (БЕЗ СОКРАЩЕНИЙ) ---

@dp.callback_query(F.data == "adm_add_club")
async def add_club_1(c: types.CallbackQuery, state: FSMContext):
    await c.message.answer("Введите название клуба:")
    await state.set_state(Form.add_club_name)

@dp.message(Form.add_club_name)
async def add_club_2(m: types.Message, state: FSMContext):
    await state.update_data(name=m.text)
    await m.answer("Введите Telegram ID владельца (ВЛД):")
    await state.set_state(Form.add_club_vld)

@dp.message(Form.add_club_vld)
async def add_club_3(m: types.Message, state: FSMContext):
    data = await state.get_data()
    db_query("INSERT INTO clubs (name, vld_id) VALUES (?, ?)", (data['name'], int(m.text)), commit=True)
    await m.answer(f"✅ Клуб {data['name']} добавлен!", reply_markup=main_kb(m.from_user.id))
    await state.clear()

@dp.callback_query(F.data == "adm_make_match")
async def make_m_1(c: types.CallbackQuery, state: FSMContext):
    clubs = db_query("SELECT id, name FROM clubs")
    if len(clubs) < 2: return await c.answer("Нужно минимум 2 клуба!")
    kb = InlineKeyboardBuilder()
    for cid, name in clubs: kb.button(text=name, callback_data=f"mt1_{cid}")
    kb.adjust(2)
    await c.message.edit_text("Команда 1:", reply_markup=kb.as_markup())
    await state.set_state(Form.m_t1)

@dp.callback_query(F.data.startswith("mt1_"))
async def make_m_2(c: types.CallbackQuery, state: FSMContext):
    await state.update_data(t1=c.data.split("_")[1])
    clubs = db_query("SELECT id, name FROM clubs WHERE id != ?", (c.data.split("_")[1],))
    kb = InlineKeyboardBuilder()
    for cid, name in clubs: kb.button(text=name, callback_data=f"mt2_{cid}")
    await c.message.edit_text("Команда 2:", reply_markup=kb.as_markup())
    await state.set_state(Form.m_t2)

@dp.callback_query(F.data.startswith("mt2_"))
async def make_m_3(c: types.CallbackQuery, state: FSMContext):
    await state.update_data(t2=c.data.split("_")[1])
    await c.message.answer("Время матча:")
    await state.set_state(Form.m_time)

@dp.message(Form.m_time)
async def make_m_4(m: types.Message, state: FSMContext):
    data = await state.get_data()
    t1n = db_query("SELECT name FROM clubs WHERE id=?", (data['t1'],), True)[0]
    t2n = db_query("SELECT name FROM clubs WHERE id=?", (data['t2'],), True)[0]
    text = f"🏟 • Отпись на матч:\n\n{t1n} — ❌\n{t2n} — ❌\n\nОтпись в бота: {BOT_USERNAME}"
    msg = await bot.send_message(CHANNEL_ID, text)
    db_query("INSERT INTO matches (t1_id, t2_id, time, msg_id) VALUES (?, ?, ?, ?)", 
             (data['t1'], data['t2'], m.text, msg.message_id), commit=True)
    await m.answer("✅ Матч создан!")
    await state.clear()

@dp.message(F.text == "📝 Дать отпись")
async def give_otpis(m: types.Message):
    matches = db_query("SELECT id, t1_id, t2_id FROM matches WHERE otpis1=0 OR otpis2=0")
    if not matches: return await m.answer("Нет матчей.")
    kb = InlineKeyboardBuilder()
    for mid, t1, t2 in matches:
        t1n = db_query("SELECT name FROM clubs WHERE id=?", (t1,), True)[0]
        t2n = db_query("SELECT name FROM clubs WHERE id=?", (t2,), True)[0]
        kb.button(text=f"{t1n} vs {t2n}", callback_data=f"otpis_{mid}")
    await m.answer("Выберите матч:", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("otpis_"))
async def proc_otpis(c: types.CallbackQuery):
    mid = c.data.split("_")[1]
    m_data = db_query("SELECT * FROM matches WHERE id=?", (mid,), True)
    uid = c.from_user.id
    c1 = db_query("SELECT vld_id, zams FROM clubs WHERE id=?", (m_data[1],), True)
    c2 = db_query("SELECT vld_id, zams FROM clubs WHERE id=?", (m_data[2],), True)
    col = None
    if uid == c1[0] or str(uid) in str(c1[1]): col = "otpis1"
    elif uid == c2[0] or str(uid) in str(c2[1]): col = "otpis2"
    if not col: return await c.answer("Вы не ВЛД/Зам!", show_alert=True)
    db_query(f"UPDATE matches SET {col}=1 WHERE id=?", (mid,), commit=True)
    await c.answer("Отпись принята")
    m_new = db_query("SELECT * FROM matches WHERE id=?", (mid,), True)
    t1n = db_query("SELECT name FROM clubs WHERE id=?", (m_new[1],), True)[0]
    t2n = db_query("SELECT name FROM clubs WHERE id=?", (m_new[2],), True)[0]
    s1, s2 = ("✅" if m_new[4] else "❌"), ("✅" if m_new[5] else "❌")
    new_text = f"🏟 • Отпись на матч:\n\n{t1n} — {s1}\n{t2n} — {s2}\n\nОтпись в бота: {BOT_USERNAME}"
    try: await bot.edit_message_text(new_text, CHANNEL_ID, m_new[6])
    except: pass
    if m_new[4] and m_new[5]:
        v1 = db_query("SELECT vld_id FROM clubs WHERE id=?", (m_new[1],), True)[0]
        v2 = db_query("SELECT vld_id FROM clubs WHERE id=?", (m_new[2],), True)[0]
        winner = random.choice([v1, v2])
        db_query("UPDATE matches SET vip_waiter=? WHERE id=?", (v1 if winner==v2 else v2, mid), commit=True)
        await bot.send_message(winner, "🎲 Вы делаете VIP! Формат: вип:Ник")

@dp.message(F.text.startswith("вип:"))
async def send_vip(m: types.Message):
    match_v = db_query("SELECT id, vip_waiter FROM matches WHERE vip_waiter IS NOT NULL ORDER BY id DESC LIMIT 1", fetchone=True)
    if match_v:
        kb = InlineKeyboardBuilder().button(text="Готово ✅", callback_data="ready").as_markup()
        await bot.send_message(match_v[1], f"📩 VIP от соперника:\n{m.text}", reply_markup=kb)
        await m.answer("✅ Отправлено!")

@dp.callback_query(F.data == "ready")
async def ready(c: types.CallbackQuery):
    await c.message.edit_text(c.message.text + "\n\n✅ Игра началась!")

@dp.message(F.text == "⚙️ Админ панель")
async def adm_p(m: types.Message):
    role = db_query("SELECT role FROM users WHERE user_id=?", (m.from_user.id,), True)
    if m.from_user.id in SUPER_ADMINS or role:
        await m.answer("⚙️ Админка:", reply_markup=admin_kb(m.from_user.id))

@dp.callback_query(F.data == "adm_give_role")
async def give_r(c: types.CallbackQuery, state: FSMContext):
    await c.message.answer("ID нового админа:")
    await state.set_state(Form.give_admin_id)

@dp.message(Form.give_admin_id)
async def give_r_f(m: types.Message, state: FSMContext):
    db_query("INSERT OR IGNORE INTO users (user_id, role) VALUES (?, 'admin')", (int(m.text),), commit=True)
    await m.answer("Готово")
    await state.clear()

@dp.callback_query(F.data == "adm_del_club")
async def del_c(c: types.CallbackQuery):
    clubs = db_query("SELECT id, name FROM clubs")
    kb = InlineKeyboardBuilder()
    for cid, name in clubs: kb.button(text=f"Удалить {name}", callback_data=f"delc_{cid}")
    await c.message.edit_text("Удаление:", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("delc_"))
async def del_c_f(c: types.CallbackQuery):
    db_query("DELETE FROM clubs WHERE id=?", (c.data.split("_")[1],), commit=True)
    await c.answer("Удалено")

async def main():
    init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
