import os
import logging
import psycopg2
from flask import Flask, request
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext, Dispatcher
import openai

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Получаем токены из переменных окружения
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")

openai.api_key = OPENAI_API_KEY

# Настройка подключения к базе данных PostgreSQL
conn = None
if DATABASE_URL:
    try:
        conn = psycopg2.connect(DATABASE_URL, sslmode="require")
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS bookings (
                id SERIAL PRIMARY KEY,
                username TEXT,
                name TEXT,
                check_in DATE,
                nights INTEGER,
                created_at TIMESTAMP DEFAULT NOW()
            );
        """)
        conn.commit()
        logger.info("База данных подключена и таблицы созданы.")
    except Exception as e:
        logger.error(f"Ошибка подключения к БД: {e}")

# Создаём Flask-приложение
app = Flask(__name__)

# Инициализация бота
updater = Updater(BOT_TOKEN, use_context=True)
dispatcher = updater.dispatcher


# Команда /start
def start(update: Update, context: CallbackContext) -> None:
    buttons = [[KeyboardButton("📍 Локация"), KeyboardButton("💼 Услуги")],
               [KeyboardButton("💰 Цены"), KeyboardButton("🏨 Бронирование")]]
    keyboard = ReplyKeyboardMarkup(buttons, resize_keyboard=True)
    update.message.reply_text("Привет! Добро пожаловать в OqtoshSoy! Чем могу помочь?", reply_markup=keyboard)


# Команда /help
def help_command(update: Update, context: CallbackContext) -> None:
    update.message.reply_text(
        "Я помогу вам узнать о курорте OqtoshSoy! Вы можете нажать на кнопки или отправить команду:\n"
        "/start - Главное меню\n"
        "/booking - Забронировать номер\n"
        "/help - Помощь")


# Обработчик сообщений с GPT-4
def chat_with_gpt(update: Update, context: CallbackContext) -> None:
    user_message = update.message.text
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[{"role": "system", "content": "Ты помощник курорта OqtoshSoy. Отвечай вежливо и понятно."},
                      {"role": "user", "content": user_message}]
        )
        bot_response = response['choices'][0]['message']['content']
    except Exception as e:
        logger.error(f"Ошибка GPT: {e}")
        bot_response = "Извините, сейчас не могу ответить. Попробуйте позже."

    update.message.reply_text(bot_response)


# Flask webhook
@app.route("/webhook", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(), updater.bot)
    dispatcher.process_update(update)
    return "OK", 200


# Запуск бота
def run_bot():
    updater.start_polling()
    updater.idle()


if __name__ == "__main__":
    run_bot()