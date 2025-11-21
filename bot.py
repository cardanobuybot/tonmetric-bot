import os
import io
from datetime import datetime

import requests

# headless backend, чтобы работало на сервере
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

BOT_TOKEN = os.getenv("BOT_TOKEN")

COINGECKO_SIMPLE_URL = "https://api.coingecko.com/api/v3/simple/price"
COINGECKO_CHART_URL = "https://api.coingecko.com/api/v3/coins/the-open-network/market_chart"
TON_ID = "the-open-network"


# --------- ДАННЫЕ ---------

def get_ton_price_usd() -> float | None:
    """Текущий курс TON в USD."""
    try:
        r = requests.get(
            COINGECKO_SIMPLE_URL,
            params={"ids": TON_ID, "vs_currencies": "usd"},
            timeout=8,
        )
        if r.status_code != 200:
            print("Price status:", r.status_code, r.text[:200])
            return None
        data = r.json()
        return float(data[TON_ID]["usd"])
    except Exception as e:
        print("Error getting price:", e)
        return None


def get_ton_history(days: int = 3):
    """История цены для графика за N дней (часовые свечи)."""
    try:
        r = requests.get(
            COINGECKO_CHART_URL,
            params={"vs_currency": "usd", "days": days, "interval": "hourly"},
            timeout=15,
        )
        if r.status_code != 200:
            print("History status:", r.status_code, r.text[:200])
            return [], []

        j = r.json()
        if "prices" not in j:
            print("No 'prices' in response:", j)
            return [], []

        data = j["prices"]
        if not data:
            print("Empty prices list")
            return [], []

        times = [datetime.fromtimestamp(p[0] / 1000) for p in data]
        prices = [p[1] for p in data]
        return times, prices
    except Exception as e:
        print("Error getting history:", e)
        return [], []


# --------- ГРАФИК (другой стиль) ---------

def create_ton_chart() -> bytes:
    """
    Строим светлый график в стиле TONOMETER:
    - белый фон
    - мягкая зелёная линия
    - заливка под графиком
    """

    times, prices = get_ton_history(days=3)
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
        f"TONCOIN:USD         1 TON = {current_price:.2f} $",
        loc="left",
        fontsize=12,
        color="#222222",
        pad=10,
    )

    # небольшой отступ по краям
    fig.tight_layout(pad=2)

    # вывод в байты
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
        "/chart — график цены TON"
    )


async def price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    price = get_ton_price_usd()
    if price is None:
        await update.message.reply_text("Не могу получить курс, попробуй позже 🙈")
    else:
        await update.message.reply_text(f"1 TON = {price:.2f} $")


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
