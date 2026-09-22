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
# ЯЗЫКИ
# ========================
TEXTS = {
    "uz": {
        "choose_section": "👇 Quyidagi bo'limlardan birini tanlang:",
        "welcome": "👋 Assalomu alaykum {name}!\n\n🤖 Bizning SMM botimizga xush kelibsiz:\n\nIjtimoiy tarmoqlar uchun obunachi, like, ko'rishlar va boshqa xizmatlar.\n\n👤 ID raqam: {user_id}",
        "balance": "💳 Hisobim",
        "topup": "💳 Pul kiritish",
        "bonus": "👥 Referal",
        "orders": "📊 Buyurtmalarim",
        "support": "☎️ Qo'llab-quvvatlash",
        "lang": "🌐 Til",
        "back": "⬅️ Orqaga",
        "your_balance": "💵 Balansingiz: {bal} so'm\n💰 Jami to'ldirilgan: {topup} so'm",
        "not_enough": "❌ Mablag' yetarli emas. Kerak: {price} so'm, sizda: {bal} so'm.",
        "order_created": "✅ {service} uchun buyurtma yaratildi.",
        "no_username": "❌ Telegram'da username o'rnatilmagan.",
        "payment_sent": "✅ Chek tekshiruvga yuborildi.",
        "topup_text": "💳 Pul kiritish\n\nQuyidagi kartaga o'tkazing:\n{karta}\n\n{ism}\n\nTo'lovni amalga oshirgandan so'ng, chekni rasm sifatida yuboring.",
        "support_text": "☎️ Qo'llab-quvvatlash: {support}",
    },
    "ru": {
        "choose_section": "👇 Выберите нужный раздел:",
        "welcome": "👋 Привет, {name}!\n\n🤖 Добро пожаловать в наш SMM-бот:\n\nНакрутка подписчиков, лайков, просмотров и другие услуги.\n\n👤 Ваш ID: {user_id}",
        "balance": "💳 Мой баланс",
        "topup": "💳 Пополнить баланс",
        "bonus": "👥 Реферал",
        "orders": "📊 Мои заказы",
        "support": "☎️ Поддержка",
        "lang": "🌐 Язык",
        "back": "⬅️ Назад",
        "your_balance": "💵 Ваш баланс: {bal} сум\n💰 Всего пополнено: {topup} сум",
        "not_enough": "❌ Недостаточно средств. Нужно: {price} сум, у вас: {bal} сум.",
        "order_created": "✅ Заказ на {service} создан.",
        "no_username": "❌ У вас не установлен username в Telegram.",
        "payment_sent": "✅ Чек отправлен на проверку.",
        "topup_text": "💳 Пополнение баланса\n\nПереведите на карту:\n{karta}\n\n{ism}\n\nПосле оплаты отправьте чек фото.",
        "support_text": "☎️ Поддержка: {support}",
    }
}

def get_lang(user_id):
    conn = db()
    c = conn.cursor()
    c.execute("SELECT lang FROM users WHERE user_id=%s", (user_id,))
    row = c.fetchone()
    c.close()
    conn.close()
    return row[0] if row else "uz"

def t(user_id, key, **kwargs):
    lang = get_lang(user_id)
    text = TEXTS.get(lang, TEXTS["uz"]).get(key, key)
    return text.format(**kwargs) if kwargs else text

# ========================
# КЛАВИАТУРЫ
# ========================
def main_menu(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        types.KeyboardButton("💎 Donat qilish"),
        types.KeyboardButton("🛍 Xizmatlar"),
        types.KeyboardButton(t(user_id, "topup")),
        types.KeyboardButton(t(user_id, "balance")),
        types.KeyboardButton(t(user_id, "bonus")),
        types.KeyboardButton(t(user_id, "orders")),
        types.KeyboardButton("📢 Kanal ulash"),
        types.KeyboardButton(t(user_id, "support")),
        types.KeyboardButton("🤝 Hamkorlik dasturi"),
        types.KeyboardButton(t(user_id, "lang")),
    )
    return markup

def services_menu(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        types.KeyboardButton("📱 Telegram"),
        types.KeyboardButton("📸 Instagram"),
        types.KeyboardButton("🎵 Tik Tok"),
        types.KeyboardButton("▶️ You tube"),
        types.KeyboardButton("📘 Facebook"),
        types.KeyboardButton("🧵 Threads"),
        types.KeyboardButton("⭐ Premium, Stars, Gift"),
        types.KeyboardButton(t(user_id, "back")),
    )
    return markup

def telegram_menu(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    markup.add(
        types.KeyboardButton("👤 Telegram obunachi"),
        types.KeyboardButton("👁 Prasmotrlar"),
        types.KeyboardButton("👍 Reaksiyalar"),
        types.KeyboardButton(t(user_id, "back")),
    )
    return markup

def instagram_menu(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    markup.add(
        types.KeyboardButton("👤 Instagram obunachilar"),
        types.KeyboardButton("👁 Prasmotr"),
        types.KeyboardButton("❤️ Like"),
        types.KeyboardButton(t(user_id, "back")),
    )
    return markup

def tiktok_menu(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    markup.add(
        types.KeyboardButton("👤 Tik Tok Obunachi"),
        types.KeyboardButton("👁 Tik Tok Prasmotr"),
        types.KeyboardButton("❤️ Tik Tok Like"),
        types.KeyboardButton(t(user_id, "back")),
    )
    return markup

def youtube_menu(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    markup.add(
        types.KeyboardButton("👥 You Tube Obunachi"),
        types.KeyboardButton("👁 You Tube Prasmotr"),
        types.KeyboardButton("👍 Yoqtirish"),
        types.KeyboardButton(t(user_id, "back")),
    )
    return markup

def facebook_menu(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    markup.add(
        types.KeyboardButton("👥 Facebook Obunachi"),
        types.KeyboardButton("❤️ Facebook Like"),
        types.KeyboardButton(t(user_id, "back")),
    )
    return markup

def threads_menu(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    markup.add(
        types.KeyboardButton("👥 Threads Obunachi"),
        types.KeyboardButton("❤️ Threads Like"),
        types.KeyboardButton(t(user_id, "back")),
    )
    return markup

def donat_menu(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        types.KeyboardButton("🎮 Free Fire"),
        types.KeyboardButton("🔫 PUBG UC"),
        types.KeyboardButton("💎 Mobile Legends"),
        types.KeyboardButton(t(user_id, "back")),
    )
    return markup

def back_kb(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    markup.add(types.KeyboardButton(t(user_id, "back")))
    return markup

# ========================
# /START
# ========================
@bot.message_handler(commands=["start"])
def send_welcome(message):
    user_id = message.from_user.id
    user_name = message.from_user.first_name or "do'stim"
    conn = db()
    c = conn.cursor()
    c.execute("INSERT INTO users (user_id) VALUES (%s) ON CONFLICT (user_id) DO NOTHING", (user_id,))
    conn.commit()
    c.close()
    conn.close()
    args = message.text.split()
    if len(args) > 1 and args[1].startswith("ref_"):
        try:
            ref_id = int(args[1].replace("ref_", ""))
            if ref_id != user_id:
                conn = db()
                c = conn.cursor()
                c.execute("UPDATE users SET ref_by=%s WHERE user_id=%s", (ref_id, user_id))
                conn.commit()
                c.close()
                conn.close()
        except:
            pass
    send_clean(
        user_id,
        t(user_id, "welcome", name=user_name, user_id=user_id),
        reply_markup=main_menu(user_id)
    )

# ========================
# ОБРАБОТЧИКИ МЕНЮ
# ========================
@bot.message_handler(func=lambda m: m.text == "🛍 Xizmatlar")
def show_services(message):
    send_clean(message.from_user.id, "👇 Xizmatlardan birini tanlang:", reply_markup=services_menu(message.from_user.id))

@bot.message_handler(func=lambda m: m.text == "📱 Telegram")
def show_telegram(message):
    send_clean(message.from_user.id, "👇 Ichki bo'limlardan birini tanlang:", reply_markup=telegram_menu(message.from_user.id))

@bot.message_handler(func=lambda m: m.text == "📸 Instagram")
def show_instagram(message):
    send_clean(message.from_user.id, "👇 Ichki bo'limlardan birini tanlang:", reply_markup=instagram_menu(message.from_user.id))

@bot.message_handler(func=lambda m: m.text == "🎵 Tik Tok")
def show_tiktok(message):
    send_clean(message.from_user.id, "👇 Ichki bo'limlardan birini tanlang:", reply_markup=tiktok_menu(message.from_user.id))

@bot.message_handler(func=lambda m: m.text == "▶️ You tube")
def show_youtube(message):
    send_clean(message.from_user.id, "👇 Ichki bo'limlardan birini tanlang:", reply_markup=youtube_menu(message.from_user.id))

@bot.message_handler(func=lambda m: m.text == "📘 Facebook")
def show_facebook(message):
    send_clean(message.from_user.id, "👇 Ichki bo'limlardan birini tanlang:", reply_markup=facebook_menu(message.from_user.id))

@bot.message_handler(func=lambda m: m.text == "🧵 Threads")
def show_threads(message):
    send_clean(message.from_user.id, "👇 Ichki bo'limlardan birini tanlang:", reply_markup=threads_menu(message.from_user.id))

@bot.message_handler(func=lambda m: m.text == "💎 Donat qilish")
def show_donat(message):
    send_clean(message.from_user.id, "👇 O'yinni tanlang:", reply_markup=donat_menu(message.from_user.id))

@bot.message_handler(func=lambda m: m.text == t(m.from_user.id, "back"))
def back_to_main(message):
    send_clean(message.from_user.id, t(message.from_user.id, "choose_section"), reply_markup=main_menu(message.from_user.id))
    # ========================
# HISOBIM (БАЛАНС)
# ========================
@bot.message_handler(func=lambda m: m.text == t(m.from_user.id, "balance"))
def show_balance(message):
    user_id = message.from_user.id
    bal = get_balance(user_id)
    topup = get_total_topup(user_id)
    send_clean(
        user_id,
        t(user_id, "your_balance", bal=bal, topup=topup),
        reply_markup=main_menu(user_id)
    )

# ========================
# PUL KIRITISH (ПОПОЛНЕНИЕ)
# ========================
@bot.message_handler(func=lambda m: m.text == t(m.from_user.id, "topup"))
def topup(message):
    user_id = message.from_user.id
    send_clean(
        user_id,
        t(user_id, "topup_text", karta=CARD_NUMBER, ism=CARD_NAME),
        reply_markup=back_kb(user_id)
    )
    bot.register_next_step_handler(message, handle_receipt)

def handle_receipt(message):
    user_id = message.from_user.id
    if message.text == t(user_id, "back"):
        send_clean(user_id, t(user_id, "choose_section"), reply_markup=main_menu(user_id))
        return
    if not message.photo:
        send_clean(user_id, "Iltimos, chekni rasm sifatida yuboring.", reply_markup=back_kb(user_id))
        bot.register_next_step_handler(message, handle_receipt)
        return
    photo_id = message.photo[-1].file_id
    conn = db()
    c = conn.cursor()
    c.execute("INSERT INTO pending_payments (user_id, photo_id) VALUES (%s, %s) RETURNING id", (user_id, photo_id))
    payment_id = c.fetchone()[0]
    conn.commit()
    c.close()
    conn.close()
    send_clean(user_id, t(user_id, "payment_sent"), reply_markup=main_menu(user_id))
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"approve_{payment_id}"),
        types.InlineKeyboardButton("❌ Rad etish", callback_data=f"reject_{payment_id}")
    )
    bot.send_photo(ADMIN_ID, photo_id, caption=f"💳 Yangi chek\nUser: {user_id}\nID: {payment_id}", reply_markup=markup)

# ========================
# REFERAL
# ========================
@bot.message_handler(func=lambda m: m.text == t(m.from_user.id, "bonus"))
def show_referral(message):
    user_id = message.from_user.id
    conn = db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users WHERE ref_by=%s", (user_id,))
    ref_count = c.fetchone()[0]
    c.close()
    conn.close()
    bot_username = bot.get_me().username
    send_clean(
        user_id,
        f"👥 Sizning referallaringiz: {ref_count} ta\n\n"
        f"✨ Do'st taklif qiling — daromad oling!\n\n"
        f"Siz taklif qilgan har bir foydalanuvchi kiritgan summadan sizga 0.4% bonus beriladi 🤝\n\n"
        f"🔗 Havolangiz:\nhttps://t.me/{bot_username}?start=ref_{user_id}",
        reply_markup=main_menu(user_id)
    )

# ========================
# BUYURTMALARIM
# ========================
@bot.message_handler(func=lambda m: m.text == t(m.from_user.id, "orders"))
def show_orders(message):
    user_id = message.from_user.id
    conn = db()
    c = conn.cursor()
    c.execute("SELECT id, service, status FROM orders WHERE user_id=%s ORDER BY id DESC LIMIT 10", (user_id,))
    rows = c.fetchall()
    c.close()
    conn.close()
    if not rows:
        send_clean(user_id, "📊 Sizda hali buyurtmalar yo'q.", reply_markup=main_menu(user_id))
        return
    text = "📊 Buyurtmalarim:\n\n"
    for oid, service, status in rows:
        text += f"№{oid} — {service} — [{status}]\n"
    send_clean(user_id, text, reply_markup=main_menu(user_id))

# ========================
# KANAL ULASH
# ========================
@bot.message_handler(func=lambda m: m.text == "📢 Kanal ulash")
def show_channel(message):
    send_clean(
        message.from_user.id,
        "📢 «Kanal ulash» bo'limi tez orada ishga tushadi.",
        reply_markup=main_menu(message.from_user.id)
    )

# ========================
# QO'LLAB-QUVVATLASH
# ========================
@bot.message_handler(func=lambda m: m.text == t(m.from_user.id, "support"))
def show_support(message):
    send_clean(
        message.from_user.id,
        t(message.from_user.id, "support_text", support=SUPPORT_USERNAME),
        reply_markup=main_menu(message.from_user.id)
    )

# ========================
# HAMKORLIK DASTURI
# ========================
@bot.message_handler(func=lambda m: m.text == "🤝 Hamkorlik dasturi")
def show_partnership(message):
    send_clean(
        message.from_user.id,
        f"🤝 Hamkorlik dasturi\n\n"
        f"⚙️ API dokument:\nhttps://neosmm.uz/api/\n\n"
        f"🔑 API xizmat:\nhttps://neosmm.uz/api/v2\n\n"
        f"💵 Balansingiz: {get_balance(message.from_user.id)} so'm",
        reply_markup=main_menu(message.from_user.id)
    )

# ========================
# TIL (ЯЗЫК)
# ========================
@bot.message_handler(func=lambda m: m.text == t(m.from_user.id, "lang"))
def lang_menu(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(types.KeyboardButton("🇺🇿 O'zbekcha"), types.KeyboardButton("🇷🇺 Русский"))
    markup.add(types.KeyboardButton(t(message.from_user.id, "back")))
    send_clean(message.from_user.id, "🌐 Tilni tanlang / Выберите язык:", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "🇺🇿 O'zbekcha")
def set_uz(message):
    conn = db()
    c = conn.cursor()
    c.execute("UPDATE users SET lang='uz' WHERE user_id=%s", (message.from_user.id,))
    conn.commit()
    c.close()
    conn.close()
    send_clean(message.from_user.id, "✅ Til o'zgartirildi: O'zbekcha", reply_markup=main_menu(message.from_user.id))

@bot.message_handler(func=lambda m: m.text == "🇷🇺 Русский")
def set_ru(message):
    conn = db()
    c = conn.cursor()
    c.execute("UPDATE users SET lang='ru' WHERE user_id=%s", (message.from_user.id,))
    conn.commit()
    c.close()
    conn.close()
    send_clean(message.from_user.id, "✅ Язык изменён: Русский", reply_markup=main_menu(message.from_user.id))

# ========================
# ПОДТВЕРЖДЕНИЕ ЧЕКА (АДМИН)
# ========================
@bot.callback_query_handler(func=lambda call: call.data.startswith("approve_") or call.data.startswith("reject_"))
def handle_payment(call):
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "❌ Ruxsat yo'q")
        return
    action, payment_id = call.data.split("_")
    payment_id = int(payment_id)
    conn = db()
    c = conn.cursor()
    c.execute("SELECT user_id FROM pending_payments WHERE id=%s", (payment_id,))
    row = c.fetchone()
    c.close()
    conn.close()
    if not row:
        bot.answer_callback_query(call.id, "❌ Topilmadi")
        return
    user_id = row[0]
    if action == "approve":
        bot.send_message(ADMIN_ID, f"💰 {user_id} uchun summani kiriting:")
        bot.register_next_step_handler_by_chat_id(ADMIN_ID, lambda msg: confirm_amount(msg, payment_id, user_id))
    else:
        conn = db()
        c = conn.cursor()
        c.execute("UPDATE pending_payments SET status='rejected' WHERE id=%s", (payment_id,))
        conn.commit()
        c.close()
        conn.close()
        bot.send_message(user_id, "❌ Chekingiz rad etildi.")
        bot.answer_callback_query(call.id, "❌ Rad etildi")

def confirm_amount(message, payment_id, user_id):
    try:
        amount = int(message.text.strip())
    except ValueError:
        bot.send_message(ADMIN_ID, "❌ Raqam kiriting.")
        return
    update_balance(user_id, amount)
    conn = db()
    c = conn.cursor()
    c.execute("UPDATE users SET total_topup = total_topup + %s WHERE user_id=%s", (amount, user_id))
    c.execute("UPDATE pending_payments SET status='approved', amount=%s WHERE id=%s", (amount, payment_id))
    # Реферальный бонус 0.4%
    c.execute("SELECT ref_by FROM users WHERE user_id=%s", (user_id,))
    ref_row = c.fetchone()
    if ref_row and ref_row[0] and ref_row[0] != 0:
        bonus = int(amount * 0.004)
        if bonus > 0:
            c.execute("UPDATE users SET balance = balance + %s WHERE user_id=%s", (bonus, ref_row[0]))
            try:
                bot.send_message(ref_row[0], f"🎁 Sizga {bonus} so'm bonus tushdi (referal)!")
            except:
                pass
    conn.commit()
    c.close()
    conn.close()
    bot.send_message(user_id, f"✅ Balansingiz {amount} so'mga to'ldirildi!")
    bot.send_message(ADMIN_ID, f"✅ {user_id} ga {amount} so'm qo'shildi.")

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
