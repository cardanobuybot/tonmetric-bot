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

# Язык пользователя: user_id -> 'ru' | 'en' | 'uk'
user_lang: dict[int, str] = {}


# ------------------ ТЕКСТЫ ------------------


def get_user_language(user_id: int) -> str:
    return user_lang.get(user_id, "ru")


def text_lang_confirm(lang: str) -> str:
    if lang == "en":
        return "Language: English ✅\nLoading TON price and chart…"
    elif lang == "uk":
        return "Мова: Українська ✅\nЗавантажую курс та графік TON…"
    else:
        return "Язык: Русский ✅\nЗагружаю курс и график TON…"


def text_price_ok(lang: str, price: float) -> str:
    if lang == "en":
        return f"1 TON = {price:.3f} $"
    elif lang == "uk":
        return f"1 TON = {price:.3f} $"
    else:
        return f"1 TON = {price:.3f} $"


def text_price_error(lang: str) -> str:
    if lang == "en":
        return "Can't get TON price now 🙈"
    elif lang == "uk":
        return "Не можу отримати курс TON 🙈"
    else:
        return "Не могу получить курс TON 🙈"


def text_chart_build(lang: str) -> str:
    if lang == "en":
        return "Building TON chart… 📈"
    elif lang == "uk":
        return "Будую графік TON… 📈"
    else:
        return "Строю график TON… 📈"


def text_chart_error(lang: str) -> str:
    if lang == "en":
        return "Can't build chart 🙈"
    elif lang == "uk":
        return "Не вдалося побудувати графік 🙈"
    else:
        return "Не удалось построить график 🙈"


def text_notify_info(lang: str) -> str:
    if lang == "en":
        return (
            "Notifications\n\n"
            "Soon I will be able to notify you when TON price changes "
            "by more than 10% from the current value."
        )
    elif lang == "uk":
        return (
            "Сповіщення\n\n"
            "Скоро бот зможе повідомляти, коли ціна TON зміниться "
            "більше ніж на 10% від поточної."
        )
    else:
        return (
            "Уведомления\n\n"
            "Скоро бот сможет уведомлять, когда цена TON изменится "
            "более чем на 10% от текущей."
        )


def text_buy_stars(lang: str) -> str:
    url = "https://tonstars.io"
    if lang == "en":
        return f"Open TON Stars: {url}"
    elif lang == "uk":
        return f"Відкрийте TON Stars: {url}"
    else:
        return f"Откройте TON Stars: {url}"


def text_wallet(lang: str) -> str:
    url = "http://t.me/send?start=r-71wfg"
    if lang == "en":
        return f"Open wallet: {url}"
    elif lang == "uk":
        return f"Відкрити гаманець: {url}"
    else:
        return f"Открыть кошелёк: {url}"


# Подписи для нижних кнопок
FOOTER_BUTTONS = {
    "ru": {
        "rate": "Курс",
        "chart": "График",
        "notify": "Уведомления",
        "buy": "Купить Stars ⭐",
        "wallet": "Кошелёк",
    },
    "en": {
        "rate": "Rate",
        "chart": "Chart",
        "notify": "Notifications",
        "buy": "Buy Stars ⭐",
        "wallet": "Wallet",
    },
    "uk": {
        "rate": "Курс",
        "chart": "Графік",
        "notify": "Сповіщення",
        "buy": "Купити Stars ⭐",
        "wallet": "Гаманець",
    },
}


# ------------------ ДАННЫЕ ------------------


def get_ton_price_usd() -> float | None:
    try:
        r = requests.get(BINANCE_TICKER, params={"symbol": SYMBOL}, timeout=8)
        data = r.json()
        return float(data["price"])
    except Exception as e:
        print("Price error:", e)
        return None


def get_ton_history(hours: int = 72):
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

        times = [datetime.fromtimestamp(k[0] / 1000) for k in klines]
        prices = [float(k[4]) for k in klines]  # close

        return times, prices

    except Exception as e:
        print("History error:", e)
        return [], []


# ------------------ ГРАФИК ------------------


def create_ton_chart() -> bytes:
    times, prices = get_ton_history(72)
    if not times or not prices:
        raise RuntimeError("No chart data")

    current_price = prices[-1]

    plt.style.use("default")
    fig, ax = plt.subplots(figsize=(9, 6), dpi=250)

    fig.patch.set_facecolor("#FFFFFF")
    ax.set_facecolor("#F5FAFF")

    line_color = "#3B82F6"
    ax.plot(times, prices, linewidth=2.3, color=line_color)
    ax.fill_between(times, prices, min(prices), color=line_color, alpha=0.22)

    ax.grid(True, linewidth=0.3, alpha=0.25)

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["bottom"].set_color("#D0D7E2")
    ax.spines["left"].set_color("#D0D7E2")

    ax.tick_params(axis="x", colors="#6B7280", labelsize=8)
    ax.tick_params(axis="y", colors="#6B7280", labelsize=8)

    # Цена снизу графика
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


async def send_price_and_chart(chat_id: int, lang: str, context: ContextTypes.DEFAULT_TYPE):
    price = get_ton_price_usd()
    if price is None:
        await context.bot.send_message(chat_id, text_price_error(lang))
        return

    await context.bot.send_message(chat_id, text_price_ok(lang, price))

    try:
        img = create_ton_chart()
        await context.bot.send_photo(
            chat_id,
            img,
            caption="[Binance]"
                     "(https://www.binance.com/referral/earn-together/"
                     "refer2earn-usdc/claim?hl=en&ref=GRO_28502_1C1WM&utm_source=default)",
            parse_mode="Markdown",
        )
    except Exception as e:
        print("Chart error:", e)
        await context.bot.send_message(chat_id, text_chart_error(lang))


# ------------------ КНОПКИ ------------------


def footer_buttons(lang: str) -> ReplyKeyboardMarkup:
    bt = FOOTER_BUTTONS.get(lang, FOOTER_BUTTONS["ru"])
    keyboard = [
        [KeyboardButton(bt["rate"])],
        [KeyboardButton(bt["chart"])],
        [KeyboardButton(bt["notify"])],
        [KeyboardButton(bt["buy"])],
        [KeyboardButton(bt["wallet"])],
    ]
    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
        one_time_keyboard=False,
    )


# ------------------ ХЕНДЛЕРЫ ------------------


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    # по умолчанию русский, пока не выбрал язык
    user_lang[user_id] = "ru"

    keyboard = [
        [
            InlineKeyboardButton("English", callback_data="lang_en"),
            InlineKeyboardButton("Русский", callback_data="lang_ru"),
            InlineKeyboardButton("Українська", callback_data="lang_uk"),
        ]
    ]

    await update.message.reply_text(
        "Выберите язык / Select language / Оберіть мову:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def lang_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    chat_id = query.message.chat_id
    data = query.data

    if data.startswith("lang_"):
        lang = data.split("_", 1)[1]  # en / ru / uk
        user_lang[user_id] = lang

        # подтверждение языка + сразу прикручиваем нижние кнопки
        await query.message.reply_text(
            text_lang_confirm(lang),
            reply_markup=footer_buttons(lang),
        )

        # курс + график
        await send_price_and_chart(chat_id, lang, context)


async def footer_buttons_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_user_language(user_id)
    bt = FOOTER_BUTTONS.get(lang, FOOTER_BUTTONS["ru"])

    text = update.message.text

    # Курс
    if text == bt["rate"]:
        price = get_ton_price_usd()
        if price:
            await update.message.reply_text(text_price_ok(lang, price))
        else:
            await update.message.reply_text(text_price_error(lang))

    # График
    elif text == bt["chart"]:
        info = await update.message.reply_text(text_chart_build(lang))
        try:
            img = create_ton_chart()
            await update.message.reply_photo(
                img,
                caption="[Binance]"
                         "(https://www.binance.com/referral/earn-together/"
                         "refer2earn-usdc/claim?hl=en&ref=GRO_28502_1C1WM&utm_source=default)",
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

    # Уведомления
    elif text == bt["notify"]:
        await update.message.reply_text(text_notify_info(lang))

    # Купить Stars
    elif text == bt["buy"]:
        await update.message.reply_text(
            text_buy_stars(lang),
            disable_web_page_preview=False,
        )

    # Кошелёк
    elif text == bt["wallet"]:
        await update.message.reply_text(
            text_wallet(lang),
            disable_web_page_preview=False,
        )


# Команды /price и /chart остаются, чтобы работали слеши


async def cmd_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_user_language(user_id)

    price = get_ton_price_usd()
    if price:
        await update.message.reply_text(text_price_ok(lang, price))
    else:
        await update.message.reply_text(text_price_error(lang))


async def cmd_chart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_user_language(user_id)

    info = await update.message.reply_text(text_chart_build(lang))
    try:
        img = create_ton_chart()
        await update.message.reply_photo(
            img,
            caption="[Binance]"
                     "(https://www.binance.com/referral/earn-together/"
                     "refer2earn-usdc/claim?hl=en&ref=GRO_28502_1C1WM&utm_source=default)",
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

    # команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("price", cmd_price))
    app.add_handler(CommandHandler("chart", cmd_chart))

    # выбор языка
    app.add_handler(CallbackQueryHandler(lang_button))

    # обработка текстовых кнопок
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            footer_buttons_handler,
        )
    )

    app.run_polling()


if __name__ == "__main__":
    main()
