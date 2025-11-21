import os
import io
from datetime import datetime

import requests

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler

BOT_TOKEN = os.getenv("BOT_TOKEN")

# Binance API
BINANCE_TICKER = "https://api.binance.com/api/v3/ticker/price"
BINANCE_KLINES = "https://api.binance.com/api/v3/klines"
SYMBOL = "TONUSDT"

# Память языков пользователей (пока в оперативке)
user_lang = {}  # user_id -> 'ru' | 'en' | 'uk'


# ---------- ВСПОМОГАТЕЛЬНЫЕ ТЕКСТЫ ----------

def get_user_lang(user_id):
    return user_lang.get(user_id, "ru")


def text_after_lang(lang_code):
    if lang_code == "en":
        return (
            "Language: English ✅\n\n"
            "Commands:\n"
            "/price – TON price\n"
            "/chart – TON price chart"
        )
    elif lang_code == "uk":
        return (
            "Мова: Українська ✅\n\n"
            "Команди:\n"
            "/price – курс TON\n"
            "/chart – графік TON"
        )
    else:  # ru
        return (
            "Язык: Русский ✅\n\n"
            "Команды:\n"
            "/price — курс TON\n"
            "/chart — график TON"
        )


def text_price_ok(lang_code, price):
    if lang_code == "en":
        return f"1 TON = {price:.3f} $ (Binance)"
    elif lang_code == "uk":
        return f"1 TON = {price:.3f} $ (Binance)"
    else:
        return f"1 TON = {price:.3f} $ (Binance)"


def text_price_error(lang_code):
    if lang_code == "en":
        return "Can't get TON price now, try again later 🙈"
    elif lang_code == "uk":
        return "Не можу отримати курс TON, спробуйте пізніше 🙈"
    else:
        return "Не могу получить курс TON, попробуйте позже 🙈"


def text_chart_building(lang_code):
    if lang_code == "en":
        return "Building TON chart… 📈"
    elif lang_code == "uk":
        return "Будую графік TON… 📈"
    else:
        return "Строю график TON… 📈"


def text_chart_error(lang_code):
    if lang_code == "en":
        return "Failed to build chart, try again later 🙈"
    elif lang_code == "uk":
        return "Не вдалося побудувати графік, спробуйте пізніше 🙈"
    else:
        return "Не удалось построить график, попробуйте позже 🙈"


# ---------- ДАННЫЕ ----------

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
            print("Binance error:", klines)
            return [], []

        times = []
        prices = []

        for k in klines:
            t = datetime.fromtimestamp(k[0] / 1000)
            price = float(k[4])  # close
            times.append(t)
            prices.append(price)

        return times, prices

    except Exception as e:
        print("History error:", e)
        return [], []


# ---------- ГРАФИК ----------

def create_ton_chart():
    times, prices = get_ton_history(72)
    if not times or not prices:
        raise RuntimeError("No chart data")

    current_price = prices[-1]

    plt.style.use("default")

    # большой синий график
    fig, ax = plt.subplots(figsize=(9, 6), dpi=250)

    # фон
    fig.patch.set_facecolor("#FFFFFF")
    ax.set_facecolor("#F5FAFF")  # светло-голубой фон

    # линия + заливка
    line_color = "#3B82F6"  # синий
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

    # заголовок
    ax.set_title(
        "TONCOIN:USDT     1 TON = {:.3f} $".format(current_price),
        color="#111827",
        fontsize=12,
        loc="left",
        pad=10,
    )

    fig.tight_layout(pad=1.5)

    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    plt.close()
    buf.seek(0)
    return buf.getvalue()


# ---------- ХЕНДЛЕРЫ ----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # клавиатура выбора языка
    keyboard = [
        [
            InlineKeyboardButton("English", callback_data="lang_en"),
            InlineKeyboardButton("Русский", callback_data="lang_ru"),
            InlineKeyboardButton("Українська", callback_data="lang_uk"),
        ]
    ]

    user_lang[user_id] = "ru"  # по умолчанию русский

    await update.message.reply_text(
        "Выберите язык / Select language / Оберіть мову:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    user_id = query.from_user.id

    if data.startswith("lang_"):
        lang_code = data.split("_", 1)[1]  # en / ru / uk
        user_lang[user_id] = lang_code

        msg = text_after_lang(lang_code)
        await query.message.reply_text(msg)


async def price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang_code = get_user_lang(user_id)

    p = get_ton_price_usd()
    if p:
        await update.message.reply_text(text_price_ok(lang_code, p))
    else:
        await update.message.reply_text(text_price_error(lang_code))


async def chart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang_code = get_user_lang(user_id)

    info = await update.message.reply_text(text_chart_building(lang_code))
    try:
        img = create_ton_chart()
        await update.message.reply_photo(img)
    except Exception as e:
        print("Chart error:", e)
        await update.message.reply_text(text_chart_error(lang_code))
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
    app.add_handler(CallbackQueryHandler(button))

    print("TONMETRIC BOT started")
    app.run_polling()


if __name__ == "__main__":
    main()
