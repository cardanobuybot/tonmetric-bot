import os
import io
from datetime import datetime, timedelta

import requests

# headless backend для сервера
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

BOT_TOKEN = os.getenv("BOT_TOKEN")

# --- MEXC API ---
MEXC_TICKER_URL = "https://api.mexc.com/api/v3/ticker/price"
MEXC_KLINES_URL = "https://api.mexc.com/api/v3/klines"
TON_SYMBOL = "TONUSDT"


# --------- ДАННЫЕ ---------

def get_ton_price_usd() -> float | None:
    """Текущий курс TON в USDT с биржи MEXC."""
    try:
        r = requests.get(
            MEXC_TICKER_URL,
            params={"symbol": TON_SYMBOL},
            timeout=8,
        )
        if r.status_code != 200:
            print("Price status:", r.status_code, r.text[:200])
            return None

        data = r.json()
        # ответ вида: {"symbol":"TONUSDT","price":"1.4900"}
        price_str = data.get("price")
        if not price_str:
            print("No 'price' in response:", data)
            return None

        return float(price_str)
    except Exception as e:
        print("Error getting price from MEXC:", e)
        return None


def get_ton_history(hours: int = 72):
    """
    История цены TON c MEXC.
    Берём 1-часовые свечи за N часов (по умолчанию 72 = 3 дня).
    """
    try:
        # лимит свечей укажем равным числу часов (макс 1000, нам надо мало)
        r = requests.get(
            MEXC_KLINES_URL,
            params={
                "symbol": TON_SYMBOL,
                "interval": "1h",
                "limit": hours,
            },
            timeout=15,
        )
        if r.status_code != 200:
            print("Klines status:", r.status_code, r.text[:200])
            return [], []

        klines = r.json()
        if not klines:
            print("Empty klines list")
            return [], []

        times = []
        prices = []

        for k in klines:
            # формат строки:
            # [ openTime, open, high, low, close, volume, ... ]
            open_time_ms = k[0]
            close_price_str = k[4]

            t = datetime.fromtimestamp(open_time_ms / 1000)
            price = float(close_price_str)

            times.append(t)
            prices.append(price)

        return times, prices

    except Exception as e:
        print("Error getting history from MEXC:", e)
        return [], []


# --------- ГРАФИК ---------

def create_ton_chart() -> bytes:
    """
    Строим светлый график в стиле TONOMETER:
    - белый фон
    - мягкая зелёная линия
    - заливка под графиком
    """
    times, prices = get_ton_history(hours=72)
    if not times or not prices:
        raise RuntimeError("No data for chart")

    current_price = prices[-1]

    plt.style.use("default")
    fig, ax = plt.subplots(figsize=(10, 4), dpi=200)

    # фон
    fig.patch.set_facecolor("#FFFFFF")
    ax.set_facecolor("#F8FFFB")  # очень светлый зелёный фон

    # линия + заливка
    line_color = "#8BE3C9"  # мятный
    ax.plot(times, prices, linewidth=2.0, color=line_color)
    ax.fill_between(times, prices, min(prices),
                    color=line_color, alpha=0.25)

    # сетка
    ax.grid(True, which="major", linestyle="-", linewidth=0.4, alpha=0.2)

    # убираем верхнюю/правую рамку
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    # оси
    for spine in ["bottom", "left"]:
        ax.spines[spine].set_color("#CCCCCC")
        ax.spines[spine].set_linewidth(0.8)

    ax.tick_params(axis="x", colors="#666666", labelsize=8, rotation=0)
    ax.tick_params(axis="y", colors="#666666", labelsize=8)

    # заголовок
    ax.set_title(
        f"TONCOIN:USDT         1 TON = {current_price:.3f} $",
        loc="left",
        fontsize=12,
        color="#222222",
        pad=10,
    )

    fig.tight_layout(pad=2)

    buf = io.BytesIO()
    plt.savefig(buf, format="png", bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()


# --------- ХЭНДЛЕРЫ ТГ ---------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я TONMETRIC BOT.\n"
        "Команды:\n"
        "/price — курс TON\n"
        "/chart — график цены TON (по MEXC)"
    )


async def price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    price = get_ton_price_usd()
    if price is None:
        await update.message.reply_text("Не могу получить курс TON (MEXC), попробуй позже 🙈")
    else:
        await update.message.reply_text(f"1 TON = {price:.3f} $ (MEXC)")


async def chart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("Строю график TON… 📈")
    try:
        png_bytes = create_ton_chart()
        await update.message.reply_photo(photo=png_bytes)
    except Exception as e:
        print("Error in /chart:", e)
        await update.message.reply_text("Не удалось построить график, попробуй позже 🙈")
    finally:
        try:
            await msg.delete()
        except Exception:
            pass


def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN не задан в переменных окружения")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("price", price))
    app.add_handler(CommandHandler("chart", chart))

    print("TONMETRIC BOT started")
    app.run_polling()


if __name__ == "__main__":
    main()
