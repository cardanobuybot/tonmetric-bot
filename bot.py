import os
import io
from datetime import datetime

import requests

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

BOT_TOKEN = os.getenv("BOT_TOKEN")

# Binance API
BINANCE_TICKER = "https://api.binance.com/api/v3/ticker/price"
BINANCE_KLINES = "https://api.binance.com/api/v3/klines"
SYMBOL = "TONUSDT"


# --- PRICE ---
def get_ton_price_usd():
    try:
        r = requests.get(BINANCE_TICKER, params={"symbol": SYMBOL}, timeout=8)
        data = r.json()
        return float(data["price"])
    except Exception as e:
        print("Price error:", e)
        return None


# --- CHART DATA ---
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
            print("Binance error:", klines)
            return [], []

        times = []
        prices = []

        for k in klines:
            t = datetime.fromtimestamp(k[0] / 1000)
            price = float(k[4])  # close
            times.append(t)
            prices.append(price)

        return times, prices

    except Exception as e:
        print("History error:", e)
        return [], []


# --- CHART ---
def create_ton_chart() -> bytes:
    times, prices = get_ton_history(72)
    if not times or not prices:
        raise RuntimeError("No chart data")

    current_price = prices[-1]

    plt.style.use("default")
    fig, ax = plt.subplots(figsize=(10, 4), dpi=200)

    fig.patch.set_facecolor("#FFFFFF")
    ax.set_facecolor("#F8FFFB")

    line_color = "#8BE3C9"
    ax.plot(times, prices, linewidth=2, color=line_color)
    ax.fill_between(times, prices, min(prices), color=line_color, alpha=0.25)

    ax.grid(True, linewidth=0.3, alpha=0.3)

    for side in ["top", "right"]:
        ax.spines[side].set_visible(False)

    ax.spines["bottom"].set_color("#CCCCCC")
    ax.spines["left"].set_color("#CCCCCC")

    ax.tick_params(axis="x", colors="#666666", labelsize=8)
    ax.tick_params(axis="y", colors="#666666", labelsize=8)

    ax.set_title(
        f"TONCOIN:USDT     1 TON = {current_price:.3f} $",
        color="#222222",
        fontsize=12,
        loc="left",
    )

    fig.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    plt.close()
    buf.seek(0)
    return buf.getvalue()


# --- HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я TONMETRIC BOT.\n"
        "/price — курс TON\n"
        "/chart — график TON (Binance API)"
    )


async def price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    p = get_ton_price_usd()
    if p:
        await update.message.reply_text(f"1 TON = {p:.3f} $ (Binance)")
    else:
        await update.message.reply_text("Не могу получить курс TON")


async def chart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    info = await update.message.reply_text("Строю график…")
    try:
        img = create_ton_chart()
        await update.message.reply_photo(img)
    except Exception as e:
        print("Chart error:", e)
        await update.message.reply_text("Не удалось построить график")
    finally:
        try:
            await info.delete()
        except:
            pass


def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("price", price))
    app.add_handler(CommandHandler("chart", chart))

    print("BOT STARTED")
    app.run_polling()


if __name__ == "__main__":
    main()
