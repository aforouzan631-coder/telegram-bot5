import os
import sqlite3
import requests
from datetime import datetime, timedelta

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters

import google.generativeai as genai

# ================= CONFIG =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
MERCHANT = os.getenv("ZARINPAL_MERCHANT")
BASE_URL = os.getenv("BASE_URL")

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-1.5-pro")

# ================= DB =================
conn = sqlite3.connect("bot.db", check_same_thread=False)
c = conn.cursor()

c.execute("""
CREATE TABLE IF NOT EXISTS users(
user_id INTEGER PRIMARY KEY,
balance INTEGER DEFAULT 0,
vip_until TEXT,
msg_count INTEGER DEFAULT 0
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS transactions(
id INTEGER PRIMARY KEY AUTOINCREMENT,
from_user INTEGER,
to_user INTEGER,
amount INTEGER,
time TEXT
)
""")

conn.commit()

# ================= MENU =================
menu = ReplyKeyboardMarkup([
    ["💰 کیف پول"],
    ["💸 ارسال پول"],
    ["💎 خرید VIP"],
    ["🤝 دعوت"],
    ["🤖 AI"],
    ["💰 دلار", "🪙 طلا"]
], resize_keyboard=True)

# ================= WALLET =================
def balance(uid):
    c.execute("SELECT balance FROM users WHERE user_id=?", (uid,))
    r = c.fetchone()
    return r[0] if r else 0

def add_balance(uid, amount):
    c.execute("INSERT OR IGNORE INTO users(user_id,balance) VALUES(?,0)", (uid,))
    c.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (amount, uid))
    conn.commit()

def remove_balance(uid, amount):
    if balance(uid) >= amount:
        c.execute("UPDATE users SET balance=balance-? WHERE user_id=?", (amount, uid))
        conn.commit()
        return True
    return False

# ================= VIP =================
def set_vip(uid):
    vip = datetime.now() + timedelta(days=30)
    c.execute("UPDATE users SET vip_until=? WHERE user_id=?", (vip.isoformat(), uid))
    conn.commit()

def is_vip(uid):
    c.execute("SELECT vip_until FROM users WHERE user_id=?", (uid,))
    r = c.fetchone()
    if not r or not r[0]:
        return False
    return datetime.fromisoformat(r[0]) > datetime.now()

# ================= TRANSFER =================
def transfer(sender, receiver, amount):
    if amount <= 0:
        return "❌ مبلغ اشتباه"

    if balance(sender) < amount:
        return "❌ موجودی کافی نیست"

    remove_balance(sender, amount)
    add_balance(receiver, amount)

    c.execute("""
    INSERT INTO transactions(from_user,to_user,amount,time)
    VALUES(?,?,?,?)
    """, (sender, receiver, amount, datetime.now().isoformat()))
    conn.commit()

    return "✅ انتقال موفق"

# ================= AI =================
def ai(text):
    return model.generate_content(text).text

# ================= START =================
async def start(update: Update, context):
    await update.message.reply_text("💎 BOT فعال شد", reply_markup=menu)

# ================= HANDLE =================
async def handle(update: Update, context):
    text = update.message.text
    uid = update.effective_user.id

    # WALLET
    if text == "💰 کیف پول":
        await update.message.reply_text(f"💰 موجودی: {balance(uid)}")
        return

    # VIP
    if text == "💎 خرید VIP":
        if remove_balance(uid, 50000):
            set_vip(uid)
            await update.message.reply_text("👑 VIP فعال شد")
        else:
            await update.message.reply_text("❌ موجودی کافی نیست")
        return

    # TRANSFER
    if text == "💸 ارسال پول":
        await update.message.reply_text("📌 فرمت:\n/user_id amount\nمثال:\n123456 10000")
        return

    if text.startswith("/"):
        try:
            parts = text.replace("/", "").split()
            to = int(parts[0])
            amount = int(parts[1])

            result = transfer(uid, to, amount)
            await update.message.reply_text(result)
        except:
            await update.message.reply_text("❌ فرمت اشتباه")
        return

    # AI
    if text == "🤖 AI":
        if not is_vip(uid):
            await update.message.reply_text("🔒 فقط VIP")
            return
        await update.message.reply_text(ai("سلام"))
        return

    # PRICE
    if text == "💰 دلار":
        await update.message.reply_text("💵 دلار: 60,000")
        return

    if text == "🪙 طلا":
        await update.message.reply_text("🪙 طلا: 3,200,000")
        return

    await update.message.reply_text("❓ دستور نامشخص")

# ================= RUN =================
app_bot = Application.builder().token(BOT_TOKEN).build()
app_bot.add_handler(CommandHandler("start", start))
app_bot.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))

app_bot.run_polling()
