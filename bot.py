from datetime import datetime
import os
import logging
import requestsimport os
import io
from datetime import datetime
import requests
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    CallbackQueryHandler,
    filters
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
BINANCE_TICKER = "https://api.binance.com/api/v3/ticker/price"
BINANCE_KLINES = "https://api.binance.com/api/v3/klines"
SYMBOL = "TONUSDT"
user_lang = {}

def get_user_language(user_id):
    return user_lang.get(user_id, "ru")

def text_lang_confirm(lang):
    if lang == "en":
        return "Language: English ✅\nLoading TON price and chart…"
    elif lang == "uk":
        return "Мова: Українська ✅\nЗавантажую курс та графік TON…"
    else:
        return "Язык: Русский ✅\nЗагружаю курс и график TON…"

def text_price_ok(lang, price):
    return f"1 TON = {price:.3f} $"

def text_price_error(lang):
    return {
        "en": "Can't get TON price now 🙈",
        "uk": "Не можу отримати курс TON 🙈",
        "ru": "Не могу получить курс TON 🙈"
    }.get(lang, "Error")

def text_chart_build(lang):
    return {
        "en": "Building TON chart… 📈",
        "uk": "Будую графік TON… 📈",
        "ru": "Строю график TON… 📈"
    }.get(lang, "…")

def text_chart_error(lang):
    return {
        "en": "Can't build chart 🙈",
        "uk": "Не вдалося побудувати графік 🙈",
        "ru": "Не удалось построить график 🙈"
    }.get(lang, "…")

def get_ton_price_usd():
    try:
        r = requests.get(BINANCE_TICKER, params={"symbol": SYMBOL}, timeout=8)
        return float(r.json()["price"])
    except Exception as e:
        print("Price error:", e)
        return None

def get_ton_history(hours=72):
    try:
        r = requests.get(BINANCE_KLINES, params={"symbol": SYMBOL, "interval": "1h", "limit": hours}, timeout=10)
        klines = r.json()
        if not isinstance(klines, list): return [], []
        times = [datetime.fromtimestamp(k[0] / 1000) for k in klines]
        prices = [float(k[4]) for k in klines]
        return times, prices
    except Exception as e:
        print("History error:", e)
        return [], []

def create_ton_chart():
    times, prices = get_ton_history(72)
    if not times or not prices:
        raise RuntimeError("No chart data")
    current_price = prices[-1]
    fig, ax = plt.subplots(figsize=(9, 6), dpi=250)
    fig.patch.set_facecolor("#FFFFFF")
    ax.set_facecolor("#F5FAFF")
    ax.plot(times, prices, linewidth=2.3, color="#3B82F6")
    ax.fill_between(times, prices, min(prices), color="#3B82F6", alpha=0.22)
    ax.grid(True, linewidth=0.3, alpha=0.25)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["bottom"].set_color("#D0D7E2")
    ax.spines["left"].set_color("#D0D7E2")
    ax.tick_params(axis="x", colors="#6B7280", labelsize=8)
    ax.tick_params(axis="y", colors="#6B7280", labelsize=8)
    fig.text(0.01, -0.04, f"1 TON = {current_price:.3f} $", fontsize=12, color="#111827", ha="left")
    fig.tight_layout(pad=1.5)
    buf = io.BytesIO()
    plt.savefig(buf, format="png", bbox_inches="tight")
    plt.close()
    buf.seek(0)
    return buf.getvalue()

def footer_buttons(lang):
    labels = {
        "en": ["Price", "Chart", "Notifications", "Buy Stars"],
        "ru": ["Курс", "График", "Уведомления", "Купить Stars"],
        "uk": ["Курс", "Графік", "Сповіщення", "Купити Stars"],
    }.get(lang, ["Курс", "График", "Уведомления", "Купить Stars"])
    return ReplyKeyboardMarkup([[KeyboardButton(lbl)] for lbl in labels], resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    keyboard = [[
        InlineKeyboardButton("English", callback_data="lang_en"),
        InlineKeyboardButton("Русский", callback_data="lang_ru"),
        InlineKeyboardButton("Українська", callback_data="lang_uk")
    ]]
    await update.message.reply_text(
        "Выберите язык / Select language / Оберіть мову:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    lang_code = query.data.split("_")[1]
    user_lang[user_id] = lang_code
    await query.message.reply_text(text_lang_confirm(lang_code), reply_markup=footer_buttons(lang_code))
    await send_price_and_chart(query.message.chat_id, lang_code, context)

async def send_price_and_chart(chat_id, lang, context):
    price = get_ton_price_usd()
    if price is None:
        await context.bot.send_message(chat_id, text_price_error(lang))
    else:
        await context.bot.send_message(chat_id, text_price_ok(lang, price))
        try:
            img = create_ton_chart()
            await context.bot.send_photo(
                chat_id,
                img,
                caption="[Binance](https://www.binance.com/referral/earn-together/refer2earn-usdc/claim?hl=en&ref=GRO_28502_1C1WM&utm_source=default)",
                parse_mode="Markdown"
            )
        except Exception as e:
            print("Chart error:", e)
            await context.bot.send_message(chat_id, text_chart_error(lang))

async def footer_buttons_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_user_language(user_id)
    msg = update.message.text.lower()
    if "курс" in msg or "price" in msg:
        await update.message.reply_text(text_price_ok(lang, get_ton_price_usd()))
    elif "график" in msg or "chart" in msg:
        msg_wait = await update.message.reply_text(text_chart_build(lang))
        try:
            img = create_ton_chart()
            await update.message.reply_photo(
                img,
                caption="[Binance](https://www.binance.com/referral/earn-together/refer2earn-usdc/claim?hl=en&ref=GRO_28502_1C1WM&utm_source=default)",
                parse_mode="Markdown"
            )
        except Exception:
            await update.message.reply_text(text_chart_error(lang))
        finally:
            await msg_wait.delete()
    elif "stars" in msg:
        await update.message.reply_text("https://tonstars.io")

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, footer_buttons_handler))
    app.run_polling()

if __name__ == "__main__":
    main()

import json
from io import BytesIO
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"  # Укажите токен вашего бота

# Определяем надписи кнопок для каждого языка
BUTTONS = {
    'ru': ["Курс", "График", "Уведомления", "Купить Toncoins"],
    'en': ["Rate", "Chart", "Notifications", "Buy Toncoins"],
    'uk': ["Курс", "Графік", "Сповіщення", "Купити Toncoins"]
}

# Функция для получения текущего курса Toncoin (USD) через API Binance
def fetch_toncoin_price_usd():
    try:
        resp = requests.get("https://api.binance.com/api/v3/ticker/price", params={"symbol": "TONUSDT"})
        data = resp.json()
        return float(data['price'])
    except Exception as e:
        logging.error(f"Error fetching price: {e}")
        return None

# Функция для получения изображения графика Toncoin (USD) за последние 24 часа
def fetch_toncoin_chart_image():
    try:
        # Запрашиваем данные свечей Toncoin/USDT за последние 24 часа с интервалом 1 час
        resp = requests.get("https://api.binance.com/api/v3/klines", params={"symbol": "TONUSDT", "interval": "1h", "limit": 24})
        data = resp.json()
        closes = [float(item[4]) for item in data]  # список цен закрытия
        labels = list(range(1, len(closes) + 1))
        # Формируем конфигурацию графика для QuickChart
        chart_config = {
            "type": "line",
            "data": {
                "labels": labels,
                "datasets": [{
                    "label": "TON/USD",
                    "data": closes,
                    "fill": False,
                    "borderColor": "#3366CC",
                    "borderWidth": 2
                }]
            },
            "options": {
                "elements": {
                    "point": {"radius": 0}
                },
                "layout": {
                    "padding": 5
                },
                "scales": {
                    "x": {"display": False},
                    "y": {"ticks": {"callback": "(value) => '$' + value.toFixed(3)"}}
                }
            }
        }
        # Получаем изображение графика через API QuickChart
        qc_url = "https://quickchart.io/chart"
        qc_response = requests.get(qc_url, params={"c": json.dumps(chart_config)})
        if qc_response.status_code == 200:
            return qc_response.content  # возвращаем байты изображения
        else:
            return None
    except Exception as e:
        logging.error(f"Error fetching chart: {e}")
        return None

# Обработчик команды /start – предлагает выбрать язык и выводит клавиатуру языков
def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[
        InlineKeyboardButton("English", callback_data='en'),
        InlineKeyboardButton("Русский", callback_data='ru'),
        InlineKeyboardButton("Українська", callback_data='uk')
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text(
        "Select language / Выберите язык / Оберіть мову:",
        reply_markup=reply_markup
    )

# Обработчик выбора языка (CallbackQuery) – устанавливает язык и отображает основное меню с кнопками
def language_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    lang = query.data  # 'ru', 'en' или 'uk'
    context.user_data['lang'] = lang  # сохраняем выбранный язык для пользователя
    # Формируем сообщение с подтверждением выбора языка
    if lang == 'ru':
        confirmation_text = "Язык установлен: Русский ✓\nЗагружаю курс и график TON..."
    elif lang == 'en':
        confirmation_text = "Language set: English ✓\nLoading TON rate and chart..."
    elif lang == 'uk':
        confirmation_text = "Мову встановлено: Українська ✓\nЗавантажую курс і графік TON..."
    else:
        confirmation_text = "Language set.\nLoading TON data..."
    # Редактируем первоначальное сообщение /start, чтобы отобразить выбор языка
    query.answer()
    query.edit_message_text(confirmation_text)
    # Отправляем сообщение с текущим курсом TON и отображаем основную клавиатуру с кнопками
    buttons = [
        [BUTTONS[lang][0], BUTTONS[lang][1]],
        [BUTTONS[lang][2], BUTTONS[lang][3]]
    ]
    reply_kb = ReplyKeyboardMarkup(buttons, resize_keyboard=True)
    # Получаем текущий курс Toncoin и формируем текст курса
    price = fetch_toncoin_price_usd()
    price_text = f"1 TON = {price:.3f} $ (Binance)" if price is not None else "TON price not available"
    # Добавляем время обновления
    timestamp = datetime.now().strftime("%H:%M %d.%m.%Y")
    if lang == 'ru':
        price_text += f"\nОбновлено: {timestamp}"
    elif lang == 'en':
        price_text += f"\nUpdated: {timestamp}"
    elif lang == 'uk':
        price_text += f"\nОновлено: {timestamp}"
    # Отправляем сообщение с курсом Toncoin и основной клавиатурой
    context.bot.send_message(chat_id=query.message.chat_id, text=price_text, reply_markup=reply_kb)
    # Получаем изображение графика и отправляем его (либо сообщение об ошибке, если не удалось)
    chart_image = fetch_toncoin_chart_image()
    if chart_image:
        bio = BytesIO(chart_image)
        bio.name = "chart.png"
        context.bot.send_photo(chat_id=query.message.chat_id, photo=bio)
    else:
        if lang == 'ru':
            context.bot.send_message(chat_id=query.message.chat_id, text="Не удалось построить график, попробуй позже.")
        elif lang == 'en':
            context.bot.send_message(chat_id=query.message.chat_id, text="Failed to load chart, please try again later.")
        elif lang == 'uk':
            context.bot.send_message(chat_id=query.message.chat_id, text="Не вдалося побудувати графік, спробуйте пізніше.")

# Обработчик нажатий на кнопки основной клавиатуры (Курс, График, Уведомления, Купить Toncoins)
def footer_buttons_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    # Определяем текущий язык пользователя (если не установлен, используем язык Telegram или по умолчанию English)
    lang = context.user_data.get('lang')
    if not lang:
        code = update.effective_user.language_code if update.effective_user else 'en'
        lang = code if code in ('ru', 'en', 'uk') else 'en'
        context.user_data['lang'] = lang
    # Обработка выбора пользователя в зависимости от нажатой кнопки
    if user_text in ["Курс", "Rate"]:
        # Отправляем текущий курс Toncoin
        price = fetch_toncoin_price_usd()
        reply_text = f"1 TON = {price:.3f} $ (Binance)" if price is not None else "TON price not available"
        timestamp = datetime.now().strftime("%H:%M %d.%m.%Y")
        if lang == 'ru':
            reply_text += f"\nОбновлено: {timestamp}"
        elif lang == 'en':
            reply_text += f"\nUpdated: {timestamp}"
        elif lang == 'uk':
            reply_text += f"\nОновлено: {timestamp}"
        update.message.reply_text(reply_text)
    elif user_text in ["График", "Chart", "Графік"]:
        # Отправляем график цены Toncoin (или сообщение об ошибке)
        chart_image = fetch_toncoin_chart_image()
        if chart_image:
            bio = BytesIO(chart_image)
            bio.name = "chart.png"
            update.message.reply_photo(photo=bio)
        else:
            if lang == 'ru':
                update.message.reply_text("Не удалось построить график, попробуй позже.")
            elif lang == 'en':
                update.message.reply_text("Failed to load chart, please try again later.")
            elif lang == 'uk':
                update.message.reply_text("Не вдалося побудувати графік, спробуйте пізніше.")
    elif user_text in ["Уведомления", "Notifications", "Сповіщення"]:
        # Переключаем состояние уведомлений для пользователя (в простом виде без сохранения между запусками)
        subscribed = context.user_data.get('notifications', False)
        context.user_data['notifications'] = not subscribed
        if not subscribed:
            if lang == 'ru':
                update.message.reply_text("Уведомления включены.")
            elif lang == 'en':
                update.message.reply_text("Notifications are now enabled.")
            elif lang == 'uk':
                update.message.reply_text("Сповіщення увімкнено.")
        else:
            if lang == 'ru':
                update.message.reply_text("Уведомления отключены.")
            elif lang == 'en':
                update.message.reply_text("Notifications are now disabled.")
            elif lang == 'uk':
                update.message.reply_text("Сповіщення вимкнено.")
    elif user_text in ["Купить Toncoins", "Buy Toncoins", "Купити Toncoins"]:
        # Отправляем информацию о покупке Toncoin (список бирж/сервисов и реферальная ссылка)
        if lang == 'ru':
            text = ("Купить Toncoin прямо сейчас вы можете в: Crypto Bot, ByBit, OKX, EXMO, Gate.io, MEXC, KuCoin.\n"
                    "Больше о TON в @givemetonru")
        elif lang == 'en':
            text = ("You can buy Toncoin right now on: Crypto Bot, ByBit, OKX, EXMO, Gate.io, MEXC, KuCoin.\n"
                    "Learn more about TON at @givemetonru")
        elif lang == 'uk':
            text = ("Придбати Toncoin прямо зараз ви можете на: Crypto Bot, ByBit, OKX, EXMO, Gate.io, MEXC, KuCoin.\n"
                    "Більше про TON в @givemetonru")
        update.message.reply_text(text)

# Обработчики команд /price и /chart (на случай, если пользователь вводит команды вручную)
def cmd_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.setdefault('lang', 'ru')
    footer_buttons_handler(update, context)

def cmd_chart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.setdefault('lang', 'ru')
    footer_buttons_handler(update, context)

# Запуск приложения Telegram Bot
def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("price", cmd_price))
    app.add_handler(CommandHandler("chart", cmd_chart))
    app.add_handler(CallbackQueryHandler(language_select))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, footer_buttons_handler))
    app.run_polling()

if __name__ == "__main__":
    main()
