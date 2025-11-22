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

import psycopg2

BOT_TOKEN = os.getenv("BOT_TOKEN")

# Binance API
BINANCE_TICKER = "https://api.binance.com/api/v3/ticker/price"
BINANCE_KLINES = "https://api.binance.com/api/v3/klines"
SYMBOL = "TONUSDT"

# язык пользователя
user_lang: dict[int, str] = {}

# Postgres
DATABASE_URL = os.getenv("DATABASE_URL")


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


# ---------- ДАННЫЕ TON ----------

def get_ton_price_usd() -> float | None:
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


# ---------- ГРАФИК ----------

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


# ---------- БАЗА: ПОДПИСКИ ----------

def init_db():
    if not DATABASE_URL:
        print("DATABASE_URL not set, notifications disabled")
        return

    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS ton_subscriptions (
            id SERIAL PRIMARY KEY,
            chat_id BIGINT UNIQUE NOT NULL,
            base_price NUMERIC(18,8) NOT NULL,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
        """
    )
    conn.commit()
    cur.close()
    conn.close()


def save_subscription(chat_id: int, base_price: float):
    if not DATABASE_URL:
        return
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO ton_subscriptions (chat_id, base_price)
        VALUES (%s, %s)
        ON CONFLICT (chat_id)
        DO UPDATE SET base_price = EXCLUDED.base_price, created_at = NOW()
        """,
        (chat_id, base_price),
    )
    conn.commit()
    cur.close()
    conn.close()


def delete_subscription(chat_id: int):
    if not DATABASE_URL:
        return
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("DELETE FROM ton_subscriptions WHERE chat_id = %s", (chat_id,))
    conn.commit()
    cur.close()
    conn.close()


def get_all_subscriptions():
    if not DATABASE_URL:
        return []
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("SELECT chat_id, base_price FROM ton_subscriptions")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


# ---------- КНОПКИ ----------

def footer_buttons(lang: str = "ru") -> ReplyKeyboardMarkup:
    if lang == "en":
        labels = [
            "Rate",
            "Chart",
            "Notifications",
            "Buy Stars ⭐",
            "Wallet",
            "Memeland 🦄",
        ]
    elif lang == "uk":
        labels = [
            "Курс",
            "Графік",
            "Сповіщення",
            "Купити Stars ⭐",
            "Гаманець",
            "Мемляндія🦄",
        ]
    else:
        labels = [
            "Курс",
            "График",
            "Уведомления",
            "Купить Stars ⭐",
            "Кошелёк",
            "Мемляндия🦄",
        ]

    keyboard = [
        [KeyboardButton(labels[0])],
        [KeyboardButton(labels[1])],
        [KeyboardButton(labels[2])],
        [KeyboardButton(labels[3])],
        [KeyboardButton(labels[4])],
        [KeyboardButton(labels[5])],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)


# ---------- ХЕНДЛЕРЫ ----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_lang[user_id] = "ru"

    keyboard = [[
        InlineKeyboardButton("English", callback_data="lang_en"),
        InlineKeyboardButton("Русский", callback_data="lang_ru"),
        InlineKeyboardButton("Українська", callback_data="lang_uk"),
    ]]

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

    # смена языка
    if data.startswith("lang_"):
        lang = data.split("_", 1)[1]
        user_lang[user_id] = lang

        await query.message.reply_text(
            text_lang_confirm(lang),
            reply_markup=footer_buttons(lang),
        )

        # сразу показать текущий курс
        price = get_ton_price_usd()
        if price is not None:
            await query.message.reply_text(text_price_ok(lang, price))
        else:
            await query.message.reply_text(text_price_error(lang))

    # отписка от уведомлений
    elif data == "unsub_price":
        delete_subscription(chat_id)
        lang = get_user_language(user_id)
        if lang == "en":
            txt = "You have unsubscribed from price alerts."
        elif lang == "uk":
            txt = "Ви відписалися від сповіщень про курс TON."
        else:
            txt = "Вы отписались от уведомлений об изменении цены TON."
        await query.message.reply_text(txt)


async def footer_buttons_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    lang = get_user_language(user_id)

    # --- Курс ---
    if text in ["Курс", "Rate"]:
        price = get_ton_price_usd()
        if price is None:
            await update.message.reply_text(text_price_error(lang))
        else:
            await update.message.reply_text(text_price_ok(lang, price))

    # --- График ---
    elif text in ["График", "Chart", "Графік"]:
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

    # --- Уведомления (подписка) ---
    elif text in ["Уведомления", "Notifications", "Сповіщення"]:
        current_price = get_ton_price_usd()
        if current_price is None:
            await update.message.reply_text(text_price_error(lang))
            return

        # сохранить/обновить подписку
        save_subscription(chat_id, current_price)

        if lang == "en":
            msg = (
                f"We'll notify you when TON moves more than 10% "
                f"from {current_price:.3f} $. After alert you'll be unsubscribed."
            )
            unsub = "Unsubscribe"
        elif lang == "uk":
            msg = (
                f"Повідомимо, якщо TON зміниться більше ніж на 10% "
                f"від {current_price:.3f} $. Після сповіщення підписка буде видалена."
            )
            unsub = "Відписатися"
        else:
            msg = (
                f"Уведомим, если TON изменится более чем на 10% "
                f"от {current_price:.3f} $. После уведомления подписка будет удалена."
            )
            unsub = "Отписаться"

        kb = InlineKeyboardMarkup(
            [[InlineKeyboardButton(unsub, callback_data="unsub_price")]]
        )
        await update.message.reply_text(msg, reply_markup=kb)

    # --- Купить Stars ---
    elif text in ["Купить Stars ⭐", "Buy Stars ⭐", "Купити Stars ⭐"]:
        if lang == "en":
            msg = "Open TON Stars: https://tonstars.io"
        elif lang == "uk":
            msg = "Відкрийте TON Stars: https://tonstars.io"
        else:
            msg = "Відкройте TON Stars: https://tonstars.io"
        await update.message.reply_text(msg)

    # --- Кошелёк / Wallet ---
    elif text in ["Кошелёк", "Wallet", "Гаманець"]:
        if lang == "en":
            msg = "Open wallet: http://t.me/send?start=r-71wfg"
        elif lang == "uk":
            msg = "Відкрити гаманець: http://t.me/send?start=r-71wfg"
        else:
            msg = "Открыть кошелёк: http://t.me/send?start=r-71wfg"
        await update.message.reply_text(msg)

    # --- Мемляндия ---
    elif text in ["Мемляндия🦄", "Memeland 🦄", "Мемляндія🦄"]:
        if lang == "en":
            msg = "TOP-5 Memeland will appear here later 🦄"
        elif lang == "uk":
            msg = "Тут пізніше з'явиться ТОП-5 Мемляндії 🦄"
        else:
            msg = "Тут позже появится ТОП-5 Мемляндии 🦄"
        await update.message.reply_text(msg)


# ---------- JOB: ПРОВЕРКА ПОДПИСОК ----------

async def check_price_job(context: ContextTypes.DEFAULT_TYPE):
    price = get_ton_price_usd()
    if price is None:
        return

    subs = get_all_subscriptions()
    if not subs:
        return

    for chat_id, base_price in subs:
        base = float(base_price)
        if price >= base * 1.10:
            text = (
                f"TON вырос более чем на 10% от вашей цены {base:.3f} $. "
                f"Текущая цена: {price:.3f} $. Подписка отключена."
            )
        elif price <= base * 0.90:
            text = (
                f"TON упал более чем на 10% от вашей цены {base:.3f} $. "
                f"Текущая цена: {price:.3f} $. Подписка отключена."
            )
        else:
            continue

        try:
            await context.bot.send_message(int(chat_id), text)
        except Exception as e:
            print("Send error:", e)

        # автоотписка после уведомления
        delete_subscription(chat_id)


# ---------- MAIN ----------

def main():
    init_db()

    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN не задан в переменных окружения")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, footer_buttons_handler))

    # фоновые проверки цены каждые 5 минут
    job_queue = app.job_queue
    job_queue.run_repeating(check_price_job, interval=300, first=60)

    app.run_polling()


if __name__ == "__main__":
    main()
