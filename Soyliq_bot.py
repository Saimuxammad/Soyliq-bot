import os
import logging
import asyncio
from flask import Flask, request
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
import openai
import psycopg2

# Загрузка переменных окружения
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
DATABASE_URL = os.getenv('DATABASE_URL')

if not TOKEN:
    raise RuntimeError("Ошибка: TELEGRAM_BOT_TOKEN не задан в переменных окружения.")
if not OPENAI_API_KEY:
    logging.warning("Предупреждение: OPENAI_API_KEY не задан. GPT-4 не будет работать.")
if not DATABASE_URL:
    logging.warning("Предупреждение: DATABASE_URL не задан. Подключение к базе данных не будет установлено.")

# Настройка API OpenAI
openai.api_key = OPENAI_API_KEY

# Подключение к PostgreSQL (если доступно)
db_conn = None
if DATABASE_URL:
    try:
        db_conn = psycopg2.connect(DATABASE_URL, sslmode='require')
        db_conn.set_session(autocommit=True)
    except Exception as e:
        logging.error(f"Ошибка подключения к базе данных: {e}")

# Настройка логирования
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация Flask
app = Flask(__name__)


@app.route('/')
def index():
    return "Бот работает!", 200


# Инициализация Telegram Application
application = Application.builder().token(TOKEN).build()


# Команда /start
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    welcome_text = (
        f"Здравствуйте, {user.first_name}! Добро пожаловать.\n"
        "Выберите опцию на клавиатуре ниже или напишите мне сообщение."
    )
    keyboard = [["Локация", "Услуги"], ["Цены", "Бронирование"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(welcome_text, reply_markup=reply_markup)


# Команда /help
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    help_text = (
        "Вот что я умею:\n"
        "/start - Перезапустить бота и показать меню\n"
        "/help - Показать эту справку\n\n"
        "Можете воспользоваться кнопками или написать любой вопрос."
    )
    await update.message.reply_text(help_text)


# Обработчики кнопок
async def location_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("🏢 Наш адрес: ул. Пример, 1, г. Город.")


async def services_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("📋 Мы предлагаем: проживание, питание, SPA и многое другое.")


async def prices_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("💰 Ознакомиться с актуальными ценами можно на нашем сайте.")


async def booking_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("📞 Для бронирования свяжитесь с нами по телефону.")


# Обработчик сообщений через OpenAI GPT-4
async def chatgpt_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_message = update.message.text
    try:
        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(
            None,
            lambda: openai.ChatCompletion.create(
                model="gpt-4",
                messages=[{"role": "user", "content": user_message}]
            )
        )
        reply_text = response['choices'][0]['message']['content'].strip()
    except Exception as e:
        logger.error(f"Ошибка API OpenAI: {e}")
        reply_text = "🤖 Ошибка при обработке запроса в GPT-4."

    await update.message.reply_text(reply_text)


# Обработчик ошибок
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(f"Ошибка обработки обновления: {context.error}")


# Регистрируем обработчики
application.add_handler(CommandHandler("start", start_command))
application.add_handler(CommandHandler("help", help_command))
application.add_handler(MessageHandler(filters.Regex('^(Локация)$'), location_handler))
application.add_handler(MessageHandler(filters.Regex('^(Услуги)$'), services_handler))
application.add_handler(MessageHandler(filters.Regex('^(Цены)$'), prices_handler))
application.add_handler(MessageHandler(filters.Regex('^(Бронирование)$'), booking_handler))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chatgpt_handler))
application.add_error_handler(error_handler)


# Вебхук для Telegram
@app.route(f"/{TOKEN}", methods=["POST"])
async def telegram_webhook():
    """Обработчик обновлений через вебхук."""
    if request.headers.get('content-type') == 'application/json':
        update_data = request.get_json()
        update = Update.de_json(update_data, application.bot)
        await application.initialize()
        try:
            await application.process_update(update)
        finally:
            await application.shutdown()
        return ('', 204)
    return ('Unsupported Media Type', 415)


# Запуск Flask (для хостинга на Heroku, AWS и т.д.)
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

