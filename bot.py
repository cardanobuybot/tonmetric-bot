import os
import io
from datetime import datetime
from decimal import Decimal
from typing import Optional, List, Dict, Any

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
CRYPTOPAY_API_TOKEN = os.getenv("CRYPTOPAY_API_TOKEN")
                      or os.getenv("CRYPTOBOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не задан в переменных окружения")

if not CRYPTOPAY_API_TOKEN:
    print("WARN: CRYPTOPAY_API_TOKEN не задан, покупка тикетов не будет работать")

# ------------------ BINANCE API ------------------

BINANCE_TICKER = "https://api.binance.com/api/v3/ticker/price"
BINANCE_KLINES = "https://api.binance.com/api/v3/klines"
SYMBOL = "TONUSDT"

# ------------------ MEMELANDIA API ------------------

MEMELANDIA_API_URL = "https://memelandia.okhlopkov.com/api/leaderboard"

# ------------------ CryptoPay API ------------------

CRYPTOPAY_API_URL = "https://pay.crypt.bot/api/"

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


# -------- ТЕКСТЫ ДЛЯ МЕМЛЯНДИИ --------

def text_memlandia_header(lang: str) -> str:
    if lang == "en":
        return "Top-5 Memelandia 🦄"
    elif lang == "uk":
        return "ТОП-5 Мемляндії 🦄"
    else:
        return "ТОП-5 Мемляндии 🦄"


def text_memlandia_error(lang: str) -> str:
    if lang == "en":
        return "Can't get Memelandia data now 🙈"
    elif lang == "uk":
        return "Не вдалось отримати дані Мемляндії 🙈"
    else:
        return "Не удалось получить данные Мемляндии 🙈"


# ------------------ ТЕКСТЫ КНОПОК ------------------

BUTTON_TEXTS = {
    "ru": {
        "price": "Курс",
        "chart": "График",
        "notify": "Уведомления",
        "wallet": "Кошелёк",
        "memland": "Мемляндия🦄",
        "buy_tickets": "Купить тикеты 🎫",
        "my_tickets": "Мои тикеты",
        "leaderboard": "🏆",
        "ref_link": "Реф. ссылка",
    },
    "en": {
        "price": "Rate",
        "chart": "Chart",
        "notify": "Notifications",
        "wallet": "Wallet",
        "memland": "Memelandia🦄",
        "buy_tickets": "Buy tickets 🎫",
        "my_tickets": "My tickets",
        "leaderboard": "🏆",
        "ref_link": "Ref. link",
    },
    "uk": {
        "price": "Курс",
        "chart": "Графік",
        "notify": "Сповіщення",
        "wallet": "Гаманець",
        "memland": "Мемляндія🦄",
        "buy_tickets": "Купити квитки 🎫",
        "my_tickets": "Мої квитки",
        "leaderboard": "🏆",
        "ref_link": "Реф. посилання",
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
        [KeyboardButton(t["wallet"])],
        [KeyboardButton(t["memland"])],
        [KeyboardButton(t["buy_tickets"])],
        [KeyboardButton(t["my_tickets"]), KeyboardButton(t["leaderboard"]), KeyboardButton(t["ref_link"])],
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
        print("DATABASE_URL не задана — подписки и тикеты отключены")
        return

    with get_conn() as conn:
        with conn.cursor() as cur:
            # подписки по цене
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
            # тикеты и статистика
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS ticket_users (
                    user_id      BIGINT PRIMARY KEY,
                    total_ton    NUMERIC NOT NULL DEFAULT 0,
                    total_tickets INTEGER NOT NULL DEFAULT 0,
                    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS ticket_invoices (
                    invoice_id   BIGINT PRIMARY KEY,
                    user_id      BIGINT NOT NULL,
                    tickets      INTEGER NOT NULL,
                    amount_ton   NUMERIC NOT NULL,
                    status       TEXT NOT NULL,
                    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )

    print("DB: tables ensured")


# --- подписки по цене

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


# --- тикеты

def add_tickets_to_user(user_id: int, tickets: int, amount_ton: float):
    if not has_db():
        return

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO ticket_users (user_id, total_ton, total_tickets, created_at, updated_at)
                VALUES (%s, %s, %s, NOW(), NOW())
                ON CONFLICT (user_id) DO UPDATE
                SET total_ton = ticket_users.total_ton + EXCLUDED.total_ton,
                    total_tickets = ticket_users.total_tickets + EXCLUDED.total_tickets,
                    updated_at = NOW();
                """,
                (user_id, Decimal(str(amount_ton)), tickets),
            )


def save_invoice(invoice_id: int, user_id: int, tickets: int, amount_ton: float, status: str):
    if not has_db():
        return
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO ticket_invoices (invoice_id, user_id, tickets, amount_ton, status)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (invoice_id) DO UPDATE
                SET status = EXCLUDED.status,
                    updated_at = NOW();
                """,
                (invoice_id, user_id, tickets, Decimal(str(amount_ton)), status),
            )


def mark_invoice_paid(invoice_id: int):
    if not has_db():
        return
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE ticket_invoices SET status = 'paid', updated_at = NOW() WHERE invoice_id = %s;",
                (invoice_id,),
            )


def get_user_ticket_stats(user_id: int) -> Dict[str, float]:
    if not has_db():
        return {"tickets": 0, "total_ton": 0.0}

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT total_tickets, total_ton
                FROM ticket_users
                WHERE user_id = %s;
                """,
                (user_id,),
            )
            row = cur.fetchone()
            if not row:
                return {"tickets": 0, "total_ton": 0.0}

            tickets, total_ton = row
            return {
                "tickets": int(tickets),
                "total_ton": float(total_ton or 0),
            }


def get_leaderboard(limit: int = 100) -> List[Dict[str, Any]]:
    if not has_db():
        return []

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT user_id, total_tickets, total_ton
                FROM ticket_users
                WHERE total_ton > 0
                ORDER BY total_ton DESC
                LIMIT %s;
                """,
                (limit,),
            )
            rows = cur.fetchall()

    result = []
    for user_id, total_tickets, total_ton in rows:
        result.append(
            {
                "user_id": int(user_id),
                "tickets": int(total_tickets),
                "total_ton": float(total_ton or 0),
            }
        )
    return result


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


# ------------------ MEMELANDIA HELPERS ------------------

def fetch_memelandia_top(limit: int = 5):
    try:
        r = requests.get(MEMELANDIA_API_URL, timeout=10)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print("Memelandia API error:", e)
        return None

    items = None

    if isinstance(data, list):
        items = data

    if items is None and isinstance(data, dict):
        for key in ("data", "items", "leaderboard", "tokens"):
            if isinstance(data.get(key), list):
                items = data[key]
                break
        if items is None:
            for v in data.values():
                if isinstance(v, list):
                    items = v
                    break

    if not items:
        print("Memelandia: no items in response")
        return None

    if any(isinstance(x, dict) and "rank" in x for x in items):
        items = sorted(
            items,
            key=lambda x: int(x.get("rank") or 10**9),
        )
    else:
        items = sorted(
            items,
            key=lambda x: float(x.get("market_cap") or 0),
            reverse=True,
        )

    top = items[:limit]
    result = []
    for i, coin in enumerate(top, start=1):
        if not isinstance(coin, dict):
            continue

        symbol = coin.get("symbol") or "?"
        price = float(coin.get("price") or 0)

        change_24 = (
            coin.get("price_change_24h")
            or coin.get("price_change_d24")
            or coin.get("price_change_d1")
            or 0
        )
        change_7d = coin.get("price_change_d7") or coin.get("price_change_7d") or 0

        holders = coin.get("holders")
        market_cap = coin.get("market_cap")

        try:
            change_24 = float(change_24)
        except Exception:
            change_24 = 0.0
        try:
            change_7d = float(change_7d)
        except Exception:
            change_7d = 0.0

        try:
            holders = int(holders) if holders is not None else None
        except Exception:
            holders = None

        try:
            market_cap = float(market_cap) if market_cap is not None else None
        except Exception:
            market_cap = None

        result.append(
            {
                "index": i,
                "symbol": symbol,
                "price": price,
                "change_24": change_24,
                "change_7d": change_7d,
                "holders": holders,
                "market_cap": market_cap,
            }
        )

    return result


def format_memelandia_top(lang: str, coins: list[dict]) -> str:
    header = text_memlandia_header(lang)
    lines = [header, ""]

    for c in coins:
        idx = c["index"]
        sym = c["symbol"]
        price = c["price"]

        ch24 = c["change_24"]
        ch7 = c["change_7d"]
        holders = c["holders"]
        mc = c["market_cap"]

        def fmt_pct(x: float) -> str:
            sign = "+" if x > 0 else ""
            return f"{sign}{x:.1f}%"

        line = f"{idx}. {sym}\n"
        line += f"   price: {price:.6f} $\n"
        line += f"   24h: {fmt_pct(ch24)}, 7d: {fmt_pct(ch7)}\n"

        if holders is not None:
            line += f"   holders: {holders}\n"
        if mc is not None and mc > 0:
            line += f"   mcap: {mc:,.0f} $\n"

        lines.append(line.rstrip())

    return "\n".join(lines)


def create_memelandia_bar_chart(coins: list[dict]) -> bytes:
    labels = [c["symbol"] for c in coins]
    values = [c["change_24"] for c in coins]

    colors = ["#EF4444" if v < 0 else "#22C55E" for v in values]

    fig, ax = plt.subplots(figsize=(9, 5), dpi=250)
    fig.patch.set_facecolor("#FFFFFF")
    ax.set_facecolor("#F5FAFF")

    positions = range(len(labels))
    ax.barh(positions, values, color=colors)
    ax.set_yticks(positions)
    ax.set_yticklabels(labels)

    ax.axvline(0, color="#9CA3AF", linewidth=0.8)
    ax.set_xlabel("24h %")
    ax.set_title("Memelandia Top-5 — 24h change")

    for i, v in enumerate(values):
        ax.text(v + (0.3 if v >= 0 else -0.3), i, f"{v:+.1f}%", va="center",
                ha="left" if v >= 0 else "right", fontsize=8)

    fig.tight_layout()

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


# ------------------ CryptoPay helpers ------------------

def cryptopay_request(method: str, data: Optional[dict] = None) -> dict:
    if not CRYPTOPAY_API_TOKEN:
        raise RuntimeError("CRYPTOPAY_API_TOKEN not set")

    url = CRYPTOPAY_API_URL + method
    headers = {
        "Crypto-Pay-API-Token": CRYPTOPAY_API_TOKEN,
        "Content-Type": "application/json",
    }
    try:
        resp = requests.post(url, json=data or {}, headers=headers, timeout=15)
        j = resp.json()
    except Exception as e:
        print("CryptoPay request error:", e)
        raise

    if not j.get("ok"):
        raise RuntimeError(f"CryptoPay API error: {j}")
    return j["result"]


def create_ticket_invoice_api(user_id: int, tickets: int, amount_ton: float) -> dict:
    payload = f"user_{user_id}_tickets_{tickets}"
    data = {
        "asset": "TON",
        "amount": str(amount_ton),
        "description": "Покупка тикетов TON Metric",
        "hidden_message": "Спасибо за поддержку пампа 🔥",
        "payload": payload,
    }
    result = cryptopay_request("createInvoice", data)
    return result


def get_invoice_api(invoice_id: int) -> dict:
    data = {"invoice_ids": [invoice_id]}
    res = cryptopay_request("getInvoices", data)
    if isinstance(res, list) and res:
        return res[0]
    raise RuntimeError("Invoice not found in CryptoPay")


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
        lang = data.split("_", 1)[1]
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

    # проверка оплаты тикетов
    if data.startswith("check_invoice:"):
        lang = get_user_language(user_id)
        invoice_id_str = data.split(":", 1)[1]
        try:
            invoice_id = int(invoice_id_str)
        except ValueError:
            await query.message.reply_text("Некорректный ID инвойса 🙈")
            return

        if not has_db():
            await query.message.reply_text("База данных недоступна 🙈")
            return

        try:
            invoice = get_invoice_api(invoice_id)
        except Exception as e:
            print("get_invoice_api error:", e)
            await query.message.reply_text("Не удалось проверить оплату 🙈")
            return

        status = invoice.get("status")
        amount = float(invoice.get("amount") or 0)
        asset = invoice.get("asset")

        if status != "paid":
            await query.message.reply_text("Пока не оплачено. Попробуй через минуту ещё раз.")
            return

        # проверяем, не зачисляли ли уже
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT status, user_id, tickets, amount_ton FROM ticket_invoices WHERE invoice_id = %s;",
                    (invoice_id,),
                )
                row = cur.fetchone()

        if row and row[0] == "paid":
            await query.message.reply_text("Этот счёт уже был зачислен ✅")
            return

        # считаем, что 1 TON = 1 тикет
        tickets = int(round(amount))

        # обновляем БД
        save_invoice(invoice_id, user_id, tickets, amount, "paid")
        add_tickets_to_user(user_id, tickets, amount)
        await query.message.reply_text(f"Оплата получена ✅\nТебе начислено: {tickets} тикетов.")

        stats = get_user_ticket_stats(user_id)
        await query.message.reply_text(
            f"Твои тикеты: {stats['tickets']}\nВсего куплено: {stats['total_ton']:.2f} TON"
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

    # Кошелёк (твоя рефка на CryptoBot / Tonkeeper — как было)
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
        top = fetch_memelandia_top(limit=5)
        if not top:
            await update.message.reply_text(text_memlandia_error(lang))
            return

        msg = format_memelandia_top(lang, top)
        await update.message.reply_text(msg)

        # картинка
        try:
            img = create_memelandia_bar_chart(top)
            await update.message.reply_photo(img, caption="Top-5 Memelandia — 24h %")
        except Exception as e:
            print("Memelandia chart error:", e)
        return

    # Купить тикеты
    if text == t["buy_tickets"]:
        if not (has_db() and CRYPTOPAY_API_TOKEN):
            await update.message.reply_text("Покупка тикетов временно недоступна 🙈")
            return

        tickets = 1
        amount_ton = 1.0

        try:
            invoice = create_ticket_invoice_api(user_id, tickets, amount_ton)
        except Exception as e:
            print("create_ticket_invoice_api error:", e)
            await update.message.reply_text("Не удалось создать счёт 🙈")
            return

        invoice_id = int(invoice["invoice_id"])
        pay_url = invoice["pay_url"]
        status = invoice["status"]

        save_invoice(invoice_id, user_id, tickets, amount_ton, status)

        text_invoice = (
            "Счёт создан ✅\n\n"
            f"Сумма: {amount_ton:.2f} TON\n"
            f"Тикетов: {tickets}\n\n"
            "После оплаты нажми «Проверить оплату»."
        )

        kb = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("Оплатить в CryptoBot", url=pay_url),
                ],
                [
                    InlineKeyboardButton("Проверить оплату", callback_data=f"check_invoice:{invoice_id}"),
                ],
            ]
        )

        await update.message.reply_text(text_invoice, reply_markup=kb)
        return

    # Мои тикеты
    if text == t["my_tickets"]:
        stats = get_user_ticket_stats(user_id)
        await update.message.reply_text(
            f"Твои тикеты: {stats['tickets']}\nВсего куплено: {stats['total_ton']:.2f} TON"
        )
        return

    # Лидерборд 🏆
    if text == t["leaderboard"]:
        await top_cmd(update, context)
        return

    # Реф. ссылка
    if text == t["ref_link"]:
        me = await context.bot.get_me()
        username = me.username
        ref_url = f"https://t.me/{username}?start={user_id}"
        await update.message.reply_text(f"Твоя реф. ссылка:\n{ref_url}")
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


async def my_tickets_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    stats = get_user_ticket_stats(user_id)
    await update.message.reply_text(
        f"Твои тикеты: {stats['tickets']}\nВсего куплено: {stats['total_ton']:.2f} TON"
    )


async def buy_tickets_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # просто продублируем поведение кнопки
    fake_update = update
    await footer_buttons_handler(fake_update, context)


async def ref_link_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    me = await context.bot.get_me()
    username = me.username
    ref_url = f"https://t.me/{username}?start={user_id}"
    await update.message.reply_text(f"Твоя реф. ссылка:\n{ref_url}")


async def top_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lb = get_leaderboard(limit=100)
    if not lb:
        await update.message.reply_text("Пока ещё никто не купил тикеты.")
        return

    lines = ["🏆 Лидерборд по тикетам:", ""]
    for i, row in enumerate(lb, start=1):
        uid = row["user_id"]
        tickets = row["tickets"]
        total_ton = row["total_ton"]
        you = ""
        if update.effective_user and uid == update.effective_user.id:
            you = " (ты)"
        lines.append(
            f"{i}. ID {uid}{you}\n"
            f"   тикеты: {tickets}, всего куплено: {total_ton:.2f} TON"
        )

    await update.message.reply_text("\n".join(lines))


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
    app.add_handler(CommandHandler("mytickets", my_tickets_cmd))
    app.add_handler(CommandHandler("buytickets", buy_tickets_cmd))
    app.add_handler(CommandHandler("reflink", ref_link_cmd))
    app.add_handler(CommandHandler("top", top_cmd))

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
