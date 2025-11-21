import os
import io
from datetime import datetime

import requests
import matplotlib.pyplot as plt
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

BOT_TOKEN = os.getenv("BOT_TOKEN")

COINGECKO_SIMPLE_URL = "https://api.coingecko.com/api/v3/simple/price"
COINGECKO_CHART_URL = "https://api.coingecko.com/api/v3/coins/the-open-network/market_chart"
TON_ID = "the-open-network"


def get_ton_price_usd() -> float | None:
    """Текущий курс TON в USD."""
    try:
        r = requests.get(
            COINGECKO_SIMPLE_URL,
            params={"ids": TON_ID, "vs_currencies": "usd"},
            timeout=5,
        )
        data = r.json()
        return float(data[TON_ID]["usd"])
    except Exception as e:
        print("Error getting price:", e)
        return None


def get_ton_history(days: int = 3):
    """История цены для графика за N дней."""
    try:
        r = requests.get(
            COINGECKO_CHART_URL,
            params={"vs_currency": "usd", "days": days, "interval": "hourly"},
            timeout=10,
        )
        data = r.json()["prices"]  # список [timestamp, price]
        times = [datetime.fromtimestamp(p[0] / 1000) for p in data]
        prices = [p[1] for p in data]
        return times, prices
    except Exception as e:
        print("Error getting history:", e)
        return [], []


def create_ton_chart() -> bytes:
    """
    Рисуем красивый кастомный график и возвращаем PNG как bytes.
    """

    times, prices = get_ton_history(days=3)
    if not times or not prices:
        raise RuntimeError("No data for chart")

    current_price = prices[-1]

    # ---------- Кастомная тема ----------
    plt.style.use("default")
    fig, ax = plt.subplots(figsize=(10, 4), dpi=200)

    # фон всего графика
    fig.patch.set_facecolor("#050814")      # тёмный почти чёрный
    ax.set_facecolor("#050814")

    # линия цены
    ax.plot(times, prices, linewidth=2.5, color="#21E6A2")

    # заливка под графиком
    ax.fill_between(times, prices, min(prices),
                    color="#21E6A2", alpha=0.12)

    # сетка — тонкая, полупрозрачная
    ax.grid(True, which="major", linestyle="-", linewidth=0.4, alpha=0.2)

    # убираем рамку сверху и справа
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    # оси делаем мягкого серого цвета
    for spine in ["bottom", "left"]:
        ax.spines[spine].set_color("#5A6475")
        ax.spines[spine].set_linewidth(0.8)

    # подписи осей
    ax.tick_params(
        axis="x",
        colors="#8C96A5",
        labelsize=8,
        rotation=0,
    )
    ax.tick_params(
        axis="y",
        colors="#8C96A5",
        labelsize=8,
    )

    # Тайтл слева и текущая цена справа
    ax.set_title(
        f"TONCOIN:USD   •   1 TON = {current_price:.2f} $",
        loc="left",
        fontsize=11,
        color="#FFFFFF",
        pad=12,
    )

    # подсветка последней точки
    ax.scatter(times[-1], prices[-1],
               s=24, color="#FFFFFF", zorder=5, edgecolor="#21E6A2", linewidth=1.5)

    # немного отступов
    fig.tight_layout(pad=2)

    # сохраняем в память, не в файл
    buf = io.BytesIO()
    plt.savefig(buf, format="png", bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я TONMETRIC BOT.\n"
        "Команды:\n"
        "/price — курс TON\n"
        "/chart — график цены TON (кастомная тема)"
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
        # отправляем как фото из байт
        await update.message.reply_photo(photo=png_bytes)
    except Exception as e:
        print("Error in /chart:", e)
        await update.message.reply_text("Не удалось построить график, попробуй позже 🙈")
    finally:
        # удаляем сообщение "Строю график…", если нужно
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
