import os
import time
import sqlite3
import telebot
import requests
from telebot import types
from flask import Flask, request

# ========================
# НАСТРОЙКИ
# ========================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
CARD_NUMBER = os.environ.get("CARD_NUMBER", "8600 0000 0000 0000")
NEOSMM_API_KEY = os.environ.get("NEOSMM_API_KEY", "")
NEOSMM_API_URL = "https://neosmm.uz/api/v2"
SUPPORT_USERNAME = "@neosmmhelp"

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN not found")

bot = telebot.TeleBot(BOT_TOKEN)
bot.threaded = False
app = Flask(__name__)

# ========================
# БАЗА ДАННЫХ
# ========================
def init_db():
    conn = sqlite3.connect("smm.db")
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, balance INTEGER DEFAULT 0, lang TEXT DEFAULT 'uz', ref_by INTEGER DEFAULT 0, total_topup INTEGER DEFAULT 0)")
    c.execute("CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, service TEXT, link TEXT, amount INTEGER, price INTEGER, status TEXT DEFAULT 'pending', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
    c.execute("CREATE TABLE IF NOT EXISTS prices (key TEXT PRIMARY KEY, value INTEGER, label TEXT, category TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS pending_payments (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount INTEGER, photo_id TEXT, status TEXT DEFAULT 'pending', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
    c.execute("CREATE TABLE IF NOT EXISTS last_msg (user_id INTEGER PRIMARY KEY, message_id INTEGER)")
    # Цены по умолчанию (вы измените их через админ-панель)
    defaults = [
        ("stars_50", 8000, "50 Stars", "stars"),
        ("stars_100", 15000, "100 Stars", "stars"),
        ("stars_250", 35000, "250 Stars", "stars"),
        ("stars_500", 70000, "500 Stars", "stars"),
        ("stars_1000", 130000, "1000 Stars", "stars"),
        ("stars_2500", 320000, "2500 Stars", "stars"),
        ("stars_5000", 600000, "5000 Stars", "stars"),
        ("stars_10000", 1150000, "10000 Stars", "stars"),
        ("premium_3m", 170000, "3 месяца", "premium"),
        ("premium_6m", 230000, "6 месяцев", "premium"),
        ("premium_12m", 390000, "12 месяцев", "premium"),
        ("ff_100", 15000, "100 UC", "freefire"),
        ("ff_300", 45000, "300 UC", "freefire"),
        ("ff_500", 75000, "500 UC", "freefire"),
    ]
    for k, v, label, cat in defaults:
        c.execute("INSERT OR IGNORE INTO prices (key, value, label, category) VALUES (?, ?, ?, ?)", (k, v, label, cat))
    conn.commit()
    conn.close()

init_db()

# ========================
# ФУНКЦИИ БД
# ========================
def get_price(key):
    conn = sqlite3.connect("smm.db")
    c = conn.cursor()
    c.execute("SELECT value FROM prices WHERE key=?", (key,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else 0

def set_price(key, value):
    conn = sqlite3.connect("smm.db")
    c = conn.cursor()
    c.execute("UPDATE prices SET value=? WHERE key=?", (value, key))
    conn.commit()
    conn.close()

def get_prices_by_category(category):
    conn = sqlite3.connect("smm.db")
    c = conn.cursor()
    c.execute("SELECT key, value, label FROM prices WHERE category=? ORDER BY value ASC", (category,))
    rows = c.fetchall()
    conn.close()
    return rows

def get_balance(user_id):
    conn = sqlite3.connect("smm.db")
    c = conn.cursor()
    c.execute("SELECT balance FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else 0

def update_balance(user_id, delta):
    conn = sqlite3.connect("smm.db")
    c = conn.cursor()
    c.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (delta, user_id))
    conn.commit()
    conn.close()

def get_total_topup(user_id):
    conn = sqlite3.connect("smm.db")
    c = conn.cursor()
    c.execute("SELECT total_topup FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else 0

# ========================
# ИСЧЕЗАЮЩИЕ СООБЩЕНИЯ
# ========================
def get_last_msg(user_id):
    conn = sqlite3.connect("smm.db")
    c = conn.cursor()
    c.execute("SELECT message_id FROM last_msg WHERE user_id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

def set_last_msg(user_id, message_id):
    conn = sqlite3.connect("smm.db")
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO last_msg (user_id, message_id) VALUES (?, ?)", (user_id, message_id))
    conn.commit()
    conn.close()

def delete_last_msg(user_id):
    msg_id = get_last_msg(user_id)
    if msg_id:
        try:
            bot.delete_message(user_id, msg_id)
        except Exception:
            pass

def send_clean(chat_id, text, reply_markup=None, parse_mode=None):
    delete_last_msg(chat_id)
    msg = bot.send_message(chat_id, text, reply_markup=reply_markup, parse_mode=parse_mode)
    set_last_msg(chat_id, msg.message_id)
    return msg

# ========================
# NEO SMM API
# ========================
def neosmm_request(action, **kwargs):
    try:
        data = {"key": NEOSMM_API_KEY, "action": action}
        data.update(kwargs)
        resp = requests.post(NEOSMM_API_URL, data=data, timeout=15)
        return resp.json()
    except Exception as e:
        print(f"NEO SMM error: {e}")
        return {"error": str(e)}

def neosmm_balance():
    return neosmm_request("balance")

def neosmm_services():
    return neosmm_request("services")

def neosmm_add_order(service, link, quantity):
    return neosmm_request("add", service=service, link=link, quantity=quantity)

def neosmm_order_status(order_id):
    return neosmm_request("status", order=order_id)

# ========================
# WEBHOOK
# ========================
@app.route("/webhook", methods=["POST"])
def webhook():
    if request.headers.get("content-type") == "application/json":
        json_string = request.get_data().decode("utf-8")
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return "OK", 200
    return "Forbidden", 403

@app.route("/", methods=["GET"])
def home():
    return "SMM-bot works!", 200

# ========================
# ЗАПУСК
# ========================
def setup_webhook():
    try:
        time.sleep(3)
        bot.remove_webhook()
        render_url = os.environ.get("RENDER_EXTERNAL_URL")
        if not render_url:
            raise RuntimeError("RENDER_EXTERNAL_URL not found")
        webhook_url = f"{render_url}/webhook"
        bot.set_webhook(url=webhook_url)
        print(f"Webhook set: {webhook_url}")
    except Exception as e:
        print(f"Webhook error: {e}")

setup_webhook()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
