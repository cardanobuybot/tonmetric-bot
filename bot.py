import os
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
    KeyboardButton,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

BOT_TOKEN = os.getenv("BOT_TOKEN")

# Binance API
BINANCE_TICKER = "https://api.binance.com/api/v3/ticker/price"
BINANCE_KLINES = "https://api.binance.com/api/v3/klines"
SYMBOL = "TONUSDT"

# Храним язык пользователя в памяти
user_lang = {}  # user_id -> 'ru' | 'en' | 'uk'

# Тексты кнопок для разных языков
BUTTON_TEXTS = {
    "ru": {
        "price": "Курс",
        "chart": "График",
        "notify": "Уведомления",
        "buy": "Купить Toncoins",
    },
    "en": {
        "price": "Price",
        "chart": "Chart",
        "notify": "Notifications",
        "buy": "Buy Toncoins",
    },
    "uk": {
        "price": "Курс",
        "chart": "Графік",
        "notify": "Сповіщення",
        "buy": "Купити Toncoins",
    },
}


# ------------------ ТЕКСТЫ ------------------

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
    if lang == "en":
        return f"1 TON = {price:.3f} $"
    elif lang == "uk":
        return f"1 TON = {price:.3f} $"
    else:
        return f"1 TON = {price:.3f} $"


def text_price_error(lang):
    if lang == "en":
        return "Can't get TON price now 🙈"
    elif lang == "uk":
        return "Не можу отримати курс TON 🙈"
    else:
        return "Не могу получить курс TON 🙈"


def text_chart_build(lang):
    if lang == "en":
        return "Building TON chart… 📈"
    elif lang == "uk":
        return "Будую графік TON… 📈"
    else:
        return "Строю график TON… 📈"


def text_chart_error(lang):
    if lang == "en":
        return "Can't build chart 🙈"
    elif lang == "uk":
        return "Не вдалося побудувати графік 🙈"
    else:
        return "Не удалось построить график 🙈"


# ------------------ ДАННЫЕ ------------------

def get_ton_price_usd():
    try:
        r = requests.get(BINANCE_TICKER, params={"symbol": SYMBOL}, timeout=8)
        data = r.json()
        return float(data["price"])
    except Exception as e:
        print("Price error:", e)
        return None


def get_ton_history(hours=72):
    try:
        r = requests.get(
            BINANCE_KLINES,
            params={
                "symbol": SYMBOL,
                "interval": "1h",
                "limit": hours,
            },
            timeout=10,
        )

        klines = r.json()
        if not isinstance(klines, list):
            return [], []

        times = [datetime.fromtimestamp(k[0] / 1000) for k in klines]
        prices = [float(k[4]) for k in klines]

        return times, prices

    except Exception as e:
        print("History error:", e)
        return [], []


# ------------------ ГРАФИК ------------------

def create_ton_chart():
    times, prices = get_ton_history(72)
    if not times or not prices:
        raise RuntimeError("No chart data")

    current_price = prices[-1]

    plt.style.use("default")

    fig, ax = plt.subplots(figsize=(9, 6), dpi=250)

    # фон
    fig.patch.set_facecolor("#FFFFFF")
    ax.set_facecolor("#F5FAFF")

    # линия + заливка
    line_color = "#3B82F6"
    ax.plot(times, prices, linewidth=2.3, color=line_color)
    ax.fill_between(times, prices, min(prices), color=line_color, alpha=0.22)

    # сетка
    ax.grid(True, linewidth=0.3, alpha=0.25)

    # оформление осей
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["bottom"].set_color("#D0D7E2")
    ax.spines["left"].set_color("#D0D7E2")

    ax.tick_params(axis="x", colors="#6B7280", labelsize=8)
    ax.tick_params(axis="y", colors="#6B7280", labelsize=8)

    # 🔥 вставляем цену СНИЗУ графика
    fig.text(
        0.01,
        -0.04,
        f"1 TON = {current_price:.3f} $",
        fontsize=12,
        color="#111827",
        ha="left",
    )

    fig.tight_layout(pad=1.5)

    buf = io.BytesIO()
    plt.savefig(buf, format="png", bbox_inches="tight")
    plt.close()
    buf.seek(0)
    return buf.getvalue()


# ----------- ОТПРАВКА ЦЕНЫ + ГРАФИКА ------------

async def send_price_and_chart(chat_id, lang, context: ContextTypes.DEFAULT_TYPE):
    price = get_ton_price_usd()
    if price is None:
        await context.bot.send_message(chat_id, text_price_error(lang))
        return

    # отправляем цену
    await context.bot.send_message(chat_id, text_price_ok(lang, price))

    # отправляем график с реф-ссылкой
    try:
        img = create_ton_chart()
        await context.bot.send_photo(
            chat_id,
            img,
            caption="[Binance](https://www.binance.com/referral/earn-together/refer2earn-usdc/claim?hl=en&ref=GRO_28502_1C1WM&utm_source=default)",
            parse_mode="Markdown",
        )
    except Exception as e:
        print("Chart error:", e)
        await context.bot.send_message(chat_id, text_chart_error(lang))


# ------------------ КНОПКИ ------------------

def footer_buttons(lang: str):
    lang = lang if lang in BUTTON_TEXTS else "ru"
    bt = BUTTON_TEXTS[lang]
    keyboard = [
        [KeyboardButton(bt["price"])],
        [KeyboardButton(bt["chart"])],
        [KeyboardButton(bt["notify"])],
        [KeyboardButton(bt["buy"])],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)


def language_inline_keyboard():
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Русский", callback_data="lang_ru"),
                InlineKeyboardButton("English", callback_data="lang_en"),
                InlineKeyboardButton("Українська", callback_data="lang_uk"),
            ]
        ]
    )


# ------------------ ХЕНДЛЕРЫ ------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_lang[user_id] = "ru"

    # Сначала показываем фиксированные кнопки (по-умолчанию русский)
    await update.message.reply_text(
        "Привет! Я TONMETRIC BOT. Выберите действие:",
        reply_markup=footer_buttons("ru"),
    )

    # И отдельным сообщением — выбор языка
    await update.message.reply_text(
        "Сменить язык / Change language / Змінити мову:",
        reply_markup=language_inline_keyboard(),
    )


async def language_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    data = query.data  # lang_ru / lang_en / lang_uk
    lang = data.split("_", 1)[1]  # ru | en | uk

    user_lang[user_id] = lang

    # Подтверждение и обновлённые фиксированные кнопки
    await query.message.reply_text(
        text_lang_confirm(lang),
        reply_markup=footer_buttons(lang),
    )


async def buttons_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка нажатий по фиксированным (reply) кнопкам внизу."""
    user_id = update.effective_user.id
    lang = get_user_language(user_id)
    text = (update.message.text or "").strip()

    bt = BUTTON_TEXTS.get(lang, BUTTON_TEXTS["ru"])

    if text == bt["price"]:
        # Кнопка «Курс»
        p = get_ton_price_usd()
        if p:
            await update.message.reply_text(text_price_ok(lang, p))
        else:
            await update.message.reply_text(text_price_error(lang))

    elif text == bt["chart"]:
        # Кнопка «График»
        info = await update.message.reply_text(text_chart_build(lang))
        try:
            img = create_ton_chart()
            await update.message.reply_photo(
                img,
                caption="[Binance](https://www.binance.com/referral/earn-together/refer2earn-usdc/claim?hl=en&ref=GRO_28502_1C1WM&utm_source=default)",
                parse_mode="Markdown",
            )
        except Exception as e:
            print("Chart error:", e)
            await update.message.reply_text(text_chart_error(lang))
        finally:
            try:
                await info.delete()
            except Exception:
                pass

    elif text == bt["notify"]:
        # Кнопка «Уведомления» (заглушка)
        if lang == "en":
            await update.message.reply_text("Notifications settings will be available soon.")
        elif lang == "uk":
            await update.message.reply_text("Налаштування сповіщень буде доступно пізніше.")
        else:
            await update.message.reply_text("Настройки уведомлений будут доступны позже.")

    elif text == bt["buy"]:
        # Кнопка «Купить Toncoins»
        await update.message.reply_text("Покупка Toncoins")


async def price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_user_language(user_id)

    p = get_ton_price_usd()
    if p:
        await update.message.reply_text(text_price_ok(lang, p))
    else:
        await update.message.reply_text(text_price_error(lang))


async def chart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_user_language(user_id)

    info = await update.message.reply_text(text_chart_build(lang))

    try:
        img = create_ton_chart()
        await update.message.reply_photo(
            img,
            caption="[Binance](https://www.binance.com/referral/earn-together/refer2earn-usdc/claim?hl=en&ref=GRO_28502_1C1WM&utm_source=default)",
            parse_mode="Markdown",
        )
    except Exception as e:
        print("Chart error:", e)
        await update.message.reply_text(text_chart_error(lang))
    finally:
        try:
            await info.delete()
        except Exception:
            pass


def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN не задан в переменных окружения")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("price", price))
    app.add_handler(CommandHandler("chart", chart))

    # callback_query только для смены языка
    app.add_handler(CallbackQueryHandler(language_callback))

    # ВСЕ текстовые сообщения (кроме команд) – это нажатия по фикс-кнопкам
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, buttons_handler))

    app.run_polling()


if __name__ == "__main__":
    main()
