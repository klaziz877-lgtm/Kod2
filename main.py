import os
from flask import Flask, request
import telebot

# Получаем токен из переменных окружения Render
BOT_TOKEN = os.environ.get('BOT_TOKEN')
bot = telebot.TeleBot(BOT_TOKEN)

app = Flask(__name__)

# 1. Сюда Telegram будет присылать сообщения пользователей
@app.route('/' + BOT_TOKEN, methods=['POST'])
def get_message():
    json_string = request.get_data().decode('utf-8')
    update = telebot.types.Update.de_json(json_string)
    bot.process_new_updates([update])
    return "!", 200

# 2. Сюда будет стучаться UptimeRobot, чтобы сервер не спал
@app.route('/')
def webhook_index():
    return "Бот работает и не спит!", 200

# --- ПРИМЕР ЛОГИКИ ВАШЕГО БОТА ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "Привет! Это твой SMM-бот, запущенный на Render.com! 🚀")

@bot.message_handler(func=lambda message: True)
def echo_all(message):
    bot.reply_to(message, f"Вы написали: {message.text}")
# ----------------------------------

if __name__ == "__main__":
    # Порт Render выдает автоматически. Если его нет — берем 5000 по умолчанию
    PORT = int(os.environ.get('PORT', 5000))
    
    # ВАЖНО: Указываем Telegram, куда слать сообщения. 
    # Замените URL на ваш адрес из панели Render (обязательно с / в конце перед токеном)
    RENDER_URL = os.environ.get('RENDER_EXTERNAL_URL') # Render сам подставит URL вашего сервиса
    bot.remove_webhook()
    bot.set_webhook(url=f"{RENDER_URL}/{BOT_TOKEN}")
    
    # Запуск веб-сервера
    app.run(host="0.0.0.0", port=PORT)
