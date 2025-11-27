import os
import io
from datetime import datetime
from decimal import Decimal

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
CRYPTOBOT_TOKEN = os.getenv("CRYPTOBOT_TOKEN")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не задан в переменных окружения")

# ------------------ BINANCE API ------------------

BINANCE_TICKER = "https://api.binance.com/api/v3/ticker/price"
BINANCE_KLINES = "https://api.binance.com/api/v3/klines"
SYMBOL = "TONUSDT"

# ------------------ MEMELANDIA API ------------------

MEMELANDIA_API_URL = "https://memelandia.okhlopkov.com/api/leaderboard"

# ------------------ CRYPTOBOT ------------------

CRYPTOBOT_API_URL = "https://pay.crypt.bot/api"
REF_PERCENT = 0.10  # 10% тикетов рефералу
TICKET_RATE = 1.0   # 1 TON = 1 тикет

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
        # "buy_stars": "Купить Stars ⭐",  # временно не используем
        "wallet": "Кошелёк",
        "memland": "Мемляндия🦄",
        "buy_tickets": "Купить тикеты 🎟",
        "my_tickets": "Мои тикеты",
        "ref_link": "Реф. ссылка",
    },
    "en": {
        "price": "Rate",
        "chart": "Chart",
        "notify": "Notifications",
        "wallet": "Wallet",
        "memland": "Memlandia🦄",
        "buy_tickets": "Buy tickets 🎟",
        "my_tickets": "My tickets",
        "ref_link": "Ref link",
    },
    "uk": {
        "price": "Курс",
        "chart": "Графік",
        "notify": "Сповіщення",
        "wallet": "Гаманець",
        "memland": "Мемляндія🦄",
        "buy_tickets": "Купити тікети 🎟",
        "my_tickets": "Мої тікети",
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
        [KeyboardButton(t["my_tickets"]), KeyboardButton(t["ref_link"])],
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
        print("DATABASE_URL не задана — подписки/ревардка отключены")
        return

    with get_conn() as conn:
        with conn.cursor() as cur:
            # Подписчики на курс TON
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

            # Пользователи ревард-программы
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS reward_users (
                    user_id      BIGINT PRIMARY KEY,
                    referrer_id  BIGINT,
                    tickets      NUMERIC NOT NULL DEFAULT 0,
                    total_ton    NUMERIC NOT NULL DEFAULT 0,
                    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )

            # Инвойсы CryptoBot
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS reward_invoices (
                    id           SERIAL PRIMARY KEY,
                    invoice_id   BIGINT UNIQUE NOT NULL,
                    user_id      BIGINT NOT NULL,
                    amount_ton   NUMERIC NOT NULL,
                    tickets      NUMERIC NOT NULL,
                    status       TEXT NOT NULL,
                    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )

    print("DB: tables ensured")


# ---- подписки на курс (как было) ----

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


def create_memelandia_chart(coins: list[dict]) -> bytes:
    labels = [c["symbol"] for c in coins]
    values = [c["change_24"] for c in coins]

    fig, ax = plt.subplots(figsize=(9, 5), dpi=250)
    fig.patch.set_facecolor("#FFFFFF")
    ax.set_facecolor("#F9FAFB")

    y_pos = range(len(labels))
    colors = ["#10B981" if v >= 0 else "#EF4444" for v in values]

    ax.barh(y_pos, values, tick_label=labels, color=colors)
    ax.axvline(0, color="#9CA3AF", linewidth=0.8)

    for i, v in enumerate(values):
        ax.text(
            v + (0.3 if v >= 0 else -0.3),
            i,
            f"{v:+.1f}%",
            va="center",
            ha="left" if v >= 0 else "right",
            fontsize=8,
        )

    ax.set_xlabel("24h %")
    ax.set_title("Memelandia Top-5 — 24h change")

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


# ------------------ CRYPTOBOT HELPERS ------------------

def cryptobot_headers():
    if not CRYPTOBOT_TOKEN:
        raise RuntimeError("CRYPTOBOT_TOKEN not set")
    return {
        "Crypto-Pay-API-Token": CRYPTOBOT_TOKEN,
        "Content-Type": "application/json",
    }


def create_invoice_ton(amount_ton: float, payload: str) -> dict | None:
    try:
        r = requests.post(
            f"{CRYPTOBOT_API_URL}/createInvoice",
            headers=cryptobot_headers(),
            json={
                "asset": "TON",
                "amount": str(amount_ton),
                "payload": payload,
            },
            timeout=10,
        )
        data = r.json()
        if not data.get("ok"):
            print("CryptoBot createInvoice error:", data)
            return None
        return data["result"]
    except Exception as e:
        print("CryptoBot error:", e)
        return None


def get_invoice(invoice_id: int) -> dict | None:
    try:
        r = requests.post(
            f"{CRYPTOBOT_API_URL}/getInvoices",
            headers=cryptobot_headers(),
            json={"invoice_ids": [invoice_id]},
            timeout=10,
        )
        data = r.json()
        if not data.get("ok"):
            print("CryptoBot getInvoices error:", data)
            return None
        items = data["result"]["items"]
        return items[0] if items else None
    except Exception as e:
        print("CryptoBot error:", e)
        return None


# ------------------ ХЕНДЛЕРЫ ------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id

    # язык по умолчанию
    user_lang[user_id] = "ru"

    # рефералка: /start 123456789
    referrer_id = None
    if context.args:
        try:
            referrer_id = int(context.args[0])
            if referrer_id == user_id:
                referrer_id = None
        except Exception:
            referrer_id = None

    # записываем пользователя в reward_users
    if has_db():
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO reward_users (user_id, referrer_id)
                    VALUES (%s, %s)
                    ON CONFLICT (user_id) DO NOTHING;
                    """,
                    (user_id, referrer_id),
                )

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

    # проверка инвойса CryptoBot
    if data.startswith("check_invoice:"):
        _, inv_id_str = data.split(":", 1)
        try:
            invoice_id = int(inv_id_str)
        except ValueError:
            await query.message.reply_text("Некорректный инвойс.")
            return

        inv = get_invoice(invoice_id)
        if not inv:
            await query.message.reply_text("Не удалось получить статус оплаты 🙈")
            return

        status = inv.get("status")
        if status != "paid":
            await query.message.reply_text("Пока не оплачено. Попробуй позже.")
            return

        tickets = 0
        ref_award = 0
        amount_ton = 0.0

        if has_db():
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT user_id, amount_ton, tickets, status FROM reward_invoices WHERE invoice_id = %s;",
                        (invoice_id,),
                    )
                    row = cur.fetchone()

                    if not row:
                        await query.message.reply_text("Инвойс не найден в базе.")
                        return

                    db_user_id, amount_ton, tickets, db_status = row
                    if db_status == "paid":
                        await query.message.reply_text("Оплата уже учтена ✅")
                        return

                    # обновляем тикеты пользователя
                    cur.execute(
                        """
                        UPDATE reward_users
                        SET tickets = tickets + %s,
                            total_ton = total_ton + %s
                        WHERE user_id = %s
                        RETURNING referrer_id;
                        """,
                        (tickets, amount_ton, db_user_id),
                    )
                    res = cur.fetchone()
                    referrer_id = res[0] if res else None

                    # помечаем инвойс как оплаченный
                    cur.execute(
                        "UPDATE reward_invoices SET status = 'paid' WHERE invoice_id = %s;",
                        (invoice_id,),
                    )

                    # тикеты рефералу
                    if referrer_id:
                        ref_award = tickets * REF_PERCENT
                        cur.execute(
                            "UPDATE reward_users SET tickets = tickets + %s WHERE user_id = %s;",
                            (ref_award, referrer_id),
                        )

        msg = f"Оплата получена ✅\nТебе начислено: {tickets:.0f} тикетов."
        if ref_award:
            msg += f"\nТвоему рефералу начислено: {ref_award:.0f} тикетов."

        await query.message.reply_text(msg)
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
        top = fetch_memelandia_top(limit=5)
        if not top:
            await update.message.reply_text(text_memlandia_error(lang))
            return

        msg = format_memelandia_top(lang, top)

        # график 24h
        try:
            img = create_memelandia_chart(top)
            await update.message.reply_photo(img, caption=msg)
        except Exception as e:
            print("Memelandia chart error:", e)
            await update.message.reply_text(msg)
        return

    # Купить тикеты (через CryptoBot)
    if text == t["buy_tickets"]:
        if not CRYPTOBOT_TOKEN:
            await update.message.reply_text("Оплата временно недоступна 🙈")
            return

        amount_ton = 1.0  # фикс: 1 TON
        tickets = amount_ton * TICKET_RATE

        payload = f"user:{user_id}"
        inv = create_invoice_ton(amount_ton, payload)
        if not inv:
            await update.message.reply_text("Не удалось создать счёт в CryptoBot 🙈")
            return

        invoice_id = inv["invoice_id"]
        pay_url = inv["pay_url"]

        if has_db():
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO reward_invoices (invoice_id, user_id, amount_ton, tickets, status)
                        VALUES (%s, %s, %s, %s, 'pending')
                        ON CONFLICT (invoice_id) DO NOTHING;
                        """,
                        (invoice_id, user_id, amount_ton, tickets),
                    )

        keyboard = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("Оплатить в CryptoBot", url=pay_url)],
                [InlineKeyboardButton("Проверить оплату", callback_data=f"check_invoice:{invoice_id}")],
            ]
        )

        await update.message.reply_text(
            f"Счёт создан ✅\n\n"
            f"Сумма: {amount_ton:.2f} TON\n"
            f"Тикетов: {tickets:.0f}\n\n"
            f"После оплаты нажми «Проверить оплату».",
            reply_markup=keyboard,
        )
        return

    # Мои тикеты
    if text == t["my_tickets"]:
        if not has_db():
            await update.message.reply_text("Хранилище тикетов временно недоступно 🙈")
            return

        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT tickets, total_ton FROM reward_users WHERE user_id = %s;",
                    (user_id,),
                )
                row = cur.fetchone()

        if not row:
            await update.message.reply_text("У тебя пока нет тикетов.")
            return

        tickets, total_ton = row
        await update.message.reply_text(
            f"Твои тикеты: {float(tickets):.0f}\nВсего куплено: {float(total_ton):.2f} TON"
        )
        return

    # Реф. ссылка
    if text == t["ref_link"]:
        link = f"https://t.me/{context.bot.username}?start={user_id}"
        await update.message.reply_text(f"Твоя реф. ссылка:\n\n{link}")
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

    # уведомления по курсу отключатся сами, если нет DATABASE_URL или JobQueue
    if app.job_queue is not None and has_db():
        app.job_queue.run_repeating(check_price_job, interval=300, first=60)
    else:
        print("Job queue or DB not available — background notifications disabled")

    app.run_polling()


if __name__ == "__main__":
    main()
