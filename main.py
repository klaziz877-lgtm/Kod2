import os
import time
import sqlite3
import telebot
from telebot import types
from flask import Flask, request

BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
CARD_NUMBER = os.environ.get("CARD_NUMBER", "8600 0000 0000 0000")
SUPPORT_USERNAME = "@assasinsmmbotadmin"

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN not found")

bot = telebot.TeleBot(BOT_TOKEN)
bot.threaded = False
app = Flask(__name__)


def init_db():
    conn = sqlite3.connect("smm.db")
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, balance INTEGER DEFAULT 0, lang TEXT DEFAULT 'ru', ref_by INTEGER DEFAULT 0)")
    c.execute("CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, service TEXT, amount INTEGER, price INTEGER, status TEXT DEFAULT 'pending', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
    c.execute("CREATE TABLE IF NOT EXISTS prices (key TEXT PRIMARY KEY, value INTEGER, label TEXT, category TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS pending_payments (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount INTEGER, photo_id TEXT, status TEXT DEFAULT 'pending', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
    defaults = [
        ("stars_50", 8000, "50 Stars", "stars"),
        ("stars_100", 15000, "100 Stars", "stars"),
        ("stars_250", 35000, "250 Stars", "stars"),
        ("stars_500", 70000, "500 Stars", "stars"),
        ("stars_1000", 130000, "1000 Stars", "stars"),
        ("stars_2500", 320000, "2500 Stars", "stars"),
        ("stars_5000", 600000, "5000 Stars", "stars"),
        ("stars_10000", 1150000, "10000 Stars", "stars"),
        ("premium_1m", 30000, "1 месяц", "premium"),
        ("premium_3m", 85000, "3 месяца", "premium"),
        ("premium_6m", 165000, "6 месяцев", "premium"),
        ("premium_12m", 320000, "12 месяцев", "premium"),
        ("nakrutka_tg_100", 10000, "100 подписчиков", "nakrutka_tg"),
        ("nakrutka_tg_500", 45000, "500 подписчиков", "nakrutka_tg"),
        ("nakrutka_tg_1000", 85000, "1000 подписчиков", "nakrutka_tg"),
        ("nakrutka_inst_100", 12000, "100 подписчиков", "nakrutka_inst"),
        ("nakrutka_inst_500", 50000, "500 подписчиков", "nakrutka_inst"),
        ("nakrutka_inst_1000", 95000, "1000 подписчиков", "nakrutka_inst"),
    ]
    for k, v, label, cat in defaults:
        c.execute("INSERT OR IGNORE INTO prices (key, value, label, category) VALUES (?, ?, ?, ?)", (k, v, label, cat))
    conn.commit()
    conn.close()


init_db()


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


def add_price(key, value, label, category):
    conn = sqlite3.connect("smm.db")
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO prices (key, value, label, category) VALUES (?, ?, ?, ?)", (key, value, label, category))
    conn.commit()
    conn.close()


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


TEXTS = {
    "ru": {
        "balance": "Баланс", "topup": "Пополнить баланс",
        "bonus": "Бонусы", "orders": "Мои заказы",
        "support": "Поддержка", "lang": "Язык",
        "stars": "Telegram Stars", "premium": "Telegram Premium",
        "nakrutka_tg": "Накрутка Telegram", "nakrutka_inst": "Накрутка Instagram",
        "choose_section": "Выберите нужный раздел:",
        "your_balance": "Ваш баланс: {bal} сум",
        "not_enough": "Недостаточно средств. Нужно {price} сум, у вас {bal} сум.",
        "order_created": "Заказ на {service} создан. Ожидайте выдачи.",
        "no_username": "У вас не установлен username в Telegram.",
        "support_text": "Поддержка: @assasinsmmbotadmin",
        "payment_sent": "Чек отправлен на проверку.",
    },
    "uz": {
        "balance": "Balans", "topup": "Balansni to'ldirish",
        "bonus": "Bonuslar", "orders": "Buyurtmalarim",
        "support": "Qo'llab-quvvatlash", "lang": "Til",
        "stars": "Telegram Stars", "premium": "Telegram Premium",
        "nakrutka_tg": "Telegram nakrutka", "nakrutka_inst": "Instagram nakrutka",
        "choose_section": "Kerakli bo'limni tanlang:",
        "your_balance": "Sizning balansingiz: {bal} so'm",
        "not_enough": "Mablag' yetarli emas. Kerak: {price} so'm, sizda: {bal} so'm.",
        "order_created": "{service} uchun buyurtma yaratildi.",
        "no_username": "Telegram'da username o'rnatilmagan.",
        "support_text": "Qo'llab-quvvatlash: @assasinsmmbotadmin",
        "payment_sent": "Chek tekshiruvga yuborildi.",
    }
}


def get_lang(user_id):
    conn = sqlite3.connect("smm.db")
    c = conn.cursor()
    c.execute("SELECT lang FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else "ru"


def t(user_id, key, **kwargs):
    lang = get_lang(user_id)
    text = TEXTS.get(lang, TEXTS["ru"]).get(key, key)
    return text.format(**kwargs) if kwargs else text


def main_menu(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        types.KeyboardButton(t(user_id, "stars")),
        types.KeyboardButton(t(user_id, "premium")),
        types.KeyboardButton(t(user_id, "nakrutka_tg")),
        types.KeyboardButton(t(user_id, "nakrutka_inst")),
        types.KeyboardButton(t(user_id, "balance")),
        types.KeyboardButton(t(user_id, "bonus")),
        types.KeyboardButton(t(user_id, "orders")),
        types.KeyboardButton(t(user_id, "support")),
        types.KeyboardButton(t(user_id, "lang")),
    )
    return markup


def back_kb():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    markup.add(types.KeyboardButton("Назад"))
    return markup


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


@bot.message_handler(commands=["start"])
def send_welcome(message):
    user_id = message.from_user.id
    user_name = message.from_user.first_name or "друг"
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
    bot.send_message(
        user_id,
        f"Привет, {user_name}!\n\n"
        f"Добро пожаловать в ASSASIN SMM BOT.\n\n"
        f"Здесь ты можешь купить:\n"
        f"Telegram Stars\n"
        f"Telegram Premium\n"
        f"Накрутку Telegram\n"
        f"Накрутку Instagram\n\n"
        f"Выбери нужный раздел ниже:",
        reply_markup=main_menu(user_id)
    )


@bot.message_handler(func=lambda m: m.text == t(m.from_user.id, "balance"))
def show_balance(message):
    user_id = message.from_user.id
    bal = get_balance(user_id)
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    markup.add(types.KeyboardButton(t(user_id, "topup")), types.KeyboardButton("Назад"))
    bot.send_message(user_id, t(user_id, "your_balance", bal=bal), reply_markup=markup)


@bot.message_handler(func=lambda m: m.text == t(m.from_user.id, "topup"))
def topup(message):
    user_id = message.from_user.id
    bot.send_message(user_id, f"Пополнение баланса\n\nПереведите сумму на карту:\n{CARD_NUMBER}\n\nПосле оплаты отправьте скриншот чека.", reply_markup=back_kb())
    bot.register_next_step_handler(message, handle_receipt)


def handle_receipt(message):
    user_id = message.from_user.id
    if message.text == "Назад":
        bot.send_message(user_id, t(user_id, "choose_section"), reply_markup=main_menu(user_id))
        return
    if not message.photo:
        bot.send_message(user_id, "Отправьте именно фото чека.")
        bot.register_next_step_handler(message, handle_receipt)
        return
    photo_id = message.photo[-1].file_id
    conn = sqlite3.connect("smm.db")
    c = conn.cursor()
    c.execute("INSERT INTO pending_payments (user_id, photo_id) VALUES (?, ?)", (user_id, photo_id))
    payment_id = c.lastrowid
    conn.commit()
    conn.close()
    bot.send_message(user_id, t(user_id, "payment_sent"))
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("Подтвердить", callback_data=f"approve_{payment_id}"),
        types.InlineKeyboardButton("Отклонить", callback_data=f"reject_{payment_id}")
    )
    bot.send_photo(ADMIN_ID, photo_id, caption=f"Новый чек\nUser: {user_id}\nID: {payment_id}", reply_markup=markup)


@bot.message_handler(func=lambda m: m.text == t(m.from_user.id, "stars"))
def stars_menu(message):
    user_id = message.from_user.id
    markup = types.InlineKeyboardMarkup(row_width=1)
    for key, price, label in get_prices_by_category("stars"):
        markup.add(types.InlineKeyboardButton(f"{label} - {price} сум", callback_data=f"buy_{key}"))
    markup.add(types.InlineKeyboardButton("Назад", callback_data="back_to_menu"))
    bot.send_message(user_id, "Выберите количество Stars:", reply_markup=markup)


@bot.message_handler(func=lambda m: m.text == t(m.from_user.id, "premium"))
def premium_menu(message):
    user_id = message.from_user.id
    markup = types.InlineKeyboardMarkup(row_width=1)
    for key, price, label in get_prices_by_category("premium"):
        markup.add(types.InlineKeyboardButton(f"{label} - {price} сум", callback_data=f"buy_{key}"))
    markup.add(types.InlineKeyboardButton("Назад", callback_data="back_to_menu"))
    bot.send_message(user_id, "Выберите срок Premium:", reply_markup=markup)


@bot.message_handler(func=lambda m: m.text == t(m.from_user.id, "nakrutka_tg"))
def nakrutka_tg_menu(message):
    user_id = message.from_user.id
    markup = types.InlineKeyboardMarkup(row_width=1)
    for key, price, label in get_prices_by_category("nakrutka_tg"):
        markup.add(types.InlineKeyboardButton(f"{label} - {price} сум", callback_data=f"buy_{key}"))
    markup.add(types.InlineKeyboardButton("Назад", callback_data="back_to_menu"))
    bot.send_message(user_id, "Выберите количество:", reply_markup=markup)


@bot.message_handler(func=lambda m: m.text == t(m.from_user.id, "nakrutka_inst"))
def nakrutka_inst_menu(message):
    user_id = message.from_user.id
    markup = types.InlineKeyboardMarkup(row_width=1)
    for key, price, label in get_prices_by_category("nakrutka_inst"):
        markup.add(types.InlineKeyboardButton(f"{label} - {price} сум", callback_data=f"buy_{key}"))
    markup.add(types.InlineKeyboardButton("Назад", callback_data="back_to_menu"))
    bot.send_message(user_id, "Выберите количество:", reply_markup=markup)


@bot.callback_query_handler(func=lambda call: call.data.startswith("buy_"))
def process_buy(call):
    user_id = call.from_user.id
    key = call.data.replace("buy_", "")
    price = get_price(key)
    bal = get_balance(user_id)
    if bal < price:
        bot.answer_callback_query(call.id, t(user_id, "not_enough", price=price, bal=bal), show_alert=True)
        return
    username = call.from_user.username
    if not username:
        bot.answer_callback_query(call.id, t(user_id, "no_username"), show_alert=True)
        return

    update_balance(user_id, -price)
    conn = sqlite3.connect("smm.db")
    c = conn.cursor()
    c.execute("INSERT INTO orders (user_id, service, amount, price, status) VALUES (?, ?, ?, ?, 'pending')",
              (user_id, key, 1, price))
    order_id = c.lastrowid
    conn.commit()
    conn.close()

    bot.answer_callback_query(call.id, "Заказ создан!")
    bot.send_message(user_id, t(user_id, "order_created", service=key))

    bot.send_message(ADMIN_ID,
        f"Новый заказ!\n"
        f"Услуга: {key}\n"
        f"User: {user_id}\n"
        f"Username: @{username}\n"
        f"Price: {price} сум\n"
        f"Order ID: {order_id}\n\n"
        f"Выполните вручную и нажмите кнопку ниже.",
        reply_markup=types.InlineKeyboardMarkup().add(
            types.InlineKeyboardButton("Выполнено", callback_data=f"complete_order_{order_id}")
        ))


@bot.callback_query_handler(func=lambda call: call.data.startswith("complete_order_"))
def complete_order(call):
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "Нет доступа")
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
        bot.send_message(row[0], f"Ваш заказ №{order_id} выполнен!")
    bot.edit_message_reply_markup(call.from_user.id, call.message.message_id, reply_markup=None)
    bot.answer_callback_query(call.id, "Отмечено как выполненное")


@bot.message_handler(func=lambda m: m.text == t(m.from_user.id, "bonus"))
def bonus(message):
    user_id = message.from_user.id
    bot.send_message(user_id, f"Пригласите друга и получите 500 сум!\nВаша ссылка: https://t.me/{bot.get_me().username}?start=ref_{user_id}")


@bot.message_handler(func=lambda m: m.text == t(m.from_user.id, "orders"))
def orders(message):
    user_id = message.from_user.id
    conn = sqlite3.connect("smm.db")
    c = conn.cursor()
    c.execute("SELECT service, amount, status FROM orders WHERE user_id=? ORDER BY id DESC LIMIT 10", (user_id,))
    rows = c.fetchall()
    conn.close()
    if not rows:
        bot.send_message(user_id, "У вас пока нет заказов.")
        return
    text = "Ваши последние заказы:\n\n"
    for s, a, st in rows:
        text += f"- {s} - {a} шт. [{st}]\n"
    bot.send_message(user_id, text)


@bot.message_handler(func=lambda m: m.text == t(m.from_user.id, "support"))
def support(message):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("Написать в поддержку", url=f"https://t.me/{SUPPORT_USERNAME.replace('@', '')}"))
    bot.send_message(message.from_user.id, t(message.from_user.id, "support_text"), reply_markup=markup)


@bot.message_handler(func=lambda m: m.text == t(m.from_user.id, "lang"))
def lang_menu(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(types.KeyboardButton("Русский"), types.KeyboardButton("O'zbekcha"))
    markup.add(types.KeyboardButton("Назад"))
    bot.send_message(message.from_user.id, "Выберите язык / Tilni tanlang:", reply_markup=markup)


@bot.message_handler(func=lambda m: m.text == "Русский")
def set_ru(message):
    conn = sqlite3.connect("smm.db")
    c = conn.cursor()
    c.execute("UPDATE users SET lang='ru' WHERE user_id=?", (message.from_user.id,))
    conn.commit()
    conn.close()
    bot.send_message(message.from_user.id, "Язык изменён на русский.", reply_markup=main_menu(message.from_user.id))


@bot.message_handler(func=lambda m: m.text == "O'zbekcha")
def set_uz(message):
    conn = sqlite3.connect("smm.db")
    c = conn.cursor()
    c.execute("UPDATE users SET lang='uz' WHERE user_id=?", (message.from_user.id,))
    conn.commit()
    conn.close()
    bot.send_message(message.from_user.id, "Til o'zgartirildi.", reply_markup=main_menu(message.from_user.id))


@bot.message_handler(func=lambda m: m.text == "Назад")
def back_to_menu(message):
    bot.send_message(message.from_user.id, t(message.from_user.id, "choose_section"), reply_markup=main_menu(message.from_user.id))


@bot.callback_query_handler(func=lambda call: call.data == "back_to_menu")
def back_cb(call):
    bot.delete_message(call.from_user.id, call.message.message_id)
    bot.send_message(call.from_user.id, t(call.from_user.id, "choose_section"), reply_markup=main_menu(call.from_user.id))


@bot.callback_query_handler(func=lambda call: call.data.startswith("approve_") or call.data.startswith("reject_"))
def handle_payment(call):
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "Нет доступа")
        return
    action, payment_id = call.data.split("_")
    payment_id = int(payment_id)
    conn = sqlite3.connect("smm.db")
    c = conn.cursor()
    c.execute("SELECT user_id FROM pending_payments WHERE id=?", (payment_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        bot.answer_callback_query(call.id, "Не найден")
        return
    user_id = row[0]
    if action == "approve":
        bot.send_message(ADMIN_ID, f"Введите сумму для пользователя {user_id}:")
        bot.register_next_step_handler_by_chat_id(ADMIN_ID, lambda msg: confirm_amount(msg, payment_id, user_id))
    else:
        conn = sqlite3.connect("smm.db")
        c = conn.cursor()
        c.execute("UPDATE pending_payments SET status='rejected' WHERE id=?", (payment_id,))
        conn.commit()
        conn.close()
        bot.send_message(user_id, "Ваш чек отклонён.")
        bot.answer_callback_query(call.id, "Отклонено")


def confirm_amount(message, payment_id, user_id):
    try:
        amount = int(message.text.strip())
    except ValueError:
        bot.send_message(ADMIN_ID, "Введите число.")
        return
    update_balance(user_id, amount)
    conn = sqlite3.connect("smm.db")
    c = conn.cursor()
    c.execute("UPDATE pending_payments SET status='approved', amount=? WHERE id=?", (amount, payment_id))
    conn.commit()
    conn.close()
    bot.send_message(user_id, f"Ваш баланс пополнен на {amount} сум!")
    bot.send_message(ADMIN_ID, f"Зачислено {amount} сум пользователю {user_id}.")


@bot.message_handler(commands=["admin"])
def admin_panel(message):
    if message.from_user.id != ADMIN_ID:
        bot.send_message(message.from_user.id, "У вас нет доступа.")
        return
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("Цены Stars", callback_data="admin_stars"),
        types.InlineKeyboardButton("Цены Premium", callback_data="admin_premium"),
        types.InlineKeyboardButton("Накрутка TG", callback_data="admin_nakrutka_tg"),
        types.InlineKeyboardButton("Накрутка Inst", callback_data="admin_nakrutka_inst"),
        types.InlineKeyboardButton("Добавить услугу", callback_data="admin_add"),
        types.InlineKeyboardButton("Статистика", callback_data="admin_stats"),
        types.InlineKeyboardButton("Пользователи", callback_data="admin_users"),
    )
    bot.send_message(message.from_user.id, "Админ-панель:", reply_markup=markup)


@bot.callback_query_handler(func=lambda call: call.data.startswith("complete_order_"))
def complete_order(call):
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "Нет доступа")
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
        bot.send_message(row[0], f"Ваш заказ №{order_id} выполнен!")
    bot.edit_message_reply_markup(call.from_user.id, call.message.message_id, reply_markup=None)
    bot.answer_callback_query(call.id, "Отмечено как выполненное")
