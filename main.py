import os
from flask import Flask, request
import telebot

# Получаем токен из настроек Render. Если его там нет — ставим ваш токен текстом для надежности
BOT_TOKEN = os.environ.get('BOT_TOKEN') or '8874298910:AAEx5QaEbVHrxyVwAHcVlaZc4H4MnzkeDK0'
bot = telebot.TeleBot(BOT_TOKEN)

app = Flask(__name__)

# Сюда Telegram будет присылать сообщения пользователей
@app.route('/webhook', methods=['POST'])
def get_message():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return '', 200
    else:
        return 'Forbidden', 403

# Сюда заходим в браузере для проверки
@app.route('/')
def webhook_index():
    return "Бот успешно запущен на Render и готов к работе!", 200

# --- СЮДА ВСТАВЛЯЙТЕ СВОИ КНОПКИ И ЛОГИКУ БОТА ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "Привет! Твой SMM-бот наконец-то полностью ожил на бесплатном сервере! 🚀")

@bot.message_handler(func=lambda message: True)
def echo_all(message):
    bot.reply_to(message, f"Вы написали: {message.text}")
# --------------------------------------------------

# Принудительно ставим вебхук на надежный и простой адрес /webhook
try:
    bot.remove_webhook()
    bot.set_webhook(url="https://onrender.com")
    print("Вебхук успешно установлен на /webhook!")
except Exception as e:
    print(f"Ошибка вебхука: {e}")

if __name__ == "__main__":
    PORT = int(os.environ.get('PORT', 10000))
    app.run(host="0.0.0.0", port=PORT)
