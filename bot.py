import os
import sqlite3
import requests
from datetime import datetime, date, timedelta

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters

import google.generativeai as genai

# ================= AI =================
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-1.5-flash")

# ================= DB =================
conn = sqlite3.connect("bot.db", check_same_thread=False)
c = conn.cursor()

c.execute("""
CREATE TABLE IF NOT EXISTS users(
user_id INTEGER PRIMARY KEY,
balance REAL DEFAULT 0,
daily_msg INTEGER DEFAULT 0,
last_reset TEXT,
vip_until TEXT,
accepted INTEGER DEFAULT 0
)
""")
conn.commit()

# ================= SETTINGS =================
LIMIT = 40

menu = ReplyKeyboardMarkup([
    ["🤖 AI"],
    ["💎 VIP"],
    ["💰 کیف پول"],
    ["📜 قرارداد"]
], resize_keyboard=True)

# ================= RESET DAILY =================
def reset(uid):
    today = str(date.today())

    c.execute("SELECT last_reset FROM users WHERE user_id=?", (uid,))
    r = c.fetchone()

    if not r or r[0] != today:
        c.execute("""
        UPDATE users SET daily_msg=0, last_reset=?
        WHERE user_id=?
        """, (today, uid))
        conn.commit()

# ================= VIP CHECK =================
def is_vip(uid):
    c.execute("SELECT vip_until FROM users WHERE user_id=?", (uid,))
    r = c.fetchone()

    if not r or not r[0]:
        return False

    return datetime.fromisoformat(r[0]) > datetime.now()

def set_vip(uid):
    vip_time = datetime.now() + timedelta(days=30)

    c.execute("""
    UPDATE users SET vip_until=?
    WHERE user_id=?
    """, (vip_time.isoformat(), uid))

    conn.commit()

# ================= LIMIT =================
def can_use(uid):
    reset(uid)

    if is_vip(uid):
        return True

    c.execute("SELECT daily_msg FROM users WHERE user_id=?", (uid,))
    count = c.fetchone()[0]

    if count >= LIMIT:
        return False

    c.execute("""
    UPDATE users SET daily_msg = daily_msg + 1
    WHERE user_id=?
    """, (uid,))
    conn.commit()

    return True

# ================= AI =================
def ask_ai(text):
    try:
        return model.generate_content(text).text
    except:
        return "❌ AI Error"

# ================= START =================
async def start(update: Update, context):
    await update.message.reply_text("💎 ربات فعال شد", reply_markup=menu)

# ================= HANDLE =================
async def handle(update: Update, context):
    uid = update.effective_user.id
    text = update.message.text

    # 📜 contract
    if text == "📜 قرارداد":
        await update.message.reply_text("✔ استفاده از ربات تایید شد")
        return

    # 💰 wallet (simple)
    if text == "💰 کیف پول":
        await update.message.reply_text("💰 سیستم کیف پول فعال است")
        return

    # 💎 VIP (REAL)
    if text == "💎 VIP":
        set_vip(uid)
        await update.message.reply_text("👑 VIP 30 روزه فعال شد")
        return

    # 🤖 AI
    if text == "🤖 AI":

        if not can_use(uid):
            await update.message.reply_text("❌ محدودیت 40 پیام تمام شد")
            return

        await update.message.reply_text("💬 سوالت را بفرست")
        context.user_data["ai"] = True
        return

    # AI RESPONSE
    if context.user_data.get("ai"):
        answer = ask_ai(text)
        await update.message.reply_text(answer)
        return

    await update.message.reply_text("📩 دریافت شد")

# ================= RUN =================
app = Application.builder().token(os.getenv("BOT_TOKEN")).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))

app.run_polling()
