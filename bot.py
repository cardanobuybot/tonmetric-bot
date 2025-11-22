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

BINANCE_REF_URL = (
    "https://www.binance.com/referral/earn-together/refer2earn-usdc/claim"
    "?hl=en&ref=GRO_28502_1C1WM&utm_source=default"
)
TONSTARS_URL = "https://tonstars.io"

# Храним язык пользователя в памяти
user_lang: dict[int, str] = {}  # user_id -> 'ru' | 'en' | 'uk'


# ------------------ ВСПОМОГАТЕЛЬНОЕ ------------------


def get_user_language(user_id: int) -> str:
    return user_lang.get(user_id, "ru")


def footer_labels(lang: str) -> dict:
    """Тексты кнопок внизу, по языку."""
    if lang == "en":
        return {
            "price": "Price",
            "chart": "Chart",
            "notify": "Notifications",
            "buy": "Buy Stars ⭐",
        }
    elif lang == "uk":
        return {
            "price": "Курс",
            "chart": "Графік",
            "notify": "Сповіщення",
            "buy": "Купити Stars ⭐",
        }
    else:  # ru
        return {
            "price": "Курс",
            "chart": "График",
            "notify": "Уведомления",
            "buy": "Купить Stars ⭐",
        }


def footer_buttons(lang: str) -> ReplyKeyboardMarkup:
    bt = footer_labels(lang)
    keyboard = [
        [KeyboardButton(bt["price"])],
        [KeyboardButton(bt["chart"])],
        [KeyboardButton(bt["notify"])],
        [KeyboardButton(bt["buy"])],
    ]
    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
        one_time_keyboard=False,
    )


# ------------------ ТЕКСТЫ ------------------


def text_lang_confirm(lang: str) -> str:
    if lang == "en":
        return "Language: English ✅\nLoading TON price and chart…"
    elif lang == "uk":
        return "Мова: Українська ✅\nЗавантажую курс та графік TON…"
    else:
        return "Язык: Русский ✅\nЗагружаю курс и график TON…"


def text_price_ok(lang: str, price: float) -> str:
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


def text_notify_stub(lang: str) -> str:
    if lang == "en":
        return "Notifications settings will be available later 🔔"
    elif lang == "uk":
        return "Налаштування сповіщень з'являться пізніше 🔔"
    else:
        return "Настройки уведомлений появятся позже 🔔"


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
            params={"symbol": SYMBOL, "interval": "1h", "limit": hours},
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

    # цена снизу графика
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

    # цена
    await context.bot.send_message(
        chat_id,
        text_price_ok(lang, price),
        reply_markup=footer_buttons(lang),
    )

    # график с Binance-ссылкой
    try:
        img = create_ton_chart()
        await context.bot.send_photo(
            chat_id,
            img,
            caption=f"[Binance]({BINANCE_REF_URL})",
            parse_mode="Markdown",
        )
    except Exception as e:
        print("Chart error:", e)
        await context.bot.send_message(chat_id, text_chart_error(lang))


# ------------------ ХЕНДЛЕРЫ ------------------


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    # по умолчанию рус
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
    """Обработка выбора языка (inline-кнопки)."""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    chat_id = query.message.chat_id
    data = query.data

    if data.startswith("lang_"):
        lang = data.split("_", 1)[1]  # en / ru / uk
        user_lang[user_id] = lang

        # подтверждение языка
        await query.message.reply_text(
            text_lang_confirm(lang),
            reply_markup=footer_buttons(lang),
        )

        # сразу курс + график
        await send_price_and_chart(chat_id, lang, context)


async def footer_buttons_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка нажатий на фиксированные кнопки снизу."""
    user_id = update.effective_user.id
    lang = get_user_language(user_id)
    bt = footer_labels(lang)

    text = (update.message.text or "").strip()

    # КУРС
    if text == bt["price"]:
        p = get_ton_price_usd()
        if p is None:
            await update.message.reply_text(
                text_price_error(lang),
                reply_markup=footer_buttons(lang),
            )
        else:
            await update.message.reply_text(
                text_price_ok(lang, p),
                reply_markup=footer_buttons(lang),
            )

    # ГРАФИК
    elif text == bt["chart"]:
        info = await update.message.reply_text(
            text_chart_build(lang),
            reply_markup=footer_buttons(lang),
        )
        try:
            img = create_ton_chart()
            await update.message.reply_photo(
                img,
                caption=f"[Binance]({BINANCE_REF_URL})",
                parse_mode="Markdown",
            )
        except Exception as e:
            print("Chart error:", e)
            await update.message.reply_text(
                text_chart_error(lang),
                reply_markup=footer_buttons(lang),
            )
        finally:
            try:
                await info.delete()
            except Exception:
                pass

    # УВЕДОМЛЕНИЯ
    elif text == bt["notify"]:
        await update.message.reply_text(
            text_notify_stub(lang),
            reply_markup=footer_buttons(lang),
        )

    # КУПИТЬ STARS
    elif text == bt["buy"]:
        # Стиль как у Binance — одно слово, которое является ссылкой
        msg = f"[TON Stars]({TONSTARS_URL})"
        await update.message.reply_text(
            msg,
            parse_mode="Markdown",
            reply_markup=footer_buttons(lang),
        )
    else:
        # На всякий случай — ничего не ломаем, просто возвращаем клаву
        await update.message.reply_text(
            "…",
            reply_markup=footer_buttons(lang),
        )


async def price_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/price — дублирующая команда, если кто-то любит слэш-команды."""
    user_id = update.effective_user.id
    lang = get_user_language(user_id)

    p = get_ton_price_usd()
    if p is None:
        await update.message.reply_text(
            text_price_error(lang),
            reply_markup=footer_buttons(lang),
        )
    else:
        await update.message.reply_text(
            text_price_ok(lang, p),
            reply_markup=footer_buttons(lang),
        )


async def chart_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ /chart — дублирующая команда. """
    user_id = update.effective_user.id
    lang = get_user_language(user_id)

    info = await update.message.reply_text(
        text_chart_build(lang),
        reply_markup=footer_buttons(lang),
    )
    try:
        img = create_ton_chart()
        await update.message.reply_photo(
            img,
            caption=f"[Binance]({BINANCE_REF_URL})",
            parse_mode="Markdown",
        )
    except Exception as e:
        print("Chart error:", e)
        await update.message.reply_text(
            text_chart_error(lang),
            reply_markup=footer_buttons(lang),
        )
    finally:
        try:
            await info.delete()
        except Exception:
            pass


def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN не задан в переменных окружения")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("price", price_cmd))
    app.add_handler(CommandHandler("chart", chart_cmd))

    # Inline-кнопки выбора языка
    app.add_handler(CallbackQueryHandler(lang_button))

    # Фиксированные кнопки снизу
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, footer_buttons_handler)
    )

    app.run_polling()


if __name__ == "__main__":
    main()
