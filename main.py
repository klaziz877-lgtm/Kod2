import os
import telebot
from flask import Flask, request

# ========================
# НАСТРОЙКИ
# ========================
BOT_TOKEN = os.environ.get("BOT_TOKEN")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не найден в Render Environment!")

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

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

# ========================
# ПРОВЕРКА СЕРВЕРА
# ========================
@app.route("/", methods=["GET"])
def home():
    return "SMM-бот успешно запущен на Render!", 200

# ========================
# КОМАНДА /START
# ========================
@bot.message_handler(commands=["start"])
def send_welcome(message):
    bot.reply_to(
        message,
        "Привет! SMM-бот запущен и готов к работе."
    )

# ========================
# ОТВЕТ НА СООБЩЕНИЯ
# ========================
@bot.message_handler(func=lambda message: True)
def echo_all(message):
    bot.reply_to(
        message,
        f"Вы написали: {message.text}"
    )

# ========================
# УСТАНОВКА WEBHOOK
# ========================
def setup_webhook():
    try:
        bot.remove_webhook()
        
        render_url = os.environ.get("RENDER_EXTERNAL_URL")
        
        if not render_url:
            raise RuntimeError("RENDER_EXTERNAL_URL не найден в переменных окружения!")
            
        webhook_url = f"{render_url}/webhook"
        bot.set_webhook(url=webhook_url)
        print(f"✅ Вебхук успешно установлен: {webhook_url}")
        
    except Exception as e:
        print(f"❌ Ошибка установки вебхука: {e}")

# ========================
# ЗАПУСК
# ========================
# ВАЖНО: Вызываем установку вебхука ЗДЕСЬ, вне блока if __name__ == "__main__"
# Это гарантирует, что Gunicorn выполнит установку при старте сервера.
setup_webhook()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
