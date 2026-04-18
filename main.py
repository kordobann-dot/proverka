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

# ================= НАЛАШТУВАННЯ =================
TOKEN = "8633419537:AAF6r1H1YtfI2whTHVdKzF2JVQnxgu9XfU4"
CHANNEL_ID = "@pistonCUPsls"  # Канал, де буде отпись
SUPER_ADMIN_ID = 6386447833   # Твій особистий Telegram ID
BOT_USERNAME = "@TernatLeague_Bot"

bot = Bot(token=TOKEN)
dp = Dispatcher()
logging.basicConfig(level=logging.INFO)

# ================= БАЗА ДАНИХ =================
def init_db():
    conn = sqlite3.connect('league_data.db')
    cur = conn.cursor()
    # Таблиця користувачів (адмінів)
    cur.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, role TEXT)")
    # Таблиця клубів
    cur.execute("CREATE TABLE IF NOT EXISTS clubs (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, vld_id INTEGER, zams TEXT DEFAULT '')")
    # Таблиця матчів
    cur.execute("""CREATE TABLE IF NOT EXISTS matches (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        t1_id INTEGER, t2_id INTEGER, 
        time TEXT, otpis1 INTEGER DEFAULT 0, 
        otpis2 INTEGER DEFAULT 0, msg_id INTEGER, vip_waiter INTEGER)""")
    # Налаштування
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

# ================= СТАНИ (FSM) =================
class Form(StatesGroup):
    add_club_name = State()
    add_club_vld = State()
    edit_club_select = State()
    edit_club_action = State()
    edit_schedule = State()
    m_t1 = State()
    m_t2 = State()
    m_time = State()
    giving_tab = State()

# ================= КЛАВІАТУРИ =================
def main_kb(uid):
    b = ReplyKeyboardBuilder()
    b.button(text="📅 Расписание матчей")
    b.button(text="📝 Дать отпись")
    b.button(text="📸 Дать табы")
    role = db_query("SELECT role FROM users WHERE user_id=?", (uid,), True)
    if uid == SUPER_ADMIN_ID or role:
        b.button(text="⚙️ Админ панель")
    b.adjust(2)
    return b.as_markup(resize_keyboard=True)

def admin_kb(uid):
    b = InlineKeyboardBuilder()
    b.button(text="🏠 Добавить клуб", callback_data="adm_add_club")
    b.button(text="✏️ Изменить клуб", callback_data="adm_edit_club")
    b.button(text="⚽ Сделать матч", callback_data="adm_make_match")
    b.button(text="📅 Изменить расписание", callback_data="adm_edit_sched")
    b.button(text="🗑 Удалить клуб", callback_data="adm_del_club")
    if uid == SUPER_ADMIN_ID:
        b.button(text="👑 Дать админку", callback_data="adm_give_admin")
    b.adjust(1)
    return b.as_markup()

# ================= ОБРОБНИКИ =================

@dp.message(Command("start"))
async def cmd_start(m: types.Message):
    init_db()
    await m.answer("⚽ Система керування лігою запущена!", reply_markup=main_kb(m.from_user.id))

# --- РОЗКЛАД ---
@dp.message(F.text == "📅 Расписание матчей")
async def show_sched(m: types.Message):
    res = db_query("SELECT value FROM settings WHERE key='schedule'", fetchone=True)
    await m.answer(res[0] if res else "Розклад ще не встановлено.")

@dp.callback_query(F.data == "adm_edit_sched")
async def edit_sched_start(c: types.CallbackQuery, state: FSMContext):
    await c.message.answer("Введіть новий текст розкладу:")
    await state.set_state(Form.edit_schedule)

@dp.message(Form.edit_schedule)
async def edit_sched_finish(m: types.Message, state: FSMContext):
    db_query("INSERT OR REPLACE INTO settings (key, value) VALUES ('schedule', ?)", (m.text,), commit=True)
    await m.answer("✅ Розклад оновлено!", reply_markup=main_kb(m.from_user.id))
    await state.clear()

# --- ДОДАВАННЯ КЛУБУ ---
@dp.callback_query(F.data == "adm_add_club")
async def add_club_1(c: types.CallbackQuery, state: FSMContext):
    await c.message.answer("Введіть назву клубу:")
    await state.set_state(Form.add_club_name)

@dp.message(Form.add_club_name)
async def add_club_2(m: types.Message, state: FSMContext):
    await state.update_data(name=m.text)
    await m.answer("Введіть Telegram ID ВЛД (власника):")
    await state.set_state(Form.add_club_vld)

@dp.message(Form.add_club_vld)
async def add_club_3(m: types.Message, state: FSMContext):
    data = await state.get_data()
    db_query("INSERT INTO clubs (name, vld_id) VALUES (?, ?)", (data['name'], int(m.text)), commit=True)
    await m.answer(f"✅ Клуб {data['name']} додано!", reply_markup=main_kb(m.from_user.id))
    await state.clear()

# --- СТВОРЕННЯ МАТЧУ ---
@dp.callback_query(F.data == "adm_make_match")
async def make_m_1(c: types.CallbackQuery, state: FSMContext):
    clubs = db_query("SELECT id, name FROM clubs")
    if len(clubs) < 2: return await c.answer("Треба мінімум 2 клуби!")
    kb = InlineKeyboardBuilder()
    for cid, name in clubs: kb.button(text=name, callback_data=f"mt1_{cid}")
    kb.adjust(2)
    await c.message.edit_text("Оберіть Команду 1:", reply_markup=kb.as_markup())
    await state.set_state(Form.m_t1)

@dp.callback_query(F.data.startswith("mt1_"))
async def make_m_2(c: types.CallbackQuery, state: FSMContext):
    await state.update_data(t1=c.data.split("_")[1])
    clubs = db_query("SELECT id, name FROM clubs WHERE id != ?", (c.data.split("_")[1],))
    kb = InlineKeyboardBuilder()
    for cid, name in clubs: kb.button(text=name, callback_data=f"mt2_{cid}")
    await c.message.edit_text("Оберіть Команду 2:", reply_markup=kb.as_markup())
    await state.set_state(Form.m_t2)

@dp.callback_query(F.data.startswith("mt2_"))
async def make_m_3(c: types.CallbackQuery, state: FSMContext):
    await state.update_data(t2=c.data.split("_")[1])
    await c.message.answer("Введіть час матчу:")
    await state.set_state(Form.m_time)

@dp.message(Form.m_time)
async def make_m_4(m: types.Message, state: FSMContext):
    data = await state.get_data()
    t1_n = db_query("SELECT name FROM clubs WHERE id=?", (data['t1'],), True)[0]
    t2_n = db_query("SELECT name FROM clubs WHERE id=?", (data['t2'],), True)[0]
    
    text = f"🏟 • Отпись на матч:\n\n{t1_n} — ❌\n{t2_n} — ❌\n\nОтпись в бота: {BOT_USERNAME}"
    msg = await bot.send_message(CHANNEL_ID, text)
    
    db_query("INSERT INTO matches (t1_id, t2_id, time, msg_id) VALUES (?, ?, ?, ?)", 
             (data['t1'], data['t2'], m.text, msg.message_id), commit=True)
    await m.answer("✅ Матч опубліковано!")
    await state.clear()

# --- ОТПИСЬ ---
@dp.message(F.text == "📝 Дать отпись")
async def give_otpis(m: types.Message):
    matches = db_query("SELECT id, t1_id, t2_id FROM matches WHERE otpis1=0 OR otpis2=0")
    if not matches: return await m.answer("Актуальних матчів немає.")
    kb = InlineKeyboardBuilder()
    for mid, t1, t2 in matches:
        t1n = db_query("SELECT name FROM clubs WHERE id=?", (t1,), True)[0]
        t2n = db_query("SELECT name FROM clubs WHERE id=?", (t2,), True)[0]
        kb.button(text=f"{t1n} vs {t2n}", callback_data=f"otpis_{mid}")
    await m.answer("Оберіть матч:", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("otpis_"))
async def proc_otpis(c: types.CallbackQuery):
    mid = c.data.split("_")[1]
    m = db_query("SELECT * FROM matches WHERE id=?", (mid,), True)
    uid = c.from_user.id
    
    c1 = db_query("SELECT vld_id, zams FROM clubs WHERE id=?", (m[1],), True)
    c2 = db_query("SELECT vld_id, zams FROM clubs WHERE id=?", (m[2],), True)
    
    col = None
    if uid == c1[0] or str(uid) in c1[1]: col = "otpis1"
    elif uid == c2[0] or str(uid) in c2[1]: col = "otpis2"
    
    if not col: return await c.answer("Ви не ВЛД/Зам цих команд!", show_alert=True)
    
    db_query(f"UPDATE matches SET {col}=1 WHERE id=?", (mid,), commit=True)
    await c.answer("✅ Відписка прийнята!")
    
    # Оновлення каналу
    m_new = db_query("SELECT * FROM matches WHERE id=?", (mid,), True)
    t1n = db_query("SELECT name FROM clubs WHERE id=?", (m_new[1],), True)[0]
    t2n = db_query("SELECT name FROM clubs WHERE id=?", (m_new[2],), True)[0]
    s1 = "✅" if m_new[4] else "❌"
    s2 = "✅" if m_new[5] else "❌"
    
    new_text = f"🏟 • Отпись на матч:\n\n{t1n} — {s1}\n{t2n} — {s2}\n\nОтпись в бота: {BOT_USERNAME}"
    try: await bot.edit_message_text(new_text, CHANNEL_ID, m_new[6])
    except: pass

    # Рандом VIP
    if m_new[4] and m_new[5]:
        v1 = db_query("SELECT vld_id FROM clubs WHERE id=?", (m_new[1],), True)[0]
        v2 = db_query("SELECT vld_id FROM clubs WHERE id=?", (m_new[2],), True)[0]
        winner = random.choice([v1, v2])
        loser = v2 if winner == v1 else v1
        db_query("UPDATE matches SET vip_waiter=? WHERE id=?", (loser, mid), commit=True)
        await bot.send_message(winner, "🎲 Рандом вибрав вас! Напишіть:\nвип:ВашНік")

# --- VIP СИСТЕМА ---
@dp.message(F.text.startswith("вип:"))
async def send_vip(m: types.Message):
    match = db_query("SELECT id, vip_waiter FROM matches WHERE vip_waiter IS NOT NULL ORDER BY id DESC LIMIT 1", fetchone=True)
    if match:
        kb = InlineKeyboardBuilder().button(text="Готово ✅", callback_data="ready").as_markup()
        await bot.send_message(match[1], f"📩 VIP від суперника:\n{m.text}", reply_markup=kb)
        await m.answer("✅ VIP надіслано!")

@dp.callback_query(F.data == "ready")
async def ready(c: types.CallbackQuery):
    await c.message.edit_text(c.message.text + "\n\n✅ Підтверджено!")

# --- ТАБИ ---
@dp.message(F.text == "📸 Дать табы")
async def tab_1(m: types.Message, state: FSMContext):
    is_vld = db_query("SELECT id FROM clubs WHERE vld_id=? OR zams LIKE ?", (m.from_user.id, f"%{m.from_user.id}%"), True)
    if not is_vld: return await m.answer("❌ Ви не ВЛД або Зам!")
    await m.answer("Надішліть фото табів:")
    await state.set_state(Form.giving_tab)

@dp.message(Form.giving_tab, F.photo)
async def tab_2(m: types.Message, state: FSMContext):
    await bot.send_photo(SUPER_ADMIN_ID, m.photo[-1].file_id, caption=f"📸 ТАБИ від {m.from_user.id}")
    await m.answer("✅ Надіслано адмінам!")
    await state.clear()

# --- АДМІН ПАНЕЛЬ ---
@dp.message(F.text == "⚙️ Admin panel")
@dp.message(F.text == "⚙️ Админ панель")
async def adm_p(m: types.Message):
    if m.from_user.id == SUPER_ADMIN_ID or db_query("SELECT role FROM users WHERE user_id=?", (m.from_user.id,), True):
        await m.answer("⚙️ Адмін-панель:", reply_markup=admin_kb(m.from_user.id))

async def main():
    init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
