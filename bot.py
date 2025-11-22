import os
import io
from datetime import datetime
from typing import Dict

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

BOT_TOKEN = os.getenv("BOT_TOKEN")

# Binance API
BINANCE_TICKER = "https://api.binance.com/api/v3/ticker/price"
BINANCE_KLINES = "https://api.binance.com/api/v3/klines"
SYMBOL = "TONUSDT"

# Язык пользователя
user_lang: Dict[int, str] = {}          # user_id -> 'ru' | 'en' | 'uk'
# Подписки на уведомления: baseline-цена, от которой считаем ±10%
user_subscriptions: Dict[int, float] = {}  # user_id -> baseline_price


# ------------------ ВСПОМОГАТЕЛЬНЫЕ ТЕКСТЫ ------------------


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


def text_notifications_intro(lang: str) -> str:
    if lang == "en":
        return (
            "You will receive a notification when TON price changes by more than 10% "
            "up or down from the current price."
        )
    elif lang == "uk":
        return (
            "Ми повідомимо, коли ціна TON зміниться більш ніж на 10% "
            "вгору або вниз від поточної ціни."
        )
    else:
        return (
            "Мы уведомим, когда цена TON изменится более чем на 10% "
            "вверх или вниз от текущей цены."
        )


def text_unsubscribed(lang: str) -> str:
    if lang == "en":
        return "You have unsubscribed from price alerts."
    elif lang == "uk":
        return "Ви відписалися від сповіщень про зміну ціни."
    else:
        return "Вы отписались от уведомлений об изменении цены."


def text_alert(lang: str, old_price: float, new_price: float) -> str:
    change = (new_price - old_price) / old_price * 100
    sign = "▲" if change > 0 else "▼"
    if lang == "en":
        return (
            f"{sign} TON price changed more than 10%.\n"
            f"Old price: {old_price:.3f} $\n"
            f"New price: {new_price:.3f} $ ({change:+.1f}%)"
        )
    elif lang == "uk":
        return (
            f"{sign} Ціна TON змінилася більш ніж на 10%.\n"
            f"Стара ціна: {old_price:.3f} $\n"
            f"Нова ціна: {new_price:.3f} $ ({change:+.1f}%)"
        )
    else:
        return (
            f"{sign} Цена TON изменилась более чем на 10%.\n"
            f"Старая цена: {old_price:.3f} $\n"
            f"Новая цена: {new_price:.3f} $ ({change:+.1f}%)"
        )


# ------------------ LABELS КНОПОК ------------------


def footer_labels(lang: str):
    if lang == "en":
        return {
            "price": "Price",
            "chart": "Chart",
            "notify": "Notifications",
            "buy": "Buy Stars ⭐",
            "wallet": "Wallet",
        }
    elif lang == "uk":
        return {
            "price": "Курс",
            "chart": "Графік",
            "notify": "Сповіщення",
            "buy": "Купити Stars ⭐",
            "wallet": "Гаманець",
        }
    else:
        return {
            "price": "Курс",
            "chart": "График",
            "notify": "Уведомления",
            "buy": "Купить Stars ⭐",
            "wallet": "Кошелёк",
        }


def footer_keyboard(lang: str) -> ReplyKeyboardMarkup:
    labels = footer_labels(lang)
    keyboard = [
        [KeyboardButton(labels["price"])],
        [KeyboardButton(labels["chart"])],
        [KeyboardButton(labels["notify"])],
        [KeyboardButton(labels["buy"])],
        [KeyboardButton(labels["wallet"])],
    ]
    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
        one_time_keyboard=False,
    )


# ------------------ ДАННЫЕ TON ------------------


def get_ton_price_usd():
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

        times = [datetime.fromtimestamp(k[0] / 1000) for k in klines]
        prices = [float(k[4]) for k in klines]

        return times, prices

    except Exception as e:
        print("History error:", e)
        return [], []


# ------------------ ГРАФИК ------------------


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
    data = query.data
    user_id = query.from_user.id
    chat_id = query.message.chat_id

    # выбор языка
    if data.startswith("lang_"):
        lang = data.split("_", 1)[1]  # en / ru / uk
        user_lang[user_id] = lang

        await query.message.reply_text(
            text_lang_confirm(lang),
            reply_markup=footer_keyboard(lang),
        )

        await send_price_and_chart(chat_id, lang, context)

    # отписка от уведомлений
    elif data == "unsub":
        if user_id in user_subscriptions:
            del user_subscriptions[user_id]
        lang = get_user_language(user_id)
        await query.message.reply_text(text_unsubscribed(lang))


async def footer_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_user_language(user_id)
    labels = footer_labels(lang)
    text = (update.message.text or "").strip()

    # Курс
    if text == labels["price"]:
        p = get_ton_price_usd()
        if p:
            await update.message.reply_text(text_price_ok(lang, p))
        else:
            await update.message.reply_text(text_price_error(lang))

    # График
    elif text == labels["chart"]:
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

    # Уведомления — сразу подписываем + кнопка "Отписаться"
    elif text == labels["notify"]:
        current_price = get_ton_price_usd()
        if current_price is None:
            await update.message.reply_text(text_price_error(lang))
            return

        # сохраняем baseline для этого пользователя
        user_subscriptions[user_id] = current_price

        keyboard = [
            [InlineKeyboardButton(
                "Отписаться" if lang == "ru" else ("Unsubscribe" if lang == "en" else "Відписатися"),
                callback_data="unsub"
            )]
        ]

        await update.message.reply_text(
            text_notifications_intro(lang),
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    # Купить Stars ⭐ — текст + ссылка
    elif text == labels["buy"]:
        if lang == "en":
            msg = "Open TON Stars: https://tonstars.io"
        elif lang == "uk":
            msg = "Відкрийте TON Stars: https://tonstars.io"
        else:
            msg = "Откройте TON Stars: https://tonstars.io"
        await update.message.reply_text(msg)

    # Кошелёк — ссылка на send-бот
    elif text == labels["wallet"]:
        if lang == "en":
            msg = "Open wallet: http://t.me/send?start=r-71wfg"
        elif lang == "uk":
            msg = "Відкрити гаманець: http://t.me/send?start=r-71wfg"
        else:
            msg = "Открыть кошелёк: http://t.me/send?start=r-71wfg"
        await update.message.reply_text(msg)


async def price_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_user_language(user_id)
    p = get_ton_price_usd()
    if p:
        await update.message.reply_text(text_price_ok(lang, p))
    else:
        await update.message.reply_text(text_price_error(lang))


async def chart_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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


# ---------- ФОНОВЫЙ JOB ДЛЯ УВЕДОМЛЕНИЙ ----------


async def price_watcher(context: ContextTypes.DEFAULT_TYPE):
    if not user_subscriptions:
        return

    current_price = get_ton_price_usd()
    if current_price is None:
        return

    # копию items, чтобы можно было изменять dict по ходу
    for user_id, baseline in list(user_subscriptions.items()):
        if baseline <= 0:
            continue
        change_ratio = abs(current_price - baseline) / baseline
        if change_ratio >= 0.10:  # 10%
            lang = get_user_language(user_id)
            text = text_alert(lang, baseline, current_price)
            try:
                await context.bot.send_message(chat_id=user_id, text=text)
            except Exception as e:
                print("Notify error:", e)
            # обновляем baseline, чтобы следующее уведомление было от новой цены
            user_subscriptions[user_id] = current_price


# ------------------ MAIN ------------------


def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN не задан в переменных окружения")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("price", price_command))
    app.add_handler(CommandHandler("chart", chart_command))

    # inline callback-и (язык + отписка)
    app.add_handler(CallbackQueryHandler(callback_handler))

    # обработка текстовых кнопок (reply keyboard)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, footer_handler))

    # фоновая задача слежения за ценой
    job_queue = app.job_queue
    job_queue.run_repeating(price_watcher, interval=300, first=30)  # каждые 5 минут

    app.run_polling()


if __name__ == "__main__":
    main()
