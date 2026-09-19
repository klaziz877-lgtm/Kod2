import os
from flask import Flask, request
import telebot

# Получаем токен из переменных окружения Render
BOT_TOKEN = os.environ.get('BOT_TOKEN')
bot = telebot.TeleBot(BOT_TOKEN)

app = Flask(__name__)

# Получаем URL вашего приложения на Render
RENDER_URL = os.environ.get('RENDER_EXTERNAL_URL')

# Функция, которая безопасно настроит вебхук при самом первом HTTP-запросе к серверу
@app.before_request
def setup_webhook_once():
    # Чтобы не дергать Telegram на каждый чих, проверим, выполняли ли мы это ранее
    if not getattr(app, '_webhook_is_set', False):
        if RENDER_URL:
            bot.remove_webhook()
            bot.set_webhook(url=f"{RENDER_URL}/webhook")
            print(f"--- ВЕБХУК УСПЕШНО УСТАНОВЛЕН НА: {RENDER_URL}/webhook ---")
            app._webhook_is_set = True
        else:
            print("ВНИМАНИЕ: Переменная RENDER_EXTERNAL_URL не найдена в окружении!")

# Сюда Telegram будет присылать сообщения пользователей
@app.route("/webhook", methods=["POST"])
def get_message():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode("utf-8")
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return "!", 200
    else:
        return "Forbidden", 403

# Сюда будет стучаться UptimeRobot (и это автоматически активирует функцию установки вебхука выше)
@app.route("/")
def webhook_index():
    return "Бот работает и не спит!", 200

# --- ЛОГИКА ВАШЕГО БОТА ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "Привет! Это твой Telegram-бот, запущенный на Render!")

@bot.message_handler(func=lambda message: True)
def echo_all(message):
    bot.reply_to(message, f"Вы написали: {message.text}")

# Этот блок сработает, если вы запустите код локально на Pydroid 3
if __name__ == "__main__":
    PORT = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=PORT)
    
