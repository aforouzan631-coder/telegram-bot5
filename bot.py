import os
import sqlite3
import random
from datetime import datetime, date, timedelta

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters

import google.generativeai as genai

# ================= AI =================
genai.configure(api_key="YOUR_GEMINI_API_KEY")
model = genai.GenerativeModel("gemini-1.5-pro")

BOT_TOKEN = os.getenv("BOT_TOKEN")

# ================= DB =================
conn = sqlite3.connect("bot.db", check_same_thread=False)
c = conn.cursor()

c.execute("""
CREATE TABLE IF NOT EXISTS users(
user_id INTEGER PRIMARY KEY,
daily_msg INTEGER DEFAULT 0,
last_reset TEXT,
vip_until TEXT,
balance REAL DEFAULT 0,
free_msgs INTEGER DEFAULT 10
)
""")
conn.commit()

LIMIT = 40

# ================= VIP =================
def is_vip(uid):
    c.execute("SELECT vip_until FROM users WHERE user_id=?", (uid,))
    r = c.fetchone()
    if not r or not r[0]:
        return False
    return datetime.fromisoformat(r[0]) > datetime.now()

def set_vip(uid):
    vip = datetime.now() + timedelta(days=30)
    c.execute("UPDATE users SET vip_until=? WHERE user_id=?", (vip.isoformat(), uid))
    conn.commit()

# ================= RESET =================
def reset(uid):
    today = str(date.today())
    c.execute("SELECT last_reset FROM users WHERE user_id=?", (uid,))
    r = c.fetchone()

    if not r or r[0] != today:
        c.execute("UPDATE users SET daily_msg=0, last_reset=? WHERE user_id=?", (today, uid))
        conn.commit()

# ================= LIMIT =================
def can_use(uid):
    reset(uid)

    if is_vip(uid):
        return True

    c.execute("SELECT free_msgs, daily_msg FROM users WHERE user_id=?", (uid,))
    free, used = c.fetchone()

    if free > 0:
        c.execute("UPDATE users SET free_msgs = free_msgs - 1 WHERE user_id=?", (uid,))
        conn.commit()
        return True

    if used >= LIMIT:
        return False

    c.execute("UPDATE users SET daily_msg = daily_msg + 1 WHERE user_id=?", (uid,))
    conn.commit()
    return True

# ================= AI =================
def ask_ai(text):
    try:
        return model.generate_content(text).text
    except:
        return "❌ خطا در AI"

# ================= GAME =================
def mine(uid):
    reward = random.uniform(0.001, 0.01)
    if is_vip(uid):
        reward *= 2

    c.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (reward, uid))
    conn.commit()
    return reward

# ================= MENU =================
def menu():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🤖 AI", callback_data="ai"),
            InlineKeyboardButton("⛏ ماین", callback_data="mine")
        ],
        [
            InlineKeyboardButton("💰 کیف پول", callback_data="wallet"),
            InlineKeyboardButton("💎 VIP", callback_data="vip")
        ],
        [
            InlineKeyboardButton("🤝 دعوت", callback_data="invite")
        ]
    ])

# ================= START =================
async def start(update: Update, context):
    uid = update.effective_user.id

    c.execute("INSERT OR IGNORE INTO users(user_id) VALUES(?)", (uid,))
    conn.commit()

    await update.message.reply_text("💎 ربات فعال شد", reply_markup=menu())

# ================= BUTTONS =================
async def buttons(update: Update, context):
    q = update.callback_query
    uid = q.from_user.id
    d = q.data

    if d == "ai":
        context.user_data["ai"] = True
        await q.message.reply_text("💬 پیام بفرست")

    elif d == "mine":
        await q.message.reply_text(f"⛏ درآمد: {mine(uid):.5f}")

    elif d == "wallet":
        c.execute("SELECT balance FROM users WHERE user_id=?", (uid,))
        await q.message.reply_text(f"💰 موجودی: {c.fetchone()[0]:.5f}")

    elif d == "vip":
        set_vip(uid)
        await q.message.reply_text("💎 VIP فعال شد")

    elif d == "invite":
        await q.message.reply_text(f"https://t.me/YOUR_BOT?start={uid}")

# ================= AI CHAT =================
async def handle(update: Update, context):
    uid = update.effective_user.id

    if context.user_data.get("ai"):
        if not can_use(uid):
            await update.message.reply_text("❌ محدودیت 40 پیام")
            return

        await update.message.reply_text(ask_ai(update.message.text))

# ================= RUN =================
app = Application.builder().token(BOT_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(buttons))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))

app.run_polling()
