import os
import time
import psycopg2
import telebot
import requests
from telebot import types
from flask import Flask, request

# ========================
# НАСТРОЙКИ
# ========================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
CARD_NUMBER = os.environ.get("CARD_NUMBER", "4067070025217360")
CARD_NAME = "Lazizbek Mavlanov"
NEOSMM_API_KEY = os.environ.get("NEOSMM_API_KEY", "")
NEOSMM_API_URL = "https://neosmm.uz/api/v2"
SUPPORT_USERNAME = "@FastGreenBot_SMM"
DATABASE_URL = os.environ.get("DATABASE_URL")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN not found")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL not found")

bot = telebot.TeleBot(BOT_TOKEN)
bot.threaded = False
app = Flask(__name__)

# ========================
# БАЗА ДАННЫХ (PostgreSQL)
# ========================
def db():
    return psycopg2.connect(DATABASE_URL, sslmode="require")

def init_db():
    conn = db()
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id BIGINT PRIMARY KEY,
        balance BIGINT DEFAULT 0,
        lang TEXT DEFAULT 'uz',
        ref_by BIGINT DEFAULT 0,
        total_topup BIGINT DEFAULT 0
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS orders (
        id SERIAL PRIMARY KEY,
        user_id BIGINT,
        service TEXT,
        link TEXT,
        amount BIGINT,
        price BIGINT,
        status TEXT DEFAULT 'pending',
        created_at TIMESTAMP DEFAULT NOW()
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS prices (
        key TEXT PRIMARY KEY,
        value BIGINT,
        label TEXT,
        category TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS pending_payments (
        id SERIAL PRIMARY KEY,
        user_id BIGINT,
        amount BIGINT,
        photo_id TEXT,
        status TEXT DEFAULT 'pending',
        created_at TIMESTAMP DEFAULT NOW()
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS last_msg (
        user_id BIGINT PRIMARY KEY,
        message_id BIGINT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )""")
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('mode', 'auto')") if False else None
    c.execute("INSERT INTO settings (key, value) VALUES ('mode', 'auto') ON CONFLICT (key) DO NOTHING")
    # Цены по умолчанию (вы измените через админку)
    defaults = [
        ("stars_50", 10750, "50 Stars", "stars"),
        ("stars_100", 21500, "100 Stars", "stars"),
        ("stars_150", 32250, "150 Stars", "stars"),
        ("stars_200", 43000, "200 Stars", "stars"),
        ("stars_250", 53750, "250 Stars", "stars"),
        ("stars_500", 107500, "500 Stars", "stars"),
        ("stars_1000", 215000, "1000 Stars", "stars"),
        ("stars_1500", 322500, "1500 Stars", "stars"),
        ("premium_1m", 0, "1 месяц", "premium"),
        ("premium_3m", 0, "3 месяца", "premium"),
        ("premium_6m", 0, "6 месяцев", "premium"),
        ("premium_12m", 0, "12 месяцев", "premium"),
        ("ff_yangi", 0, "Yangi o'yinchi bonusi", "freefire"),
        ("ff_haftalik_lite", 0, "Haftalik Lite", "freefire"),
        ("ff_evo_3d", 0, "Evo Access 3D", "freefire"),
        ("ff_evo_7d", 0, "Evo Access 7D", "freefire"),
        ("ff_evo_30d", 0, "Evo Access 30D", "freefire"),
        ("ff_lvl_6", 0, "Level Up 6", "freefire"),
        ("ff_lvl_10", 0, "Level Up 10", "freefire"),
        ("ff_lvl_15", 0, "Level Up 15", "freefire"),
        ("ff_lvl_20", 0, "Level Up 20", "freefire"),
        ("ff_lvl_25", 0, "Level Up 25", "freefire"),
        ("ff_lvl_30", 0, "Level Up 30", "freefire"),
        ("ff_110", 0, "110 Almaz", "freefire"),
        ("ff_341", 0, "341 Almaz", "freefire"),
        ("ff_572", 0, "572 Almaz", "freefire"),
        ("ff_1166", 0, "1166 Almaz", "freefire"),
        ("ff_2398", 0, "2398 Almaz", "freefire"),
        ("ff_6160", 0, "6160 Almaz", "freefire"),
        ("ff_vaucher_hafta", 0, "Haftalik Vaucher", "freefire"),
        ("ff_vaucher_oy", 0, "Oylik Vaucher obuna", "freefire"),
        ("pubg_60", 0, "60 UC", "pubg"),
        ("pubg_325", 0, "325 UC", "pubg"),
        ("pubg_660", 0, "660 UC", "pubg"),
        ("pubg_1800", 0, "1800 UC", "pubg"),
        ("pubg_3850", 0, "3850 UC", "pubg"),
        ("pubg_8100", 0, "8100 UC", "pubg"),
        ("pubg_16200", 0, "16200 UC", "pubg"),
        ("ml_55", 0, "55 Olmaz", "ml"),
        ("ml_86", 0, "86 Olmaz", "ml"),
        ("ml_165", 0, "165 Olmaz", "ml"),
        ("ml_172", 0, "172 Olmaz", "ml"),
        ("ml_256", 0, "256 Olmaz", "ml"),
        ("ml_275", 0, "275 Olmaz", "ml"),
        ("ml_565", 0, "565 Olmaz", "ml"),
        ("ml_706", 0, "706 Olmaz", "ml"),
        ("ml_2195", 0, "2195 Olmaz", "ml"),
        ("ml_3688", 0, "3688 Olmaz", "ml"),
        ("ml_5532", 0, "5532 Olmaz", "ml"),
        ("ml_elit", 0, "Haftalik Elit Pass", "ml"),
        ("ml_diamond", 0, "Haftalik Diamond Pass", "ml"),
    ]
    for k, v, label, cat in defaults:
        c.execute("INSERT INTO prices (key, value, label, category) VALUES (%s, %s, %s, %s) ON CONFLICT (key) DO NOTHING", (k, v, label, cat))
    conn.commit()
    c.close()
    conn.close()

init_db()

# ========================
# ФУНКЦИИ БД
# ========================
def get_price(key):
    conn = db()
    c = conn.cursor()
    c.execute("SELECT value FROM prices WHERE key=%s", (key,))
    row = c.fetchone()
    c.close()
    conn.close()
    return row[0] if row else 0

def set_price(key, value):
    conn = db()
    c = conn.cursor()
    c.execute("UPDATE prices SET value=%s WHERE key=%s", (value, key))
    conn.commit()
    c.close()
    conn.close()

def get_prices_by_category(category):
    conn = db()
    c = conn.cursor()
    c.execute("SELECT key, value, label FROM prices WHERE category=%s ORDER BY value ASC", (category,))
    rows = c.fetchall()
    c.close()
    conn.close()
    return rows

def get_balance(user_id):
    conn = db()
    c = conn.cursor()
    c.execute("SELECT balance FROM users WHERE user_id=%s", (user_id,))
    row = c.fetchone()
    c.close()
    conn.close()
    return row[0] if row else 0

def update_balance(user_id, delta):
    conn = db()
    c = conn.cursor()
    c.execute("UPDATE users SET balance = balance + %s WHERE user_id=%s", (delta, user_id))
    conn.commit()
    c.close()
    conn.close()

def get_total_topup(user_id):
    conn = db()
    c = conn.cursor()
    c.execute("SELECT total_topup FROM users WHERE user_id=%s", (user_id,))
    row = c.fetchone()
    c.close()
    conn.close()
    return row[0] if row else 0

def get_setting(key):
    conn = db()
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key=%s", (key,))
    row = c.fetchone()
    c.close()
    conn.close()
    return row[0] if row else None

def set_setting(key, value):
    conn = db()
    c = conn.cursor()
    c.execute("INSERT INTO settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE SET value=%s", (key, value, value))
    conn.commit()
    c.close()
    conn.close()

# ========================
# ИСЧЕЗАЮЩИЕ СООБЩЕНИЯ
# ========================
def get_last_msg(user_id):
    conn = db()
    c = conn.cursor()
    c.execute("SELECT message_id FROM last_msg WHERE user_id=%s", (user_id,))
    row = c.fetchone()
    c.close()
    conn.close()
    return row[0] if row else None

def set_last_msg(user_id, message_id):
    conn = db()
    c = conn.cursor()
    c.execute("INSERT INTO last_msg (user_id, message_id) VALUES (%s, %s) ON CONFLICT (user_id) DO UPDATE SET message_id=%s", (user_id, message_id, message_id))
    conn.commit()
    c.close()
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

def neosmm_donat_services():
    return neosmm_request("donat_services")

def neosmm_donat_add(product, player_id, server_id=None):
    params = {"product": product, "player_id": player_id}
    if server_id:
        params["server_id"] = server_id
    return neosmm_request("donat_add", **params)

def neosmm_donat_status(order_id):
    return neosmm_request("donat_status", order=order_id)

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
