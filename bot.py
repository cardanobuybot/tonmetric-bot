import os
import io
from datetime import datetime
import logging

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
import asyncpg

# ---------- ENV ----------

BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

# ---------- CONSTANTS ----------

# Binance API
BINANCE_TICKER = "https://api.binance.com/api/v3/ticker/price"
BINANCE_KLINES = "https://api.binance.com/api/v3/klines"
SYMBOL = "TONUSDT"

# user_id -> 'ru' | 'en' | 'uk'
user_lang: dict[int, str] = {}

# пул соединений с БД
db_pool: asyncpg.pool.Pool | None = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ---------- ТЕКСТЫ ----------

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


def footer_labels(lang: str) -> dict[str, str]:
    if lang == "en":
        return {
            "price": "Rate",
            "chart": "Chart",
            "notify": "Notifications",
            "buy_stars": "Buy Stars ⭐",
            "wallet": "Wallet",
            "memeland": "Memeland 🦄",
        }
    elif lang == "uk":
        return {
            "price": "Курс",
            "chart": "Графік",
            "notify": "Сповіщення",
            "buy_stars": "Купити Stars ⭐",
            "wallet": "Гаманець",
            "memeland": "Мемляндія 🦄",
        }
    else:
        return {
            "price": "Курс",
            "chart": "График",
            "notify": "Уведомления",
            "buy_stars": "Купить Stars ⭐",
            "wallet": "Кошелёк",
            "memeland": "Мемляндия🦄",
        }


def footer_keyboard(lang: str) -> ReplyKeyboardMarkup:
    labels = footer_labels(lang)
    keyboard = [
        [KeyboardButton(labels["price"])],
        [KeyboardButton(labels["chart"])],
        [KeyboardButton(labels["notify"])],
        [KeyboardButton(labels["buy_stars"])],
        [KeyboardButton(labels["wallet"])],
        [KeyboardButton(labels["memeland"])],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)


def notification_subscribed_text(lang: str, price: float) -> str:
    if lang == "en":
        return (
            f"Notifications enabled ✅\n\n"
            f"We'll notify you if TON price changes more than 10% from {price:.3f} $."
        )
    elif lang == "uk":
        return (
            f"Сповіщення увімкнено ✅\n\n"
            f"Ми повідомимо, якщо ціна TON зміниться більше ніж на 10% від {price:.3f} $."
        )
    else:
        return (
            f"Уведомления включены ✅\n\n"
            f"Мы сообщим, если цена TON изменится больше чем на 10% от {price:.3f} $."
        )


def notification_unsubscribed_text(lang: str) -> str:
    if lang == "en":
        return "Notifications disabled ❌"
    elif lang == "uk":
        return "Сповіщення вимкнено ❌"
    else:
        return "Уведомления отключены ❌"


def notification_alert_text(lang: str, old: float, new: float) -> str:
    change = (new - old) / old * 100
    if lang == "en":
        direction = "up" if change > 0 else "down"
        return (
            f"TON price changed {direction} by {abs(change):.1f}%\n"
            f"Old price: {old:.3f} $\n"
            f"New price: {new:.3f} $"
        )
    elif lang == "uk":
        direction = "вгору" if change > 0 else "вниз"
        return (
            f"Ціна TON змінилася {direction} на {abs(change):.1f}%\n"
            f"Стара ціна: {old:.3f} $\n"
            f"Нова ціна: {new:.3f} $"
        )
    else:
        direction = "вверх" if change > 0 else "вниз"
        return (
            f"Цена TON изменилась {direction} на {abs(change):.1f}%\n"
            f"Старая цена: {old:.3f} $\n"
            f"Новая цена: {new:.3f} $"
        )


def buy_stars_text(lang: str) -> str:
    if lang == "en":
        return "Open TON Stars: https://tonstars.io"
    elif lang == "uk":
        return "Відкрийте TON Stars: https://tonstars.io"
    else:
        return "Откройте TON Stars: https://tonstars.io"


def wallet_text(lang: str) -> str:
    if lang == "en":
        return "Open wallet: http://t.me/send?start=r-71wfg"
    elif lang == "uk":
        return "Відкрити гаманець: http://t.me/send?start=r-71wfg"
    else:
        return "Открыть кошелёк: http://t.me/send?start=r-71wfg"


def memeland_text(lang: str) -> str:
    if lang == "en":
        return "Memeland TOP-5 will appear here later 🦄"
    elif lang == "uk":
        return "Тут пізніше з'явиться ТОП-5 Мемляндії 🦄"
    else:
        return "Тут позже появится ТОП-5 Мемляндии 🦄"


# ---------- ДАННЫЕ TON ----------

def get_ton_price_usd():
    try:
        r = requests.get(BINANCE_TICKER, params={"symbol": SYMBOL}, timeout=8)
        data = r.json()
        return float(data["price"])
    except Exception as e:
        logger.error("Price error: %s", e)
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
        logger.error("History error: %s", e)
        return [], []


def create_ton_chart():
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


# ---------- ОТПРАВКА ЦЕНЫ / ГРАФИКА ----------

async def send_price_and_chart(
    chat_id: int, lang: str, context: ContextTypes.DEFAULT_TYPE
):
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
            caption="[Binance](https://www.binance.com/referral/earn-together/refer2earn-usdc/claim?hl=en&ref=GRO_28502_1C1WM&utm_source=default)",
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error("Chart error: %s", e)
        await context.bot.send_message(chat_id, text_chart_error(lang))


async def send_price_only(
    chat_id: int, lang: str, context: ContextTypes.DEFAULT_TYPE
):
    p = get_ton_price_usd()
    if p:
        await context.bot.send_message(chat_id, text_price_ok(lang, p))
    else:
        await context.bot.send_message(chat_id, text_price_error(lang))


async def send_chart_only(
    update: Update, context: ContextTypes.DEFAULT_TYPE, lang: str
):
    info = await update.message.reply_text(text_chart_build(lang))
    try:
        img = create_ton_chart()
        await update.message.reply_photo(
            img,
            caption="[Binance](https://www.binance.com/referral/earn-together/refer2earn-usdc/claim?hl=en&ref=GRO_28502_1C1WM&utm_source=default)",
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error("Chart error: %s", e)
        await update.message.reply_text(text_chart_error(lang))
    finally:
        try:
            await info.delete()
        except Exception:
            pass


# ---------- БАЗА ДАННЫХ ----------

async def init_db():
    """Создаём пул и таблицу subscribers."""
    global db_pool
    if not DATABASE_URL:
        logger.error("DATABASE_URL is not set")
        return

    db_pool = await asyncpg.create_pool(DATABASE_URL)

    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS subscribers (
                user_id BIGINT PRIMARY KEY,
                lang TEXT NOT NULL,
                base_price DOUBLE PRECISION NOT NULL,
                active BOOLEAN NOT NULL DEFAULT TRUE
            )
            """
        )
    logger.info("DB initialized")


async def subscribe_user(user_id: int, lang: str) -> float | None:
    """Подписать пользователя и запомнить текущую цену как базовую."""
    if db_pool is None:
        return None

    price = get_ton_price_usd()
    if price is None:
        return None

    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO subscribers(user_id, lang, base_price, active)
            VALUES($1, $2, $3, TRUE)
            ON CONFLICT (user_id)
            DO UPDATE SET lang = EXCLUDED.lang,
                          base_price = EXCLUDED.base_price,
                          active = TRUE
            """,
            user_id,
            lang,
            price,
        )
    return price


async def unsubscribe_user(user_id: int):
    if db_pool is None:
        return
    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE subscribers SET active = FALSE WHERE user_id = $1",
            user_id,
        )


async def check_price_job(context: ContextTypes.DEFAULT_TYPE):
    """Периодически проверяем цену и шлём пуш, если изменилось >10%."""
    if db_pool is None:
        return

    current_price = get_ton_price_usd()
    if current_price is None:
        return

    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT user_id, lang, base_price FROM subscribers WHERE active = TRUE"
        )

        for row in rows:
            user_id = row["user_id"]
            lang = row["lang"]
            base_price = row["base_price"]

            if base_price <= 0:
                continue

            change = abs(current_price - base_price) / base_price
            if change >= 0.10:  # 10%
                try:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=notification_alert_text(
                            lang, base_price, current_price
                        ),
                    )
                    # обновляем базовую цену, чтобы дальше считать от нового уровня
                    await conn.execute(
                        "UPDATE subscribers SET base_price = $1 WHERE user_id = $2",
                        current_price,
                        user_id,
                    )
                except Exception as e:
                    logger.error(
                        "Error sending alert to %s: %s", user_id, e
                    )


# ---------- ХЕНДЛЕРЫ ----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/start — выбор языка через инлайн-кнопки."""
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
    """Обрабатываем выбор языка и кнопку Отписаться."""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    chat_id = query.message.chat_id
    data = query.data

    # выбор языка
    if data.startswith("lang_"):
        lang = data.split("_", 1)[1]  # en / ru / uk
        user_lang[user_id] = lang

        # подтверждение + сразу прикрутим нижнюю клаву
        await query.message.reply_text(
            text_lang_confirm(lang),
            reply_markup=footer_keyboard(lang),
        )

        # сразу же курс + график
        await send_price_and_chart(chat_id, lang, context)

    # отписка от уведомлений
    elif data == "unsubscribe":
        lang = get_user_language(user_id)
        await unsubscribe_user(user_id)
        await query.message.reply_text(notification_unsubscribed_text(lang))


async def footer_buttons_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нижних фикс-кнопок."""
    user_id = update.effective_user.id
    lang = get_user_language(user_id)
    labels = footer_labels(lang)
    text = update.message.text

    # Курс
    if text == labels["price"]:
        await send_price_only(update.effective_chat.id, lang, context)

    # График
    elif text == labels["chart"]:
        await send_chart_only(update, context, lang)

    # Уведомления — сразу подписываем и даём кнопку Отписаться
    elif text == labels["notify"]:
        price = await subscribe_user(user_id, lang)
        if price is None:
            await update.message.reply_text(text_price_error(lang))
            return

        unsub_text = (
            "Отписаться"
            if lang == "ru"
            else ("Unsubscribe" if lang == "en" else "Відписатися")
        )
        kb = InlineKeyboardMarkup(
            [[InlineKeyboardButton(unsub_text, callback_data="unsubscribe")]]
        )

        await update.message.reply_text(
            notification_subscribed_text(lang, price),
            reply_markup=kb,
        )

    # Купить Stars
    elif text == labels["buy_stars"]:
        await update.message.reply_text(buy_stars_text(lang))

    # Кошелёк
    elif text == labels["wallet"]:
        await update.message.reply_text(wallet_text(lang))

    # Мемляндия
    elif text == labels["memeland"]:
        await update.message.reply_text(memeland_text(lang))


async def price_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_user_language(user_id)
    await send_price_only(update.effective_chat.id, lang, context)


async def chart_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_user_language(user_id)
    await send_chart_only(update, context, lang)


# ---------- STARTUP ----------

async def on_startup(app):
    # инициализируем БД + заводим cron-задачу
    await init_db()
    if app.job_queue:
        app.job_queue.run_repeating(check_price_job, interval=600, first=60)


def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set")

    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .post_init(on_startup)  # вызов on_startup после запуска
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("price", price_command))
    app.add_handler(CommandHandler("chart", chart_command))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, footer_buttons_handler)
    )

    app.run_polling()


if __name__ == "__main__":
    main()
