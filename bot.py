import os
import sqlite3
import random
from datetime import datetime, date, timedelta

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters

import google.generativeai as genai

# ================= AI =================
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-1.5-pro")

# ================= DB =================
conn = sqlite3.connect("bot.db", check_same_thread=False)
c = conn.cursor()

c.execute("""
CREATE TABLE IF NOT EXISTS users(
user_id INTEGER PRIMARY KEY,
accepted INTEGER DEFAULT 0,
daily_msg INTEGER DEFAULT 0,
last_reset TEXT,
vip_until TEXT,
balance REAL DEFAULT 0,
ref_by INTEGER,
invites INTEGER DEFAULT 0,
free_msgs INTEGER DEFAULT 0
)
""")
conn.commit()

LIMIT = 40

# ================= RESET =================
def reset(uid):
    today = str(date.today())
    c.execute("SELECT last_reset FROM users WHERE user_id=?", (uid,))
    r = c.fetchone()

    if not r or r[0] != today:
        c.execute("UPDATE users SET daily_msg=0, last_reset=? WHERE user_id=?", (today, uid))
        conn.commit()

# ================= VIP =================
def is_vip(uid):
    c.execute("SELECT vip_until FROM users WHERE user_id=?", (uid,))
    r = c.fetchone()

    if not r or not r[0]:
        return False

    return datetime.fromisoformat(r[0]) > datetime.now()

def set_vip(uid):
    vip_time = datetime.now() + timedelta(days=30)
    c.execute("UPDATE users SET vip_until=? WHERE user_id=?", (vip_time.isoformat(), uid))
    conn.commit()

# ================= AI LIMIT =================
def can_use(uid):
    reset(uid)

    # free messages first
    c.execute("SELECT free_msgs FROM users WHERE user_id=?", (uid,))
    free = c.fetchone()[0]

    if free > 0:
        c.execute("UPDATE users SET free_msgs = free_msgs - 1 WHERE user_id=?", (uid,))
        conn.commit()
        return True

    if is_vip(uid):
        return True

    c.execute("SELECT daily_msg FROM users WHERE user_id=?", (uid,))
    count = c.fetchone()[0]

    if count >= LIMIT:
        return False

    c.execute("UPDATE users SET daily_msg = daily_msg + 1 WHERE user_id=?", (uid,))
    conn.commit()

    return True

# ================= AI =================
def ask_ai(text):
    try:
        return model.generate_content(text).text
    except:
        return "❌ AI Error"

# ================= MINE =================
def mine(uid):
    reward = random.uniform(0.0001, 0.01)

    if is_vip(uid):
        reward *= 2

    c.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (reward, uid))
    conn.commit()

    return reward

# ================= INVITE =================
def get_link(uid):
    return f"https://t.me/YOUR_BOT_USERNAME?start={uid}"

def register_invite(new_user, ref):
    if new_user == ref:
        return

    c.execute("SELECT ref_by FROM users WHERE user_id=?", (new_user,))
    r = c.fetchone()

    if r and r[0] is None:
        c.execute("""
        UPDATE users
        SET invites = invites + 1,
            free_msgs = free_msgs + 10
        WHERE user_id=?
        """, (ref,))
        conn.commit()

# ================= START =================
async def start(update: Update, context):
    uid = update.effective_user.id

    c.execute("INSERT OR IGNORE INTO users(user_id) VALUES(?)", (uid,))
    conn.commit()

    if context.args:
        ref = int(context.args[0])
        register_invite(uid, ref)

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✔ ورود", callback_data="menu")]
    ])

    await update.message.reply_text("💎 خوش آمدی", reply_markup=keyboard)

# ================= MENU =================
async def menu(update: Update, context):
    q = update.callback_query

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🤖 AI", callback_data="ai")],
        [InlineKeyboardButton("⛏ ماین", callback_data="mine")],
        [InlineKeyboardButton("💰 کیف پول", callback_data="wallet")],
        [InlineKeyboardButton("💎 VIP", callback_data="vip")],
        [InlineKeyboardButton("🤝 دعوت", callback_data="invite")]
    ])

    await q.answer()
    await q.edit_message_text("🎮 منو", reply_markup=keyboard)

# ================= BUTTONS =================
async def buttons(update: Update, context):
    q = update.callback_query
    uid = q.from_user.id
    data = q.data

    if data == "ai":
        context.user_data["ai"] = True
        await q.message.reply_text("💬 سوال بفرست")
        return

    if data == "mine":
        reward = mine(uid)
        await q.message.reply_text(f"⛏ درآمد: {reward:.5f}")
        return

    if data == "wallet":
        c.execute("SELECT balance FROM users WHERE user_id=?", (uid,))
        bal = c.fetchone()[0]
        await q.message.reply_text(f"💰 موجودی: {bal:.5f}")
        return

    if data == "vip":
        set_vip(uid)
        await q.message.reply_text("👑 VIP فعال شد")
        return

    if data == "invite":
        link = get_link(uid)
        await q.message.reply_text(f"🤝 لینک دعوت:\n{link}\n🎁 هر دعوت = 10 پیام رایگان")
        return

# ================= AI CHAT =================
async def handle(update: Update, context):
    uid = update.effective_user.id
    text = update.message.text

    if context.user_data.get("ai"):
        if not can_use(uid):
            await update.message.reply_text("❌ محدودیت پیام تمام شد")
            return

        ans = ask_ai(text)
        await update.message.reply_text(ans)
        return

# ================= RUN =================
app = Application.builder().token(os.getenv("BOT_TOKEN")).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(menu, pattern="menu"))
app.add_handler(CallbackQueryHandler(buttons))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))

app.run_polling()
