import os
import sqlite3
import random
from datetime import datetime, date, timedelta

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters

import google.generativeai as genai

# 🤖 AI
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-1.5-pro")

# 🗄 DB
conn = sqlite3.connect("bot.db", check_same_thread=False)
c = conn.cursor()

c.execute("""
CREATE TABLE IF NOT EXISTS users(
user_id INTEGER PRIMARY KEY,
accepted INTEGER DEFAULT 0,
daily_msg INTEGER DEFAULT 0,
last_reset TEXT,
vip_until TEXT,
balance REAL DEFAULT 0
)
""")
conn.commit()

LIMIT = 40

# 🎮 CONTRACT
contract_text = "📜 برای استفاده از ربات باید قرارداد را تایید کنید"

# 🎯 RESET
def reset(uid):
    today = str(date.today())

    c.execute("SELECT last_reset FROM users WHERE user_id=?", (uid,))
    r = c.fetchone()

    if not r or r[0] != today:
        c.execute("UPDATE users SET daily_msg=0, last_reset=? WHERE user_id=?", (today, uid))
        conn.commit()

# 💎 VIP
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

# ⛔ LIMIT
def can_use(uid):
    reset(uid)

    if is_vip(uid):
        return True

    c.execute("SELECT daily_msg FROM users WHERE user_id=?", (uid,))
    count = c.fetchone()[0]

    if count >= LIMIT:
        return False

    c.execute("UPDATE users SET daily_msg = daily_msg + 1 WHERE user_id=?", (uid,))
    conn.commit()

    return True

# 🤖 AI
def ask_ai(text):
    try:
        return model.generate_content(text).text
    except:
        return "❌ خطا در AI"

# ⛏ MINE GAME
def mine(uid):
    reward = random.uniform(0.0001, 0.005)
    if is_vip(uid):
        reward *= 2

    c.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (reward, uid))
    conn.commit()

    return reward

# 🎮 START
async def start(update: Update, context):
    uid = update.effective_user.id

    c.execute("INSERT OR IGNORE INTO users(user_id) VALUES(?)", (uid,))
    conn.commit()

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✔ قبول قرارداد", callback_data="accept")]
    ])

    await update.message.reply_text(contract_text, reply_markup=keyboard)

# ✔ ACCEPT CONTRACT
async def accept(update: Update, context):
    q = update.callback_query
    uid = q.from_user.id

    c.execute("UPDATE users SET accepted=1 WHERE user_id=?", (uid,))
    conn.commit()

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🤖 هوش مصنوعی", callback_data="ai")],
        [InlineKeyboardButton("⛏ ماین", callback_data="mine")],
        [InlineKeyboardButton("💰 کیف پول", callback_data="wallet")],
        [InlineKeyboardButton("💎 VIP", callback_data="vip")],
        [InlineKeyboardButton("🤝 دعوت", callback_data="invite")]
    ])

    await q.answer()
    await q.edit_message_text("✔ قرارداد تایید شد\n💎 ربات فعال شد", reply_markup=keyboard)

# 💬 CALLBACKS
async def buttons(update: Update, context):
    q = update.callback_query
    uid = q.from_user.id
    data = q.data

    # AI
    if data == "ai":
        context.user_data["ai"] = True
        await q.message.reply_text("💬 سوالت را بفرست")
        return

    # MINE
    if data == "mine":
        reward = mine(uid)
        await q.message.reply_text(f"⛏ درآمد: {reward:.5f} BTC")
        return

    # WALLET
    if data == "wallet":
        c.execute("SELECT balance FROM users WHERE user_id=?", (uid,))
        bal = c.fetchone()[0]
        await q.message.reply_text(f"💰 موجودی: {bal:.5f}")
        return

    # VIP
    if data == "vip":
        set_vip(uid)
        await q.message.reply_text("👑 VIP فعال شد (30 روز)")
        return

    # INVITE
    if data == "invite":
        link = f"https://t.me/YOUR_BOT?start={uid}"
        await q.message.reply_text(f"📎 لینک دعوت:\n{link}")
        return

# 💬 AI MESSAGE
async def handle(update: Update, context):
    uid = update.effective_user.id
    text = update.message.text

    if context.user_data.get("ai"):
        if not can_use(uid):
            await update.message.reply_text("❌ 40 پیام تمام شد")
            return

        ans = ask_ai(text)
        await update.message.reply_text(ans)
        return

# 🚀 RUN
app = Application.builder().token(os.getenv("BOT_TOKEN")).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(accept, pattern="accept"))
app.add_handler(CallbackQueryHandler(buttons))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))

app.run_polling()    
