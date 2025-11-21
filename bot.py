import os
import io
from datetime import datetime

import requests

# headless-backend для сервера
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

BOT_TOKEN = os.getenv("BOT_TOKEN")

# Binance API
BINANCE_TICKER = "https://api.binance.com/api/v3/ticker/price"
BINANCE_KLINES = "https://api.binance.com/api/v3/klines"
SYMBOL = "TONUSDT"

# Конвертация фиата
FX_API = "https://api.exchangerate.host/latest"

# Память в RAM для настроек пользователей
user_settings: dict[int, dict] = {}

LANG_OPTIONS = {
    "en": "English",
    "ru": "Русский",
    "uk": "Українська",
}

FIAT_OPTIONS = {
    "usd": {"label": "$ USD", "symbol": "$"},
    "rub": {"label": "₽ RUB", "symbol": "₽"},
    "eur": {"label": "€ EUR", "symbol": "€"},
    "gbp": {"label": "£ GBP", "symbol": "£"},
    "usdt": {"label": "₮ USDT", "symbol": "₮"},
}


# ----------------- ДАННЫЕ -----------------


def get_ton_price_usd() -> float | None:
    """Текущий курс TON в USDT (≈USD) с Binance."""
    try:
        r = requests.get(BINANCE_TICKER, params={"symbol": SYMBOL}, timeout=8)
        r.raise_for_status()
        data = r.json()
        return float(data["price"])
    except Exception as e:
        print("Price error:", e)
        return None


def get_ton_history(hours: int = 72):
    """История цены TON c Binance (часовые свечи)."""
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
        r.raise_for_status()
        klines = r.json()
        if not isinstance(klines, list):
            print("Binance error:", klines)
            return [], []

        times = []
        prices = []

        for k in klines:
            t = datetime.fromtimestamp(k[0] / 1000)  # open time
            price = float(k[4])  # close
            times.append(t)
            prices.append(price)

        return times, prices
    except Exception as e:
        print("History error:", e)
        return [], []


def convert_price(usd_price: float, fiat: str) -> tuple[float, str]:
    """
    Конвертируем USD → выбранная валюта.
    fiat: 'usd' | 'rub' | 'eur' | 'gbp' | 'usdt'
    """
    # USD и USDT считаем равными по курсу
    if fiat == "usd":
        return usd_price, "$"
    if fiat == "usdt":
        return usd_price, "₮"

    try:
        r = requests.get(
            FX_API,
            params={"base": "USD", "symbols": "EUR,RUB,GBP"},
            timeout=8,
        )
        r.raise_for_status()
        rates = r.json().get("rates", {})

        if fiat == "rub":
            rate = rates.get("RUB")
            symbol = "₽"
        elif fiat == "eur":
            rate = rates.get("EUR")
            symbol = "€"
        elif fiat == "gbp":
            rate = rates.get("GBP")
            symbol = "£"
        else:
            return usd_price, "$"

        if rate is None:
            return usd_price, "$"

        return usd_price * float(rate), symbol
    except Exception as e:
        print("FX error:", e)
        # если не получилось — показываем USD
        return usd_price, "$"


# ----------------- ГРАФИК -----------------


def create_ton_chart() -> bytes:
    """
    Большой синий график:
    - белый фон
    - синяя линия
    - синяя заливка
    """
    times, prices = get_ton_history(72)
    if not times or not prices:
        raise RuntimeError("No chart data")

    current_price = prices[-1]

    plt.style.use("default")
    fig, ax = plt.subplots(figsize=(9, 5), dpi=250)

    fig.patch.set_facecolor("#FFFFFF")
    ax.set_facecolor("#F5FAFF")  # светло-голубой фон

    line_color = "#3B82F6"  # синий
    ax.plot(times, prices, linewidth=2.2, color=line_color)
    ax.fill_between(times, prices, min(prices), color=line_color, alpha=0.22)

    ax.grid(True, linewidth=0.3, alpha=0.25)

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["bottom"].set_color("#D0D7E2")
    ax.spines["left"].set_color("#D0D7E2")

    ax.tick_params(axis="x", colors="#6B7280", labelsize=8)
    ax.tick_params(axis="y", colors="#6B7280", labelsize=8)

    ax.set_title(
        f"TONCOIN:USDT         1 TON = {current_price:.3f} $",
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


# ----------------- ВСПОМОГАТЕЛЬНОЕ -----------------


def get_user_lang(user_id: int) -> str:
    return user_settings.get(user_id, {}).get("lang", "ru")


def get_user_fiat(user_id: int) -> str:
    return user_settings.get(user_id, {}).get("fiat", "usd")


async def send_price_and_chart(chat_id: int, user_id: int, context: ContextTypes.DEFAULT_TYPE):
    usd_price = get_ton_price_usd()
    if usd_price is None:
        await context.bot.send_message(chat_id, "Не могу получить курс TON, попробуй позже 🙈")
        return

    fiat = get_user_fiat(user_id)
    price, symbol = convert_price(usd_price, fiat)

    # подпись валюты
    if fiat == "usd":
        fiat_name = "USD"
    elif fiat == "rub":
        fiat_name = "RUB"
    elif fiat == "eur":
        fiat_name = "EUR"
    elif fiat == "gbp":
        fiat_name = "GBP"
    elif fiat == "usdt":
        fiat_name = "USDT"
    else:
        fiat_name = "USD"

    text = f"1 TON ≈ {price:.4f} {symbol} ({fiat_name})\nИсточник: Binance"

    await context.bot.send_message(chat_id, text)

    try:
        chart_bytes = create_ton_chart()
        await context.bot.send_photo(chat_id, chart_bytes)
    except Exception as e:
        print("Chart error:", e)
        await context.bot.send_message(chat_id, "Не удалось построить график, попробуй позже 🙈")


# ----------------- ХЭНДЛЕРЫ -----------------


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # выбор языка
    keyboard = [
        [
            InlineKeyboardButton("English", callback_data="lang_en"),
            InlineKeyboardButton("Русский", callback_data="lang_ru"),
            InlineKeyboardButton("Українська", callback_data="lang_uk"),
        ]
    ]
    await update.message.reply_text(
        "Выберите язык / Select language:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

    # начальные настройки
    user_settings[user_id] = {"lang": "ru", "fiat": "usd"}


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id
    chat_id = query.message.chat_id

    if data.startswith("lang_"):
        lang_code = data.split("_", 1)[1]
        user_settings.setdefault(user_id, {})["lang"] = lang_code

        # выбор валюты — 2 строки кнопок
        keyboard = [
            [
                InlineKeyboardButton(FIAT_OPTIONS["usd"]["label"], callback_data="fiat_usd"),
                InlineKeyboardButton(FIAT_OPTIONS["rub"]["label"], callback_data="fiat_rub"),
                InlineKeyboardButton(FIAT_OPTIONS["eur"]["label"], callback_data="fiat_eur"),
            ],
            [
                InlineKeyboardButton(FIAT_OPTIONS["gbp"]["label"], callback_data="fiat_gbp"),
                InlineKeyboardButton(FIAT_OPTIONS["usdt"]["label"], callback_data="fiat_usdt"),
            ],
        ]
        await query.message.reply_text(
            "Выберите вашу валюту:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    elif data.startswith("fiat_"):
        fiat_code = data.split("_", 1)[1]
        user_settings.setdefault(user_id, {})["fiat"] = fiat_code

        # после выбора валюты сразу показываем цену + график
        await query.message.reply_text("Загружаю курс и график TON…")
        await send_price_and_chart(chat_id, user_id, context)


async def cmd_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    await send_price_and_chart(chat_id, user_id, context)


async def cmd_chart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    await update.message.reply_text("Строю график TON… 📈")

    try:
        chart_bytes = create_ton_chart()
        await context.bot.send_photo(chat_id, chart_bytes)
    except Exception as e:
        print("Chart error:", e)
        await context.bot.send_message(chat_id, "Не удалось построить график, попробуй позже 🙈")


def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN не задан в переменных окружения")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("price", cmd_price))
    app.add_handler(CommandHandler("chart", cmd_chart))
    app.add_handler(CallbackQueryHandler(handle_callback))

    print("TONMETRIC BOT started")
    app.run_polling()


if __name__ == "__main__":
    main()
