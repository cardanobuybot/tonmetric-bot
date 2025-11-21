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
    ReplyKeyboardRemove
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
    MessageHandler,
    filters
)

BOT_TOKEN = os.getenv("BOT_TOKEN")

# Binance API
BINANCE_TICKER = "https://api.binance.com/api/v3/ticker/price"
BINANCE_KLINES = "https://api.binance.com/api/v3/klines"
SYMBOL = "TONUSDT"

# Store the user's language in memory
user_lang = {}  # user_id -> 'ru' | 'en' | 'uk'


# ------------------ TEXTS ------------------

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


# ------------------ DATA ------------------

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


# ------------------ CHART ------------------

def create_ton_chart():
    times, prices = get_ton_history(72)
    if not times or not prices:
        raise RuntimeError("No chart data")

    current_price = prices[-1]

    plt.style.use("default")

    fig, ax = plt.subplots(figsize=(9, 6), dpi=250)

    # Background
    fig.patch.set_facecolor("#FFFFFF")
    ax.set_facecolor("#F5FAFF")

    # Line + fill
    line_color = "#3B82F6"
    ax.plot(times, prices, linewidth=2.3, color=line_color)
    ax.fill_between(times, prices, min(prices), color=line_color, alpha=0.22)

    # Grid
    ax.grid(True, linewidth=0.3, alpha=0.25)

    # Axis styling
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["bottom"].set_color("#D0D7E2")
    ax.spines["left"].set_color("#D0D7E2")

    ax.tick_params(axis="x", colors="#6B7280", labelsize=8)
    ax.tick_params(axis="y", colors="#6B7280", labelsize=8)

    # Insert price at the bottom of the chart
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


# ----------- SEND PRICE + CHART ------------

async def send_price_and_chart(chat_id, lang, context):
    price = get_ton_price_usd()
    if price is None:
        await context.bot.send_message(chat_id, text_price_error(lang))
        return

    # Send price
    await context.bot.send_message(chat_id, text_price_ok(lang, price))

    # Send chart with referral link
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


# ------------------ HANDLERS ------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_lang[user_id] = "ru"

    keyboard = [
        [
            InlineKeyboardButton("English", callback_data="lang_en"),
            InlineKeyboardButton("Русский", callback_data="lang_ru"),
            InlineKeyboardButton("Українська", callback_data="lang_uk"),
        ]
    ]

    # Send initial message with language options
    await update.message.reply_text(
        "Выберите язык / Select language / Оберіть мову:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    chat_id = query.message.chat_id

    data = query.data

    if data.startswith("lang_"):
        lang = data.split("_", 1)[1]  # en / ru / uk
        user_lang[user_id] = lang

        # Language confirmation
        await query.message.reply_text(text_lang_confirm(lang))

        # Send price and chart after language selection
        await send_price_and_chart(chat_id, lang, context)


# ------------------ FOOTER BUTTONS ------------------

async def footer_buttons_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_user_language(user_id)

    if update.message.text == "Курс":
        await price(update, context)
    elif update.message.text == "График":
        await chart(update, context)
    elif update.message.text == "Уведомления":
        await update.message.reply_text("Уведомления еще не настроены.")
    elif update.message.text == "Купить Stars":
        await update.message.reply_text("Перейдите на сайт TONStars: https://tonstars.io")


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
        except:
            pass


def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN не задан в переменных окружения")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("price", price))
    app.add_handler(CommandHandler("chart", chart))
    app.add_handler(CallbackQueryHandler(button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, footer_buttons_handler))

    print("TONMETRIC BOT started")
    app.run_polling()


if __name__ == "__main__":
    main()
