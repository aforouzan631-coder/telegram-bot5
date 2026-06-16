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
msg_count INTEGER DEFAULT 0,
img_count INTEGER DEFAULT 0,
invites INTEGER DEFAULT 0
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
    ["🤖 AI"],
    ["💰 کیف پول", "💸 انتقال پول"],
    ["🤝 دعوت دوستان"],
    ["💎 خرید VIP"],
    ["💰 دلار", "🪙 طلا"],
    ["🎮 بازی"]
], resize_keyboard=True)

# ================= VIP =================
def set_vip(uid, days=30):
    vip = datetime.now() + timedelta(days=days)
    c.execute("UPDATE users SET vip_until=? WHERE user_id=?", (vip.isoformat(), uid))
    conn.commit()

def is_vip(uid):
    c.execute("SELECT vip_until FROM users WHERE user_id=?", (uid,))
    r = c.fetchone()
    if not r or not r[0]:
        return False
    return datetime.fromisoformat(r[0]) > datetime.now()

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

# ================= TRANSFER =================
def transfer(frm, to, amount):
    if amount <= 0:
        return "❌ مبلغ اشتباه"

    if balance(frm) < amount:
        return "❌ موجودی کافی نیست"

    remove_balance(frm, amount)
    add_balance(to, amount)

    c.execute("""
    INSERT INTO transactions(from_user,to_user,amount,time)
    VALUES(?,?,?,?)
    """, (frm, to, amount, datetime.now().isoformat()))
    conn.commit()

    return "✅ انتقال موفق"

# ================= AI =================
def ai(text):
    return model.generate_content(text).text

# ================= START =================
async def start(update: Update, context):
    uid = update.effective_user.id

    # referral
    if context.args:
        ref = int(context.args[0])
        if ref != uid:
            c.execute("UPDATE users SET invites = invites + 1 WHERE user_id=?", (ref,))
            c.execute("UPDATE users SET msg_count = msg_count - 10 WHERE user_id=?", (ref,))
            conn.commit()

    await update.message.reply_text("💎 GOLD PRO MAX BOT", reply_markup=menu)

# ================= PAYMENT =================
def create_payment(uid):
    data = {
        "merchant_id": MERCHANT,
        "amount": 50000,
        "callback_url": f"{BASE_URL}/verify?user_id={uid}",
        "description": "VIP GOLD"
    }

    r = requests.post(
        "https://api.zarinpal.com/pg/v4/payment/request.json",
        json=data
    ).json()

    return r

# ================= HANDLE =================
async def handle(update: Update, context):
    text = update.message.text
    uid = update.effective_user.id

    # WALLET
    if text == "💰 کیف پول":
        await update.message.reply_text(f"💰 موجودی: {balance(uid)}")
        return

    # TRANSFER
    if text == "💸 انتقال پول":
        await update.message.reply_text("📌 فرمت:\n123456 10000")
        return

    if text.replace(" ", "").isdigit() is False and " " in text:
        try:
            to, amount = map(int, text.split())
            await update.message.reply_text(transfer(uid, to, amount))
        except:
            pass
        return

    # VIP
    if text == "💎 خرید VIP":
        pay = create_payment(uid)
        if pay.get("data"):
            url = "https://www.zarinpal.com/pg/StartPay/" + pay["data"]["authority"]
            await update.message.reply_text("💳 پرداخت:\n" + url)
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

    if text == "🎮 بازی":
        await update.message.reply_text("🎯 یک عدد 1 تا 5 بفرست")
        return

    await update.message.reply_text("❓ دستور نامشخص")

# ================= VERIFY =================
from flask import Flask, request
app = Flask(__name__)

@app.route("/verify")
def verify():
    uid = int(request.args.get("user_id"))
    authority = request.args.get("Authority")

    data = {
        "merchant_id": MERCHANT,
        "authority": authority,
        "amount": 50000
    }

    r = requests.post(
        "https://api.zarinpal.com/pg/v4/payment/verify.json",
        json=data
    ).json()

    if r.get("data", {}).get("code") == 100:
        set_vip(uid, 30)
        return "VIP ACTIVE"

    return "FAILED"

# ================= RUN =================
app_bot = Application.builder().token(BOT_TOKEN).build()
app_bot.add_handler(CommandHandler("start", start))
app_bot.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))

app_bot.run_polling()
