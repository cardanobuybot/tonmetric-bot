import os
import io
from datetime import datetime

import requests
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from telegram.ext import (
    ApplicationBuilder,
    Application,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

import asyncpg

BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

# Binance API
BINANCE_TICKER = "https://api.binance.com/api/v3/ticker/price"
BINANCE_KLINES = "https://api.binance.com/api/v3/klines"
SYMBOL = "TONUSDT"

# Язык пользователя в памяти (просто dict по user_id)
user_lang: dict[int, str] = {}  # user_id -> 'ru' | 'en' | 'uk'

# Пул соединений к базе
db_pool: asyncpg.Pool | None = None


# -------------------------------------------------
# ТЕКСТЫ
# -------------------------------------------------


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


def text_notifications_unavailable(lang: str) -> str:
    if lang == "en":
        return "Notifications are temporarily unavailable 🙈"
    elif lang == "uk":
        return "Сповіщення тимчасово недоступні 🙈"
    else:
        return "Уведомления временно недоступны 🙈"


def text_subscribed(lang: str, price: float) -> str:
    if lang == "en":
        return (
            "You are subscribed to TON price alerts ✅\n\n"
            f"Base price: {price:.3f} $.\n"
            "We'll notify you when TON moves more than 10% up or down."
        )
    elif lang == "uk":
        return (
            "Ви підписані на сповіщення про ціну TON ✅\n\n"
            f"Базова ціна: {price:.3f} $.\n"
            "Повідомимо, якщо TON зміниться більш ніж на 10% вгору чи вниз."
        )
    else:
        return (
            "Вы подписаны на уведомления о цене TON ✅\n\n"
            f"Базовая цена: {price:.3f} $.\n"
            "Сообщу, если TON изменится больше чем на 10% вверх или вниз."
        )


def text_unsubscribed(lang: str) -> str:
    if lang == "en":
        return "You have unsubscribed from TON price alerts."
    elif lang == "uk":
        return "Ви відписалися від сповіщень про ціну TON."
    else:
        return "Вы отписались от уведомлений о цене TON."


def text_unsub_button(lang: str) -> str:
    if lang == "en":
        return "Unsubscribe"
    elif lang == "uk":
        return "Відписатися"
    else:
        return "Отписаться"


def text_wallet(lang: str) -> str:
    if lang == "en":
        return "Open wallet: http://t.me/send?start=r-71wfg"
    elif lang == "uk":
        return "Відкрити гаманець: http://t.me/send?start=r-71wfg"
    else:
        return "Открыть кошелёк: http://t.me/send?start=r-71wfg"


def text_buy_stars(lang: str) -> str:
    if lang == "en":
        return "Open TON Stars: https://tonstars.io"
    elif lang == "uk":
        return "Відкрийте TON Stars: https://tonstars.io"
    else:
        return "Откройте TON Stars: https://tonstars.io"


def text_memland(lang: str) -> str:
    if lang == "en":
        return "TOP-5 Memeland will appear here later 🦄"
    elif lang == "uk":
        return "Тут пізніше з'явиться ТОП-5 Мемляндії 🦄"
    else:
        return "Тут позже появится ТОП-5 Мемляндии 🦄"


# подписи для фиксированных кнопок
FOOTER_LABELS = {
    "ru": {
        "rate": "Курс",
        "chart": "График",
        "notify": "Уведомления",
        "stars": "Купить Stars ⭐",
        "wallet": "Кошелёк",
        "mem": "Мемляндия🦄",
    },
    "uk": {
        "rate": "Курс",
        "chart": "Графік",
        "notify": "Сповіщення",
        "stars": "Купити Stars ⭐",
        "wallet": "Гаманець",
        "mem": "Мемляндія🦄",
    },
    "en": {
        "rate": "Rate",
        "chart": "Chart",
        "notify": "Notifications",
        "stars": "Buy Stars ⭐",
        "wallet": "Wallet",
        "mem": "Memeland 🦄",
    },
}


def footer_buttons(lang: str) -> ReplyKeyboardMarkup:
    labels = FOOTER_LABELS.get(lang, FOOTER_LABELS["ru"])
    keyboard = [
        [KeyboardButton(labels["rate"])],
        [KeyboardButton(labels["chart"])],
        [KeyboardButton(labels["notify"])],
        [KeyboardButton(labels["stars"])],
        [KeyboardButton(labels["wallet"])],
        [KeyboardButton(labels["mem"])],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)


# -------------------------------------------------
# BINANCE ДАННЫЕ + ГРАФИК
# -------------------------------------------------


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


async def send_price_and_chart(chat_id: int, lang: str, context: ContextTypes.DEFAULT_TYPE):
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
            caption="[Binance](https://www.binance.com/referral/earn-together/"
            "refer2earn-usdc/claim?hl=en&ref=GRO_28502_1C1WM&utm_source=default)",
            parse_mode="Markdown",
        )
    except Exception as e:
        print("Chart error:", e)
        await context.bot.send_message(chat_id, text_chart_error(lang))


# -------------------------------------------------
# БАЗА: ПОДПИСКИ
# -------------------------------------------------


async def init_db():
    global db_pool
    if not DATABASE_URL:
        print("DATABASE_URL not set, notifications disabled")
        return

    db_pool = await asyncpg.create_pool(DATABASE_URL)
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ton_subscriptions (
                user_id BIGINT,
                chat_id BIGINT,
                base_price DOUBLE PRECISION NOT NULL,
                lang VARCHAR(3) NOT NULL,
                PRIMARY KEY (user_id, chat_id)
            );
            """
        )
    print("DB initialized")


async def subscribe_user(user_id: int, chat_id: int, lang: str) -> float | None:
    """Сохраняем/обновляем подписку, возвращаем базовую цену."""
    if db_pool is None:
        return None

    price = get_ton_price_usd()
    if price is None:
        return None

    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO ton_subscriptions (user_id, chat_id, base_price, lang)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (user_id, chat_id)
            DO UPDATE SET base_price = EXCLUDED.base_price,
                          lang = EXCLUDED.lang
            """,
            user_id,
            chat_id,
            price,
            lang,
        )
    return price


async def unsubscribe_user(user_id: int, chat_id: int) -> None:
    if db_pool is None:
        return
    async with db_pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM ton_subscriptions WHERE user_id=$1 AND chat_id=$2",
            user_id,
            chat_id,
        )


async def check_price_job(context: ContextTypes.DEFAULT_TYPE):
    """Фоновая задача: каждые N секунд проверяет цену и шлёт пуши."""
    if db_pool is None:
        return

    price = get_ton_price_usd()
    if price is None:
        print("check_price_job: cannot get price")
        return

    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT user_id, chat_id, base_price, lang FROM ton_subscriptions"
        )

        for row in rows:
            base = row["base_price"]
            if base == 0:
                continue

            diff = abs(price - base) / base

            if diff >= 0.10:  # 10%
                lang = row["lang"]
                chat_id = row["chat_id"]

                if lang == "en":
                    msg = (
                        "TON price changed more than 10%.\n"
                        f"Current: {price:.3f} $ (was {base:.3f} $)."
                    )
                elif lang == "uk":
                    msg = (
                        "Ціна TON змінилася більш ніж на 10%.\n"
                        f"Поточна: {price:.3f} $ (було {base:.3f} $)."
                    )
                else:
                    msg = (
                        "Цена TON изменилась более чем на 10%.\n"
                        f"Текущая: {price:.3f} $ (было {base:.3f} $)."
                    )

                try:
                    await context.bot.send_message(chat_id, msg)
                except Exception as e:
                    print("send notification error:", e)
                    continue

                # обновляем базу: новая базовая цена = текущая
                await conn.execute(
                    """
                    UPDATE ton_subscriptions
                    SET base_price=$1
                    WHERE user_id=$2 AND chat_id=$3
                    """,
                    price,
                    row["user_id"],
                    chat_id,
                )


# -------------------------------------------------
# ХЕНДЛЕРЫ
# -------------------------------------------------


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

    data = query.data
    user_id = query.from_user.id
    chat_id = query.message.chat_id

    # выбор языка
    if data.startswith("lang_"):
        lang = data.split("_", 1)[1]
        user_lang[user_id] = lang

        await context.bot.send_message(chat_id, text_lang_confirm(lang))

        # сразу курс + график
        await send_price_and_chart(chat_id, lang, context)

        # и нижние кнопки
        await context.bot.send_message(
            chat_id,
            {
                "en": "Choose an action:",
                "uk": "Оберіть дію:",
            }.get(lang, "Выберите действие:"),
            reply_markup=footer_buttons(lang),
        )

    # отписка
    elif data == "unsubscribe":
        lang = get_user_language(user_id)
        await unsubscribe_user(user_id, chat_id)
        await query.edit_message_text(text_unsubscribed(lang))


async def price_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_user_language(user_id)

    p = get_ton_price_usd()
    if p is None:
        await update.message.reply_text(text_price_error(lang))
    else:
        await update.message.reply_text(text_price_ok(lang, p))


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


async def footer_buttons_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_user_language(user_id)
    labels = FOOTER_LABELS.get(lang, FOOTER_LABELS["ru"])

    text_val = (update.message.text or "").strip()

    # Курс
    if text_val == labels["rate"]:
        await price_command(update, context)
        return

    # График
    if text_val == labels["chart"]:
        await chart_command(update, context)
        return

    # Уведомления (подписка)
    if text_val == labels["notify"]:
        if db_pool is None:
            await update.message.reply_text(text_notifications_unavailable(lang))
            return

        price = await subscribe_user(user_id, update.effective_chat.id, lang)
        if price is None:
            await update.message.reply_text(text_notifications_unavailable(lang))
            return

        kb = InlineKeyboardMarkup(
            [[InlineKeyboardButton(text_unsub_button(lang), callback_data="unsubscribe")]]
        )
        await update.message.reply_text(text_subscribed(lang, price), reply_markup=kb)
        return

    # Купить Stars
    if text_val == labels["stars"]:
        await update.message.reply_text(text_buy_stars(lang))
        return

    # Кошелёк
    if text_val == labels["wallet"]:
        await update.message.reply_text(text_wallet(lang))
        return

    # Мемляндия
    if text_val == labels["mem"]:
        await update.message.reply_text(text_memland(lang))
        return


# -------------------------------------------------
# STARTUP + MAIN
# -------------------------------------------------


async def on_startup(app: Application):
    await init_db()
    if app.job_queue is not None and db_pool is not None:
        app.job_queue.run_repeating(check_price_job, interval=300, first=60)
    else:
        print("JobQueue or DB not available, notifications disabled")


def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN не задан в переменных окружения")

    app: Application = ApplicationBuilder().token(BOT_TOKEN).build()

    # команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("price", price_command))
    app.add_handler(CommandHandler("chart", chart_command))

    # callback-кнопки (язык + отписка)
    app.add_handler(CallbackQueryHandler(callback_handler))

    # текстовые фикс-кнопки
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, footer_buttons_handler))

    app.run_polling(post_init=on_startup)


if __name__ == "__main__":
    main()
