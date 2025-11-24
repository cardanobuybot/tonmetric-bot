import os
import io
from datetime import datetime

import requests
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from bs4 import BeautifulSoup

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
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не задан в переменных окружения")

# ------------------ CONST ------------------

# Binance API
BINANCE_TICKER = "https://api.binance.com/api/v3/ticker/price"
BINANCE_KLINES = "https://api.binance.com/api/v3/klines"
SYMBOL = "TONUSDT"

# Memlandia / Ton Meme Republic leaderboard page
MEMELANDIA_URL = "https://www.tonmemerepublic.com/leaderboard"

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
    # во всех языках формат одинаковый — текст меняется чуть-чуть выше/ниже по желанию
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


def text_memland_header(lang: str) -> str:
    if lang == "en":
        return "🏆 Memlandia Top-5"
    elif lang == "uk":
        return "🏆 ТОП-5 Мемляндії"
    else:
        return "🏆 ТОП-5 Мемляндии"


def text_memland_error(lang: str) -> str:
    if lang == "en":
        return "Can't get Memlandia Top-5 🙈"
    elif lang == "uk":
        return "Не вдалося отримати ТОП-5 Мемляндії 🙈"
    else:
        return "Не удалось получить ТОП-5 Мемляндии 🙈"


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


# ------------------ TON DATA ------------------

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
            print("Binance kline error:", klines)
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


# ------------------ MEMLANDIA ------------------

def fetch_memlandia_top5():
    """
    Пытаемся вытащить топ-5 из таблицы на странице.
    Если верстка другая — правишь этот кусок под реальную структуру.
    Возвращаем список словарей:
    { "name": str, "price": str, "change": str }
    """
    try:
        r = requests.get(MEMELANDIA_URL, timeout=10)
        r.raise_for_status()
    except Exception as e:
        print("Memlandia request error:", e)
        return None

    try:
        soup = BeautifulSoup(r.text, "html.parser")

        # пример: ищем первую таблицу на странице
        table = soup.find("table")
        if not table:
            print("Memlandia: no <table> found")
            return None

        rows = table.find("tbody").find_all("tr") if table.find("tbody") else table.find_all("tr")
        rows = rows[:5]

        result = []
        for row in rows:
            cols = [c.get_text(strip=True) for c in row.find_all("td")]
            if len(cols) < 3:
                # ожидаем как минимум: [Name, Price, Change]
                continue
            name = cols[0]
            price = cols[1]
            change = cols[2]
            result.append(
                {
                    "name": name,
                    "price": price,
                    "change": change,
                }
            )

        if not result:
            print("Memlandia: parsed 0 rows")
            return None

        return result

    except Exception as e:
        print("Memlandia parse error:", e)
        return None


def format_memlandia_line(idx: int, name: str, price: str, change: str) -> str:
    """
    Делаем стрелочку и зелёный/красный кружок по знаку change.
    change может быть в формате "+12.3%" или "-4.5%" и т.п.
    """
    ch_clean = change.replace(" ", "")
    arrow = "🟢"  # по умолчанию плюс
    if ch_clean.startswith("-"):
        arrow = "🔴"

    return f"{idx}. {name}\n   {arrow} {change}   {price}"


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


# ------------------ ХЕНДЛЕРЫ ------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_lang[user_id] = "ru"  # дефолт до выбора

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

        await query.message.reply_text(text_lang_confirm(lang))
        await send_price_and_chart(chat_id, lang, context)

        # показать меню с кнопками
        await context.bot.send_message(
            chat_id,
            text_menu_prompt(lang),
            reply_markup=footer_buttons(lang),
        )


async def footer_buttons_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_user_language(user_id)
    t = get_button_texts(lang)
    text_msg = (update.message.text or "").strip()

    # Курс
    if text_msg == t["price"]:
        p = get_ton_price_usd()
        if p is not None:
            await update.message.reply_text(text_price_ok(lang, p))
        else:
            await update.message.reply_text(text_price_error(lang))
        return

    # График
    if text_msg == t["chart"]:
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

    # Уведомления — пока заглушка, без БД/cron
    if text_msg == t["notify"]:
        if lang == "en":
            msg = "Price notifications will be available later 🔔"
        elif lang == "uk":
            msg = "Сповіщення про ціну будуть доступні пізніше 🔔"
        else:
            msg = "Уведомления о цене будут доступны позже 🔔"
        await update.message.reply_text(msg)
        return

    # Купить Stars
    if text_msg == t["buy_stars"]:
        if lang == "en":
            msg = "Open TON Stars: https://tonstars.io"
        elif lang == "uk":
            msg = "Відкрийте TON Stars: https://tonstars.io"
        else:
            msg = "Откройте TON Stars: https://tonstars.io"
        await update.message.reply_text(msg)
        return

    # Кошелёк
    if text_msg == t["wallet"]:
        if lang == "en":
            msg = "Open wallet: http://t.me/send?start=r-71wfg"
        elif lang == "uk":
            msg = "Відкрити гаманець: http://t.me/send?start=r-71wfg"
        else:
            msg = "Открыть кошелёк: http://t.me/send?start=r-71wfg"
        await update.message.reply_text(msg)
        return

    # Мемляндия
    if text_msg == t["memland"]:
        top = fetch_memlandia_top5()
        if not top:
            await update.message.reply_text(text_memland_error(lang))
            return

        lines: list[str] = []
        for i, coin in enumerate(top, start=1):
            lines.append(
                format_memlandia_line(
                    i,
                    coin["name"],
                    coin["price"],
                    coin["change"],
                )
            )

        header = text_memland_header(lang)
        text_out = header + "\n\n" + "\n\n".join(lines)
        await update.message.reply_text(text_out)
        return


# отдельные команды (если кто-то руками вводит)
async def price_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_user_language(user_id)
    p = get_ton_price_usd()
    if p is not None:
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


# ------------------ MAIN ------------------

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("price", price_cmd))
    app.add_handler(CommandHandler("chart", chart_cmd))

    # inline callback (языки)
    app.add_handler(CallbackQueryHandler(callback_handler))

    # текстовые кнопки внизу
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, footer_buttons_handler)
    )

    app.run_polling()


if __name__ == "__main__":
    main()
