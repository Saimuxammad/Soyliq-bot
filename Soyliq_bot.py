import os
import logging
import asyncio

import openai
import psycopg2
from flask import Flask, request
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

# Загружаем переменные окружения
TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
DATABASE_URL = os.environ.get('DATABASE_URL')

if not TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")
if not OPENAI_API_KEY:
    logging.warning("OPENAI_API_KEY is not set. GPT-4 chat will not work.")
if not DATABASE_URL:
    logging.warning("DATABASE_URL is not set. Database connection will not be established.")

# Настраиваем ключ OpenAI API
openai.api_key = OPENAI_API_KEY

# Подключаемся к PostgreSQL (если DATABASE_URL задан)
db_conn = None
if DATABASE_URL:
    try:
        db_conn = psycopg2.connect(DATABASE_URL, sslmode='require')
        db_conn.set_session(autocommit=True)
    except Exception as e:
        logging.error(f"Failed to connect to the database: {e}")

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# Инициализируем Flask-приложение
app = Flask(__name__)
@app.route('/')
def index():
    return "Bot is running!"

if __name__ == "__main__":
    app.run()


# Инициализируем Telegram Application (PTB v20)
application = Application.builder().token(TOKEN).build()

# Обработчик команды /start
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет приветственное сообщение и показывает меню с кнопками."""
    user = update.effective_user
    welcome_text = (
        f"Здравствуйте, {user.first_name}! Добро пожаловать.\n"
        "Выберите опцию на клавиатуре ниже или напишите мне сообщение."
    )
    keyboard = [
        ["Локация", "Услуги"],
        ["Цены", "Бронирование"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(welcome_text, reply_markup=reply_markup)

# Обработчик команды /help
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет сообщение с подсказками по использованию бота."""
    help_text = (
        "Вот что я умею:\n"
        "/start - начать заново и показать меню\n"
        "/help - показать это сообщение\n\n"
        "Также вы можете воспользоваться кнопками ниже или написать любой вопрос для GPT-4."
    )
    await update.message.reply_text(help_text)

# Обработчики нажатий кнопок меню
async def location_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает нажатие кнопки 'Локация'."""
    await update.message.reply_text("🏢 Наш адрес: ул. Пример, 1, г. Город.")

async def services_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает нажатие кнопки 'Услуги'."""
    await update.message.reply_text("📋 Мы предлагаем следующие услуги: ...")

async def prices_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает нажатие кнопки 'Цены'."""
    await update.message.reply_text("💰 Актуальные цены вы можете найти на нашем сайте...")

async def booking_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает нажатие кнопки 'Бронирование'."""
    await update.message.reply_text("📞 Для бронирования свяжитесь с нами по телефону ...")

# Обработчик обычных сообщений: пересылает их в GPT-4 и возвращает ответ
async def chatgpt_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает сообщения пользователя через OpenAI GPT-4."""
    user_message = update.message.text
    try:
        loop = asyncio.get_running_loop()
        # Вызов OpenAI API в отдельном потоке, чтобы не блокировать event loop
        response = await loop.run_in_executor(
            None,
            lambda: openai.ChatCompletion.create(
                model="gpt-4",
                messages=[{"role": "user", "content": user_message}]
            )
        )
        reply_text = response['choices'][0]['message']['content'].strip()
    except Exception as e:
        logger.error(f"Error calling OpenAI API: {e}")
        reply_text = "🤖 Извините, произошла ошибка при обращении к GPT-4."
    await update.message.reply_text(reply_text)

# Обработчик ошибок для логирования исключений
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Логирует ошибки, возникшие при обработке обновлений."""
    logger.error("Exception while handling an update:", exc_info=context.error)

# Регистрируем обработчики в приложении Telegram
application.add_handler(CommandHandler("start", start_command))
application.add_handler(CommandHandler("help", help_command))
application.add_handler(MessageHandler(filters.Regex('^(Локация)$'), location_handler))
application.add_handler(MessageHandler(filters.Regex('^(Услуги)$'), services_handler))
application.add_handler(MessageHandler(filters.Regex('^(Цены)$'), prices_handler))
application.add_handler(MessageHandler(filters.Regex('^(Бронирование)$'), booking_handler))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chatgpt_handler))
application.add_error_handler(error_handler)

# Маршрут Flask для приема вебхуков от Telegram
@app.route(f'/{TOKEN}', methods=['POST'])
async def telegram_webhook():
    """Обрабатывает входящие обновления от Telegram (вебхук)."""
    if request.headers.get('content-type') == 'application/json':
        update_data = request.get_json(force=True)
        update = Update.de_json(update_data, application.bot)
        # Передаем обновление в Telegram Application
        await application.initialize()
        try:
            await application.process_update(update)
        finally:
            await application.shutdown()
        return ('', 204)
    else:
        return ('Unsupported Media Type', 415)

# Необязательный маршрут для проверки работоспособности
@app.route('/', methods=['GET'])
def health_check():
    return "Bot is running!", 200

# Запуск Flask-приложения (для Heroku)
if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host="0.0.0.0", port=port)
