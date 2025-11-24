import os
import io
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

import requests
import psycopg2

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InputFile,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

# ------------------ ENV ------------------

BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не задан в переменных окружения")

# ------------------ BINANCE API ------------------

BINANCE_TICKER = "https://api.binance.com/api/v3/ticker/price"
BINANCE_KLINES = "https://api.binance.com/api/v3/klines"
SYMBOL = "TONUSDT"

# ------------------ MEMELANDIA API ------------------

MEMELANDIA_URL = "https://memelandia.okhlopkov.com/api/leaderboard"

# ------------------ ЯЗЫК ------------------

user_lang: dict[int, str] = {}  # user_id -> 'ru' | 'en' | 'uk'


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


def text_menu_prompt(lang: str) -> str:
    if lang == "en":
        return "Choose an action:"
    elif lang == "uk":
        return "Оберіть дію:"
    else:
        return "Выберите действие:"


def text_subscribed(lang: str, base_price: float) -> str:
    if lang == "en":
        return (
            f"Notifications are ON ✅\n\n"
            f"We will notify you when TON price changes more than 10% "
            f"from {base_price:.3f} $.\n\n"
            f"To stop notifications, press «Unsubscribe»."
        )
    elif lang == "uk":
        return (
            f"Сповіщення увімкнено ✅\n\n"
            f"Ми повідомимо, коли ціна TON зміниться більш ніж на 10% "
            f"від {base_price:.3f} $.\n\n"
            f"Щоб вимкнути сповіщення, натисніть «Відписатися»."
        )
    else:
        return (
            f"Уведомления включены ✅\n\n"
            f"Мы сообщим, когда цена TON изменится более чем на 10% "
            f"от {base_price:.3f} $.\n\n"
            f"Чтобы выключить уведомления, нажмите «Отписаться»."
        )


def text_already_subscribed(lang: str) -> str:
    if lang == "en":
        return "Notifications are already ON ✅"
    elif lang == "uk":
        return "Сповіщення вже увімкнено ✅"
    else:
        return "Уведомления уже включены ✅"


def text_subscriptions_disabled(lang: str) -> str:
    if lang == "en":
        return "Notifications are temporarily unavailable 🙈"
    elif lang == "uk":
        return "Сповіщення тимчасово недоступні 🙈"
    else:
        return "Уведомления временно недоступны 🙈"


def text_unsubscribed(lang: str) -> str:
    if lang == "en":
        return "Notifications are OFF ❌"
    elif lang == "uk":
        return "Сповіщення вимкнено ❌"
    else:
        return "Уведомления отключены ❌"


def text_price_alert(lang: str, old: float, new: float, diff_percent: float) -> str:
    arrow = "⬆️" if new > old else "⬇️"
    if lang == "en":
        return (
            f"{arrow} TON price changed by {diff_percent:.1f}%\n\n"
            f"Was: {old:.3f} $\n"
            f"Now: {new:.3f} $"
        )
    elif lang == "uk":
        return (
            f"{arrow} Ціна TON змінилася на {diff_percent:.1f}%\n\n"
            f"Було: {old:.3f} $\n"
            f"Зараз: {new:.3f} $"
        )
    else:
        return (
            f"{arrow} Цена TON изменилась на {diff_percent:.1f}%\n\n"
            f"Было: {old:.3f} $\n"
            f"Сейчас: {new:.3f} $"
        )


def unsubscribe_button_text(lang: str) -> str:
    if lang == "en":
        return "Unsubscribe"
    elif lang == "uk":
        return "Відписатися"
    else:
        return "Отписаться"


# ------------------ ТЕКСТЫ КНОПОК ------------------

BUTTON_TEXTS = {
    "ru": {
        "price": "Курс",
        "chart": "График",
        "notify": "Уведомления",
        "buy_stars": "Купить Stars ⭐",
        "wallet": "Кошелёк",
        "memland": "Мемляндия🦄",
    },
    "en": {
        "price": "Rate",
        "chart": "Chart",
        "notify": "Notifications",
        "buy_stars": "Buy Stars ⭐",
        "wallet": "Wallet",
        "memland": "Memlandia🦄",
    },
    "uk": {
        "price": "Курс",
        "chart": "Графік",
        "notify": "Сповіщення",
        "buy_stars": "Купити Stars ⭐",
        "wallet": "Гаманець",
        "memland": "Мемляндія🦄",
    },
}


def get_button_texts(lang: str) -> dict:
    return BUTTON_TEXTS.get(lang, BUTTON_TEXTS["ru"])


def footer_buttons(lang: str) -> ReplyKeyboardMarkup:
    t = get_button_texts(lang)
    keyboard = [
        [KeyboardButton(t["price"])],
        [KeyboardButton(t["chart"])],
        [KeyboardButton(t["notify"])],
        [KeyboardButton(t["buy_stars"])],
        [KeyboardButton(t["wallet"])],
        [KeyboardButton(t["memland"])],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)


# ------------------ РАБОТА С БД ------------------

def has_db() -> bool:
    return bool(DATABASE_URL)


def get_conn():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL не задана")
    return psycopg2.connect(DATABASE_URL)


def init_db():
    if not DATABASE_URL:
        print("DATABASE_URL не задана — подписки отключены")
        return

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS subscribers (
                    user_id    BIGINT PRIMARY KEY,
                    lang       TEXT NOT NULL,
                    base_price NUMERIC,
                    active     BOOLEAN NOT NULL DEFAULT TRUE,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )
    print("DB: subscribers table ensured")


def subscribe_user_db(user_id: int, lang: str, base_price: float):
    if not has_db():
        return

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO subscribers (user_id, lang, base_price, active, created_at, updated_at)
                VALUES (%s, %s, %s, TRUE, NOW(), NOW())
                ON CONFLICT (user_id) DO UPDATE
                SET lang = EXCLUDED.lang,
                    base_price = EXCLUDED.base_price,
                    active = TRUE,
                    updated_at = NOW();
                """,
                (user_id, lang, base_price),
            )


def get_subscription(user_id: int):
    if not has_db():
        return None

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT user_id, lang, base_price, active FROM subscribers WHERE user_id = %s;",
                (user_id,),
            )
            row = cur.fetchone()
            if not row:
                return None

            return {
                "user_id": row[0],
                "lang": row[1],
                "base_price": float(row[2]) if row[2] is not None else None,
                "active": bool(row[3]),
            }


def unsubscribe_user_db(user_id: int):
    if not has_db():
        return

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE subscribers SET active = FALSE, updated_at = NOW() WHERE user_id = %s;",
                (user_id,),
            )


def get_active_subscribers():
    if not has_db():
        return []

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT user_id, lang, base_price FROM subscribers WHERE active = TRUE;"
            )
            rows = cur.fetchall()

    result = []
    for user_id, lang, base_price in rows:
        result.append(
            {
                "user_id": int(user_id),
                "lang": lang,
                "base_price": float(base_price) if base_price is not None else None,
            }
        )
    return result


def update_base_price(user_id: int, new_price: float):
    if not has_db():
        return
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE subscribers SET base_price = %s, updated_at = NOW() WHERE user_id = %s;",
                (new_price, user_id),
            )


# ------------------ ДАННЫЕ TON ------------------

def get_ton_price_usd() -> Optional[float]:
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


# ------------------ ГРАФИК TON ------------------

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
        0.01, -0.04, f"1 TON = {current_price:.3f} $", fontsize=12, color="#111827", ha="left"
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
            caption="[Binance](https://www.binance.com/referral/earn-together/refer2earn-usdc/claim?hl=en&ref=GRO_28502_1C1WM&utm_source=default)",
            parse_mode="Markdown",
        )
    except Exception as e:
        print("Chart error:", e)
        await context.bot.send_message(chat_id, text_chart_error(lang))


# ------------------ MEMELANDIA: ВСПОМОГАТЕЛЬНЫЕ ------------------

def fetch_memelandia() -> List[Dict[str, Any]]:
    """Тянем список монет Мемляндии."""
    try:
        r = requests.get(MEMELANDIA_URL, timeout=10)
        r.raise_for_status()
        data = r.json()
        # предполагаем, что основная масса в data["data"]
        items = data.get("data") or data.get("tokens") or []
        if not isinstance(items, list):
            return []
        return items
    except Exception as e:
        print("Memelandia fetch error:", e)
        return []


def format_change_with_emoji(value: float) -> str:
    """Подсветка + зелёный, - красный, через эмодзи."""
    emoji = "🟢" if value >= 0 else "🔴"
    sign = "+" if value >= 0 else ""
    return f"{emoji} {sign}{value:.1f}%"


def create_memecoin_chart_image(
    symbol: str,
    price: float,
    change_24h: float,
    change_7d: float,
    market_cap: float,
    holders: int,
) -> bytes:
    """Рисуем картинку: барчарт 24h/7d + краткая инфа."""
    plt.style.use("default")
    fig, ax = plt.subplots(figsize=(6, 4), dpi=200)

    fig.patch.set_facecolor("#0f172a")     # тёмный фон
    ax.set_facecolor("#020617")

    labels = ["24h", "7d"]
    values = [change_24h, change_7d]
    colors = [
        "#22c55e" if change_24h >= 0 else "#ef4444",
        "#22c55e" if change_7d >= 0 else "#ef4444",
    ]

    ax.bar(labels, values, color=colors, width=0.5)

    # линия 0 для наглядности
    ax.axhline(0, color="#64748b", linewidth=0.8)

    for i, v in enumerate(values):
        ax.text(
            i,
            v + (0.8 if v >= 0 else -0.8),
            f"{v:+.1f}%",
            ha="center",
            va="bottom" if v >= 0 else "top",
            color="white",
            fontsize=9,
        )

    ax.tick_params(colors="#e5e7eb")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#334155")
    ax.spines["bottom"].set_color("#334155")

    title = f"{symbol}\nprice: {price:.6f} $ | holders: {holders:,}\nmcap: {market_cap:,.0f} $"
    fig.suptitle(title, color="white", fontsize=10)

    fig.tight_layout(pad=2.0)

    buf = io.BytesIO()
    plt.savefig(buf, format="png", bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close()
    buf.seek(0)
    return buf.getvalue()


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

    # смена языка
    if data.startswith("lang_"):
        lang = data.split("_", 1)[1]  # en / ru / uk
        user_lang[user_id] = lang

        await query.message.reply_text(text_lang_confirm(lang))
        await send_price_and_chart(chat_id, lang, context)

        await context.bot.send_message(
            chat_id,
            text_menu_prompt(lang),
            reply_markup=footer_buttons(lang),
        )
        return

    # отписка от уведомлений
    if data == "unsubscribe":
        lang = get_user_language(user_id)
        if has_db():
            unsubscribe_user_db(user_id)
            await query.message.reply_text(text_unsubscribed(lang))
        else:
            await query.message.reply_text(text_subscriptions_disabled(lang))
        return

    # график конкретной монеты Мемляндии
    if data.startswith("memcoin_"):
        try:
            index = int(data.split("_", 1)[1])
        except ValueError:
            return

        lang = get_user_language(user_id)

        items = fetch_memelandia()
        if not items or index < 0 or index >= len(items):
            await query.message.reply_text("Не удалось получить данные Мемляндии 🙈")
            return

        coin = items[index]
        symbol = str(coin.get("symbol") or coin.get("name") or "COIN")
        price = float(coin.get("price") or 0.0)
        ch24 = float(coin.get("price_change_24h") or 0.0)
        ch7 = float(coin.get("price_change_d7") or 0.0)
        mcap = float(coin.get("market_cap") or 0.0)
        holders = int(coin.get("holders") or 0)

        img = create_memecoin_chart_image(symbol, price, ch24, ch7, mcap, holders)

        caption = (
            f"{symbol}\n"
            f"price: {price:.6f} $\n"
            f"24h: {format_change_with_emoji(ch24)}, 7d: {format_change_with_emoji(ch7)}\n"
            f"holders: {holders:,}\n"
            f"mcap: {mcap:,.0f} $"
        )

        await context.bot.send_photo(
            chat_id=chat_id,
            photo=img,
            caption=caption,
        )
        return


async def footer_buttons_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_user_language(user_id)
    t = get_button_texts(lang)
    text = (update.message.text or "").strip()

    # Курс
    if text == t["price"]:
        p = get_ton_price_usd()
        if p is not None:
            await update.message.reply_text(text_price_ok(lang, p))
        else:
            await update.message.reply_text(text_price_error(lang))
        return

    # График
    if text == t["chart"]:
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
        return

    # Уведомления
    if text == t["notify"]:
        if not has_db():
            await update.message.reply_text(text_subscriptions_disabled(lang))
            return

        current_price = get_ton_price_usd()
        if current_price is None:
            await update.message.reply_text(text_price_error(lang))
            return

        sub = get_subscription(user_id)
        if sub and sub["active"]:
            await update.message.reply_text(text_already_subscribed(lang))
        else:
            subscribe_user_db(user_id, lang, current_price)
            await update.message.reply_text(
                text_subscribed(lang, current_price),
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton(unsubscribe_button_text(lang), callback_data="unsubscribe")]]
                ),
            )
        return

    # Купить Stars
    if text == t["buy_stars"]:
        if lang == "en":
            msg = "Open TON Stars: https://tonstars.io"
        elif lang == "uk":
            msg = "Відкрийте TON Stars: https://tonstars.io"
        else:
            msg = "Откройте TON Stars: https://tonstars.io"
        await update.message.reply_text(msg)
        return

    # Кошелёк
    if text == t["wallet"]:
        if lang == "en":
            msg = "Open wallet: http://t.me/send?start=r-71wfg"
        elif lang == "uk":
            msg = "Відкрити гаманець: http://t.me/send?start=r-71wfg"
        else:
            msg = "Открыть кошелёк: http://t.me/send?start=r-71wfg"
        await update.message.reply_text(msg)
        return

    # Мемляндия
    if text == t["memland"]:
        items = fetch_memelandia()
        if not items:
            await update.message.reply_text("Не могу получить данные Мемляндии 🙈")
            return

        top = items[:5]

        lines = ["ТОП-5 Мемляндии 🦄", ""]
        for idx, coin in enumerate(top, start=1):
            symbol = str(coin.get("symbol") or coin.get("name") or f"#{idx}")
            price = float(coin.get("price") or 0.0)
            ch24 = float(coin.get("price_change_24h") or 0.0)
            ch7 = float(coin.get("price_change_d7") or 0.0)
            holders = int(coin.get("holders") or 0)
            mcap = float(coin.get("market_cap") or 0.0)

            lines.append(
                f"{idx}. {symbol}\n"
                f"price: {price:.6f} $\n"
                f"24h: {format_change_with_emoji(ch24)}, 7d: {format_change_with_emoji(ch7)}\n"
                f"holders: {holders:,}\n"
                f"mcap: {mcap:,.0f} $\n"
            )

        text_out = "\n".join(lines).rstrip()

        keyboard = [
            [
                InlineKeyboardButton("1", callback_data="memcoin_0"),
                InlineKeyboardButton("2", callback_data="memcoin_1"),
                InlineKeyboardButton("3", callback_data="memcoin_2"),
                InlineKeyboardButton("4", callback_data="memcoin_3"),
                InlineKeyboardButton("5", callback_data="memcoin_4"),
            ]
        ]

        await update.message.reply_text(
            text_out + "\nНажми на номер, чтобы увидеть график 24h/7d 📊",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return


# отдельные команды (если кто-то захочет писать руками)

async def price_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_user_language(user_id)
    p = get_ton_price_usd()
    if p:
        await update.message.reply_text(text_price_ok(lang, p))
    else:
        await update.message.reply_text(text_price_error(lang))


async def chart_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
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


# ------------------ ФОНОВЫЙ ДЖОБ ------------------

async def check_price_job(context: ContextTypes.DEFAULT_TYPE):
    if not has_db():
        return

    current_price = get_ton_price_usd()
    if current_price is None:
        return

    subscribers = get_active_subscribers()
    if not subscribers:
        return

    to_update: list[int] = []

    for sub in subscribers:
        base_price = sub["base_price"]
        if base_price is None:
            continue

        diff = abs(current_price - base_price) / base_price
        if diff >= 0.10:
            diff_percent = diff * 100.0
            lang = sub["lang"]
            user_id = sub["user_id"]

            text = text_price_alert(lang, base_price, current_price, diff_percent)
            try:
                await context.bot.send_message(chat_id=user_id, text=text)
                to_update.append(user_id)
            except Exception as e:
                print(f"Notify send error for {user_id}:", e)

    for user_id in to_update:
        update_base_price(user_id, current_price)


# ------------------ MAIN ------------------

def main():
    init_db()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("price", price_cmd))
    app.add_handler(CommandHandler("chart", chart_cmd))

    app.add_handler(CallbackQueryHandler(callback_handler))

    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, footer_buttons_handler)
    )

    if app.job_queue is not None and has_db():
        app.job_queue.run_repeating(check_price_job, interval=300, first=60)
    else:
        print("Job queue or DB not available — background notifications disabled")

    app.run_polling()


if __name__ == "__main__":
    main()
