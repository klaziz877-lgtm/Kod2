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
# ЯЗЫКИ
# ========================
TEXTS = {
    "uz": {
        "choose_section": "👇 Quyidagi bo'limlardan birini tanlang:",
        "balance": "💳 Hisobim",
        "topup": "💳 Pul kiritish",
        "bonus": "👥 Referal",
        "orders": "📊 Buyurtmalarim",
        "support": "☎️ Qo'llab-quvvatlash",
        "lang": "🌐 Til",
        "your_balance": "💵 Balansingiz: {bal} so'm\n💰 Jami to'ldirilgan: {topup} so'm",
        "not_enough": "❌ Mablag' yetarli emas. Kerak: {price} so'm, sizda: {bal} so'm.",
        "order_created": "✅ {service} uchun buyurtma yaratildi.",
        "no_username": "❌ Telegram'da username o'rnatilmagan.",
        "support_text": "☎️ Qo'llab-quvvatlash: @neosmmhelp",
        "payment_sent": "✅ Chek tekshiruvga yuborildi.",
        "back": "⬅️ Orqaga",
    }
}

def get_lang(user_id):
    return "uz"

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
        types.KeyboardButton("💳 Pul kiritish"),
        types.KeyboardButton("💳 Hisobim"),
        types.KeyboardButton("👥 Referal"),
        types.KeyboardButton("📊 Buyurtmalarim"),
        types.KeyboardButton("📢 Kanal ulash"),
        types.KeyboardButton("☎️ Qo'llab-quvvatlash"),
        types.KeyboardButton("🤝 Hamkorlik dasturi"),
    )
    return markup

def services_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        types.KeyboardButton("📱 Telegram"),
        types.KeyboardButton("📸 Instagram"),
        types.KeyboardButton("🎵 Tik Tok"),
        types.KeyboardButton("▶️ You tube"),
        types.KeyboardButton("📘 Facebook"),
        types.KeyboardButton("🧵 Threads"),
        types.KeyboardButton("🎮 Free Fire"),
        types.KeyboardButton("⭐ Premium, Stars, Gift"),
        types.KeyboardButton("⬅️ Orqaga"),
    )
    return markup

def telegram_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    markup.add(
        types.KeyboardButton("👤 Telegram obunachi"),
        types.KeyboardButton("👁 Prasmotrlar"),
        types.KeyboardButton("👍 Reaksiyalar"),
        types.KeyboardButton("⬅️ Orqaga"),
    )
    return markup

def instagram_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    markup.add(
        types.KeyboardButton("👤 Instagram obunachilar"),
        types.KeyboardButton("👁 Prasmotr"),
        types.KeyboardButton("❤️ Like"),
        types.KeyboardButton("⬅️ Orqaga"),
    )
    return markup

def tiktok_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    markup.add(
        types.KeyboardButton("👤 Tik Tok Obunachi"),
        types.KeyboardButton("👁 Tik Tok Prasmotr"),
        types.KeyboardButton("❤️ Tik Tok Like"),
        types.KeyboardButton("⬅️ Orqaga"),
    )
    return markup

def youtube_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    markup.add(
        types.KeyboardButton("👥 You Tube Obunachi"),
        types.KeyboardButton("👁 You Tube Prasmotr"),
        types.KeyboardButton("👍 Yoqtirish"),
        types.KeyboardButton("⬅️ Orqaga"),
    )
    return markup

def facebook_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    markup.add(
        types.KeyboardButton("👥 Facebook Obunachi"),
        types.KeyboardButton("❤️ Facebook Like"),
        types.KeyboardButton("⬅️ Orqaga"),
    )
    return markup

def threads_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    markup.add(
        types.KeyboardButton("👥 Threads Obunachi"),
        types.KeyboardButton("❤️ Threads Like"),
        types.KeyboardButton("⬅️ Orqaga"),
    )
    return markup

def freefire_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    markup.add(
        types.KeyboardButton("🎮 100 UC"),
        types.KeyboardButton("🎮 300 UC"),
        types.KeyboardButton("🎮 500 UC"),
        types.KeyboardButton("⬅️ Orqaga"),
    )
    return markup

def back_kb():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    markup.add(types.KeyboardButton("⬅️ Orqaga"))
    return markup

# ========================
# /START
# ========================
@bot.message_handler(commands=["start"])
def send_welcome(message):
    user_id = message.from_user.id
    user_name = message.from_user.first_name or "do'stim"
    conn = sqlite3.connect("smm.db")
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    conn.commit()
    conn.close()
    args = message.text.split()
    if len(args) > 1 and args[1].startswith("ref_"):
        try:
            ref_id = int(args[1].replace("ref_", ""))
            if ref_id != user_id:
                conn = sqlite3.connect("smm.db")
                c = conn.cursor()
                c.execute("UPDATE users SET ref_by=? WHERE user_id=?", (ref_id, user_id))
                conn.commit()
                conn.close()
        except:
            pass
    send_clean(
        user_id,
        f"👋 Assalomu alaykum {user_name}!\n\n"
        f"🤖 Bizning nakrutka botimizga xush kelibsiz:\n"
        f"👇\n"
        f"Ijtimoiy tarmoqlar (Telegram, Instagram, Tiktok va Youtube) uchun obunachi, like, ko'rishlar hamda reaksiyalarni ko'paytirishingiz mumkin\n\n"
        f"👤 ID raqam: {user_id}",
        reply_markup=main_menu(user_id)
    )

# ========================
# ОБРАБОТЧИКИ МЕНЮ
# ========================
@bot.message_handler(func=lambda m: m.text == "🛍 Xizmatlar")
def show_services(message):
    send_clean(message.from_user.id, "👇 Quyidagi Ijtimoiy tarmoqlardan birini tanlang.", reply_markup=services_menu())

@bot.message_handler(func=lambda m: m.text == "📱 Telegram")
def show_telegram(message):
    send_clean(message.from_user.id, "👇 Quyidagi ichki bo'limlardan birini tanlang:", reply_markup=telegram_menu())

@bot.message_handler(func=lambda m: m.text == "📸 Instagram")
def show_instagram(message):
    send_clean(message.from_user.id, "👇 Quyidagi ichki bo'limlardan birini tanlang:", reply_markup=instagram_menu())

@bot.message_handler(func=lambda m: m.text == "🎵 Tik Tok")
def show_tiktok(message):
    send_clean(message.from_user.id, "👇 Quyidagi ichki bo'limlardan birini tanlang:", reply_markup=tiktok_menu())

@bot.message_handler(func=lambda m: m.text == "▶️ You tube")
def show_youtube(message):
    send_clean(message.from_user.id, "👇 Quyidagi ichki bo'limlardan birini tanlang:", reply_markup=youtube_menu())

@bot.message_handler(func=lambda m: m.text == "📘 Facebook")
def show_facebook(message):
    send_clean(message.from_user.id, "👇 Quyidagi ichki bo'limlardan birini tanlang:", reply_markup=facebook_menu())

@bot.message_handler(func=lambda m: m.text == "🧵 Threads")
def show_threads(message):
    send_clean(message.from_user.id, "👇 Quyidagi ichki bo'limlardan birini tanlang:", reply_markup=threads_menu())

@bot.message_handler(func=lambda m: m.text == "🎮 Free Fire")
def show_freefire(message):
    send_clean(message.from_user.id, "👇 Free Fire UC:", reply_markup=freefire_menu())

@bot.message_handler(func=lambda m: m.text == "⬅️ Orqaga")
def back_to_main(message):
    send_clean(message.from_user.id, "Asosiy menyu:", reply_markup=main_menu(message.from_user.id))
    # ========================
# HISOBIM (БАЛАНС)
# ========================
@bot.message_handler(func=lambda m: m.text == "💳 Hisobim")
def show_balance(message):
    user_id = message.from_user.id
    bal = get_balance(user_id)
    topup = get_total_topup(user_id)
    send_clean(
        user_id,
        f"🔑 Sizning ID raqamingiz: {user_id}\n\n"
        f"💵 Balansingiz: {bal} so'm\n"
        f"💰 Jami to'ldirilgan so'mma: {topup} so'm",
        reply_markup=main_menu(user_id)
    )

# ========================
# PUL KIRITISH (ПОПОЛНЕНИЕ)
# ========================
@bot.message_handler(func=lambda m: m.text == "💳 Pul kiritish")
def topup(message):
    user_id = message.from_user.id
    send_clean(
        user_id,
        f"💳 Pul kiritish\n\n"
        f"Quyidagi kartaga o'tkazing:\n"
        f"{CARD_NUMBER}\n\n"
        f"To'lovni amalga oshirgandan so'ng, chekni rasm sifatida yuboring.",
        reply_markup=back_kb()
    )
    bot.register_next_step_handler(message, handle_receipt)


def handle_receipt(message):
    user_id = message.from_user.id
    if message.text == "⬅️ Orqaga":
        send_clean(user_id, "Asosiy menyu:", reply_markup=main_menu(user_id))
        return
    if not message.photo:
        send_clean(user_id, "Iltimos, chekni rasm sifatida yuboring.", reply_markup=back_kb())
        bot.register_next_step_handler(message, handle_receipt)
        return
    photo_id = message.photo[-1].file_id
    conn = sqlite3.connect("smm.db")
    c = conn.cursor()
    c.execute("INSERT INTO pending_payments (user_id, photo_id) VALUES (?, ?)", (user_id, photo_id))
    payment_id = c.lastrowid
    conn.commit()
    conn.close()
    send_clean(user_id, "✅ Chek tekshiruvga yuborildi.", reply_markup=main_menu(user_id))
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"approve_{payment_id}"),
        types.InlineKeyboardButton("❌ Rad etish", callback_data=f"reject_{payment_id}")
    )
    bot.send_photo(ADMIN_ID, photo_id, caption=f"💳 Yangi chek\nUser: {user_id}\nID: {payment_id}", reply_markup=markup)

# ========================
# REFERAL
# ========================
@bot.message_handler(func=lambda m: m.text == "👥 Referal")
def show_referral(message):
    user_id = message.from_user.id
    conn = sqlite3.connect("smm.db")
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users WHERE ref_by=?", (user_id,))
    ref_count = c.fetchone()[0]
    conn.close()
    bot_username = bot.get_me().username
    send_clean(
        user_id,
        f"Sizning referallaringiz: {ref_count} ta\n\n"
        f"✨ Do'st taklif qiling — daromad oling!\n\n"
        f"Siz taklif qilgan har bir foydalanuvchi kiritgan summadan sizga 1% bonus beriladi 🤝\n\n"
        f"🔗 Havolangizni ulashing va daromadni boshlang!\n\n"
        f"https://t.me/{bot_username}?start=ref_{user_id}",
        reply_markup=main_menu(user_id)
    )

# ========================
# BUYURTMALARIM
# ========================
@bot.message_handler(func=lambda m: m.text == "📊 Buyurtmalarim")
def show_orders(message):
    user_id = message.from_user.id
    conn = sqlite3.connect("smm.db")
    c = conn.cursor()
    c.execute("SELECT id, service, status FROM orders WHERE user_id=? ORDER BY id DESC LIMIT 10", (user_id,))
    rows = c.fetchall()
    conn.close()
    if not rows:
        send_clean(user_id, "📊 Sizda hali buyurtmalar yo'q.", reply_markup=main_menu(user_id))
        return
    text = "📊 Buyurtmalarim:\n\n"
    for oid, service, status in rows:
        text += f"{oid} - {service} - [{status}]\n"
    send_clean(user_id, text, reply_markup=main_menu(user_id))

# ========================
# KANAL ULASH
# ========================
@bot.message_handler(func=lambda m: m.text == "📢 Kanal ulash")
def show_channel(message):
    send_clean(
        message.from_user.id,
        f"📢 «Kanalim» bo'limidan foydalanish uchun botga kanalingizni ulashingiz kerak.\n\n"
        f"Buning uchun 3 xil usuldan birini bajaring 👇\n\n"
        f"1️⃣ «Kanallar ro'yxati» tugmasini bosing va kanalni tanlang!\n\n"
        f"2️⃣ Kanalingiz havolasini (masalan: https://t.me/neosmnn yoki @neosmnn) yuboring!\n\n"
        f"3️⃣ Kanalingizdagi istalgan postni botga ulashib yuboring!\n\n"
        f"⚠️ Faqat ochiq (public) kanal tanlang!",
        reply_markup=main_menu(message.from_user.id)
    )

# ========================
# QO'LLAB-QUVVATLASH
# ========================
@bot.message_handler(func=lambda m: m.text == "☎️ Qo'llab-quvvatlash")
def show_support(message):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("☎️ Qo'llab-quvvatlash", url=f"https://t.me/{SUPPORT_USERNAME.replace('@', '')}"))
    send_clean(
        message.from_user.id,
        f"📢 Bot yangiliklari: @neosmnn\n"
        f"👤 Qo'llab-quvvatlash: {SUPPORT_USERNAME}\n\n"
        f"❓ Sizga qanday yordam kerak.",
        reply_markup=main_menu(message.from_user.id)
    )
    bot.send_message(message.from_user.id, "👇", reply_markup=markup)

# ========================
# HAMKORLIK DASTURI
# ========================
@bot.message_handler(func=lambda m: m.text == "🤝 Hamkorlik dasturi")
def show_partnership(message):
    send_clean(
        message.from_user.id,
        f"⚙️ Api dokument:\nhttps://neosmm.uz/api/\n\n"
        f"🔑 Api xizmat:\nhttps://neosmm.uz/api/v2\n\n"
        f"🔑 Sizning API kalitingiz: Yo'q\n"
        f"💵 Balansingiz: {get_balance(message.from_user.id)} so'm",
        reply_markup=main_menu(message.from_user.id)
    )

# ========================
# DONAT QILISH
# ========================
@bot.message_handler(func=lambda m: m.text == "💎 Donat qilish")
def show_donat(message):
    send_clean(message.from_user.id, "💎 Donat qilish bo'limi tez orada ishga tushadi.", reply_markup=main_menu(message.from_user.id))

# ========================
# PREMIUM, STARS, GIFT (РУЧНОЙ РЕЖИМ)
# ========================
@bot.message_handler(func=lambda m: m.text == "⭐ Premium, Stars, Gift")
def show_premium(message):
    user_id = message.from_user.id
    markup = types.InlineKeyboardMarkup(row_width=1)
    # Stars
    for key, price, label in get_prices_by_category("stars"):
        markup.add(types.InlineKeyboardButton(f"⭐ {label} - {price} so'm", callback_data=f"buy_{key}"))
    # Premium
    for key, price, label in get_prices_by_category("premium"):
        markup.add(types.InlineKeyboardButton(f"💎 Premium {label} - {price} so'm", callback_data=f"buy_{key}"))
    markup.add(types.InlineKeyboardButton("⬅️ Orqaga", callback_data="back_to_services"))
    send_clean(user_id, "⭐ Premium, Stars, Gift:\n\n👇 Xizmatlardan birini tanlang:", reply_markup=markup)

# ========================
# ОБРАБОТЧИКИ КНОПОК "ORQAGA" ДЛЯ УСЛУГ (inline)
# ========================
@bot.callback_query_handler(func=lambda call: call.data == "back_to_services")
def back_to_services(cb):
    bot.delete_message(cb.from_user.id, cb.message.message_id)
    send_clean(cb.from_user.id, "🛍 Xizmatlar:", reply_markup=services_menu())

# ========================
# ПОКУПКА (РУЧНАЯ ВЫДАЧА)
# ========================
@bot.callback_query_handler(func=lambda call: call.data.startswith("buy_"))
def process_buy(call):
    user_id = call.from_user.id
    key = call.data.replace("buy_", "")
    price = get_price(key)
    bal = get_balance(user_id)
    if bal < price:
        bot.answer_callback_query(call.id, f"❌ Mablag' yetarli emas. Kerak: {price} so'm, sizda: {bal} so'm.", show_alert=True)
        return
    username = call.from_user.username
    if not username:
        bot.answer_callback_query(call.id, "❌ Telegram'da username o'rnatilmagan.", show_alert=True)
        return
    update_balance(user_id, -price)
    conn = sqlite3.connect("smm.db")
    c = conn.cursor()
    c.execute("INSERT INTO orders (user_id, service, amount, price, status) VALUES (?, ?, ?, ?, 'pending')",
              (user_id, key, 1, price))
    order_id = c.lastrowid
    conn.commit()
    conn.close()
    bot.answer_callback_query(call.id, "✅ Buyurtma yaratildi!")
    send_clean(user_id, f"✅ {key} uchun buyurtma yaratildi. Admin tez orada bajaradi.", reply_markup=main_menu(user_id))
    bot.send_message(ADMIN_ID,
        f"🆕 Yangi buyurtma!\n"
        f"Xizmat: {key}\n"
        f"User: {user_id}\n"
        f"Username: @{username}\n"
        f"Narx: {price} so'm\n"
        f"Order ID: {order_id}\n\n"
        f"Qo'lda bajaring va quyidagi tugmani bosing.",
        reply_markup=types.InlineKeyboardMarkup().add(
            types.InlineKeyboardButton("✅ Bajarildi", callback_data=f"complete_order_{order_id}")
        ))

# ========================
# ЗАВЕРШЕНИЕ ЗАКАЗА
# ========================
@bot.callback_query_handler(func=lambda call: call.data.startswith("complete_order_"))
def complete_order(call):
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "❌ Ruxsat yo'q")
        return
    order_id = int(call.data.split("_")[2])
    conn = sqlite3.connect("smm.db")
    c = conn.cursor()
    c.execute("UPDATE orders SET status='completed' WHERE id=?", (order_id,))
    c.execute("SELECT user_id FROM orders WHERE id=?", (order_id,))
    row = c.fetchone()
    conn.commit()
    conn.close()
    if row:
        bot.send_message(row[0], f"✅ Buyurtmangiz №{order_id} bajarildi!")
    bot.edit_message_reply_markup(call.from_user.id, call.message.message_id, reply_markup=None)
    bot.answer_callback_query(call.id, "✅ Bajarildi deb belgilandi")

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
    conn = sqlite3.connect("smm.db")
    c = conn.cursor()
    c.execute("SELECT user_id FROM pending_payments WHERE id=?", (payment_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        bot.answer_callback_query(call.id, "❌ Topilmadi")
        return
    user_id = row[0]
    if action == "approve":
        bot.send_message(ADMIN_ID, f"💰 {user_id} uchun summani kiriting:")
        bot.register_next_step_handler_by_chat_id(ADMIN_ID, lambda msg: confirm_amount(msg, payment_id, user_id))
    else:
        conn = sqlite3.connect("smm.db")
        c = conn.cursor()
        c.execute("UPDATE pending_payments SET status='rejected' WHERE id=?", (payment_id,))
        conn.commit()
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
    conn = sqlite3.connect("smm.db")
    c = conn.cursor()
    c.execute("UPDATE users SET total_topup = total_topup + ? WHERE user_id=?", (amount, user_id))
    c.execute("UPDATE pending_payments SET status='approved', amount=? WHERE id=?", (amount, payment_id))
    conn.commit()
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
