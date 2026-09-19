import os
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.utils.executor import start_webhook
from flask import Flask, request

# ========================
# НАСТРОЙКИ
# ========================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не найден!")

WEBHOOK_HOST = os.environ.get("RENDER_EXTERNAL_URL")
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"

WEBAPP_HOST = "0.0.0.0"
WEBAPP_PORT = int(os.environ.get("PORT", 10000))

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)
dp.middleware.setup(LoggingMiddleware())

app = Flask(__name__)

# ========================
# ХЭНДЛЕРЫ
# ========================
@dp.message_handler(commands=["start"])
async def send_welcome(message: types.Message):
    await message.reply("Привет! SMM-бот запущен и готов к работе.")

@dp.message_handler()
async def echo_all(message: types.Message):
    await message.reply(f"Вы написали: {message.text}")

# ========================
# ВЕБХУК
# ========================
@app.route(WEBHOOK_PATH, methods=["POST"])
def webhook():
    if request.headers.get("content-type") == "application/json":
        update = types.Update.de_json(request.get_data().decode("utf-8"))
        dp.process_update(update)
        return "OK", 200
    return "Forbidden", 403

@app.route("/", methods=["GET"])
def home():
    return "SMM-бот успешно запущен на Render!", 200

# ========================
# ЗАПУСК
# ========================
async def on_startup(dp):
    await bot.set_webhook(WEBHOOK_URL)
    print(f"✅ Вебхук установлен: {WEBHOOK_URL}")

async def on_shutdown(dp):
    await bot.delete_webhook()

if __name__ == "__main__":
    start_webhook(
        dispatcher=dp,
        webhook_path=WEBHOOK_PATH,
        on_startup=on_startup,
        on_shutdown=on_shutdown,
        skip_updates=True,
        host=WEBAPP_HOST,
        port=WEBAPP_PORT,
    )
