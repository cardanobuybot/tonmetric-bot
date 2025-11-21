import os
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

BOT_TOKEN = os.getenv("BOT_TOKEN")  # токен возьмём из переменных окружения

COINGECKO_URL = "https://api.coingecko.com/api/v3/simple/price"
TON_ID = "the-open-network"

def get_ton_price_usd() -> float | None:
    try:
        r = requests.get(
            COINGECKO_URL,
            params={"ids": TON_ID, "vs_currencies": "usd"},
            timeout=5
        )
        data = r.json()
        return float(data[TON_ID]["usd"])
    except Exception as e:
        print("Error getting price:", e)
        return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я TONMETRIC BOT.\n"
        "Команды:\n"
        "/price — курс TON\n"
        "/chart — (пока пусто, потом сделаем график)"
    )

async def price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    price = get_ton_price_usd()
    if price is None:
        await update.message.reply_text("Не могу получить курс, попробуй позже 🙈")
    else:
        await update.message.reply_text(f"1 TON = {price:.2f} $")

def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN не задан в переменных окружения")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("price", price))

    print("TONMETRIC BOT запущен")
    app.run_polling()

if __name__ == "__main__":
    main()
