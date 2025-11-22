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

TONSTARS_URL = "https://tonstars.io"

# Храним настройки пользователей в памяти
user_lang: dict[int, str] = {}         # user_id -> 'ru' | 'en' | 'uk'
user_subscribed: set[int] = set()      # user_ids, подписанные на уведомления


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


def text_tonstars(lang: str) -> str:
    if lang == "en":
        return f"Open TON Stars: {TONSTARS_URL}"
    elif lang == "uk":
        return f"Відкрийте TON Stars: {TONSTARS_URL}"
    else:
        return f"Откройте TON Stars: {TONSTARS_URL}"


def text_subscribe_info(lang: str) -> str:
    if lang == "en":
        return (
            "We will notify you if Toncoin price changes more than 10% "
            "(up or down) from the current price.\n\n"
            "Press “Unsubscribe” if you no longer want to receive such alerts."
        )
    elif lang == "uk":
        return (
            "Ми повідомимо про зміну ціни Toncoin більш ніж на 10% "
            "(вгору або вниз) від поточної ціни.\n\n"
            "Натиснувши кнопку «Відписатися», ви більше не будете отримувати такі сповіщення."
        )
    else:
        return (
            "Уведомим об изменении цены Toncoin более чем на 10% "
            "(вверх или вниз) от текущей цены.\n\n"
            "Нажав кнопку «Отписаться» вы больше не будете получать подобные уведомления."
        )


def text_unsubscribed(lang: str) -> str:
    if lang == "en":
        return "You have unsubscribed from TON price alerts."
    elif lang == "uk":
        return "Ви відписалися від сповіщень про ціну TON."
    else:
        return "Вы отписались от уведомлений о цене TON."


def text_already_subscribed(lang: str) -> str:
    if lang == "en":
        return "You are already subscribed to TON price alerts."
    elif lang == "uk":
        return "Ви вже підписані на сповіщення про ціну TON."
    else:
        return "Вы уже подписаны на уведомления о цене TON."


def text_unsubscribe_button(lang: str) -> str:
    if lang == "en":
        return "Unsubscribe"
    elif lang == "uk":
        return "Відписатися"
    else:
        return "Отписаться"


# подписи для нижних кнопок
FOOTER_BUTTONS = {
    "ru": {
        "rate": "Курс",
        "chart": "График",
        "notify": "Уведомления",
        "buy": "Купить Stars ⭐",
    },
    "en": {
        "rate": "Rate",
        "chart": "Chart",
        "notify": "Notifications",
        "buy": "Buy Stars ⭐",
    },
    "uk": {
        "rate": "Курс",
        "chart": "Графік",
        "notify": "Сповіщення",
        "buy": "Купити Stars ⭐",
    },
}


def footer_buttons(lang: str) -> ReplyKeyboardMarkup:
    bt = FOOTER_BUTTONS.get(lang, FOOTER_BUTTONS["ru"])
    keyboard = [
        [KeyboardButton(bt["rate"])],
        [KeyboardButton(bt["chart"])],
        [KeyboardButton(bt["notify"])],
        [KeyboardButton(bt["buy"])],
    ]
    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
        one_time_keyboard=False,
    )


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
            return [], []

        times = [datetime.fromtimestamp(k[0] / 1000) for k in klines]
        prices = [float(k[4]) for k in klines]

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
            caption="[Binance](https://www.binance.com/referral/earn-together/"
                     "refer2earn-usdc/claim?hl=en&ref=GRO_28502_1C1WM&utm_source=default)",
            parse_mode="Markdown",
        )
    except Exception as e:
        print("Chart error:", e)
        await context.bot.send_message(chat_id, text_chart_error(lang))


# ------------------ ХЕНДЛЕРЫ ------------------

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

    await update.message.reply_text(
        "Выберите язык / Select language / Оберіть мову:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    chat_id = query.message.chat_id
    data = query.data

    # выбор языка
    if data.startswith("lang_"):
        lang = data.split("_", 1)[1]  # en / ru / uk
        user_lang[user_id] = lang

        await query.message.reply_text(
            text_lang_confirm(lang),
            reply_markup=footer_buttons(lang),
        )

        await send_price_and_chart(chat_id, lang, context)

    # отписка от уведомлений
    elif data == "unsubscribe":
        lang = get_user_language(user_id)
        if user_id in user_subscribed:
            user_subscribed.discard(user_id)
        await query.message.reply_text(text_unsubscribed(lang))


async def footer_buttons_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_user_language(user_id)
    bt = FOOTER_BUTTONS.get(lang, FOOTER_BUTTONS["ru"])

    text = (update.message.text or "").strip()

    # Курс
    if text == bt["rate"]:
        p = get_ton_price_usd()
        if p:
            await update.message.reply_text(text_price_ok(lang, p))
        else:
            await update.message.reply_text(text_price_error(lang))

    # График
    elif text == bt["chart"]:
        info = await update.message.reply_text(text_chart_build(lang))
        try:
            img = create_ton_chart()
            await update.message.reply_photo(
                img,
                caption="[Binance](https://www.binance.com/referral/earn-together/"
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

    # Уведомления (подписка)
    elif text == bt["notify"]:
        # отмечаем пользователя как подписанного
        first_time = user_id not in user_subscribed
        user_subscribed.add(user_id)

        if not first_time:
            await update.message.reply_text(text_already_subscribed(lang))

        keyboard = [[InlineKeyboardButton(text_unsubscribe_button(lang), callback_data="unsubscribe")]]

        await update.message.reply_text(
            text_subscribe_info(lang),
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    # Купить Stars
    elif text == bt["buy"]:
        await update.message.reply_text(
            text_tonstars(lang),
            disable_web_page_preview=False,
        )


async def price_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_user_language(user_id)

    p = get_ton_price_usd()
    if p:
        await update.message.reply_text(text_price_ok(lang, p))
    else:
        await update.message.reply_text(text_price_error(lang))


async def chart_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_user_language(user_id)

    info = await update.message.reply_text(text_chart_build(lang))

    try:
        img = create_ton_chart()
        await update.message.reply_photo(
            img,
            caption="[Binance](https://www.binance.com/referral/earn-together/"
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

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("price", price_command))
    app.add_handler(CommandHandler("chart", chart_command))

    # callback-кнопки (язык, отписка)
    app.add_handler(CallbackQueryHandler(callback_handler))

    # все текстовые сообщения (нижние кнопки)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, footer_buttons_handler))

    app.run_polling()


if __name__ == "__main__":
    main()
