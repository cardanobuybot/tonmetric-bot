import os
import io
from datetime import datetime

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import requests

from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

# ------------------ НАСТРОЙКИ ------------------

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не задан в переменных окружения")

# Binance
BINANCE_TICKER = "https://api.binance.com/api/v3/ticker/price"
BINANCE_KLINES = "https://api.binance.com/api/v3/klines"
SYMBOL = "TONUSDT"

# Мемляндия (примерный URL — подправишь при необходимости)
MEMLAND_API_URL = "https://memelandia.okhlopkov.com/api/leaderboard?limit=5"

# Память по языку пользователя
user_lang: dict[int, str] = {}  # user_id -> 'ru' | 'en' | 'uk'

# Подписи кнопок по языкам
BUTTON_LABELS = {
    "ru": {
        "price": "Курс",
        "chart": "График",
        "notifications": "Уведомления",
        "buy_stars": "Купить Stars ⭐",
        "wallet": "Кошелёк",
        "memland": "Мемляндия🦄",
    },
    "uk": {
        "price": "Курс",
        "chart": "Графік",
        "notifications": "Сповіщення",
        "buy_stars": "Купити Stars ⭐",
        "wallet": "Гаманець",
        "memland": "Мемляндія🦄",
    },
    "en": {
        "price": "Price",
        "chart": "Chart",
        "notifications": "Alerts",
        "buy_stars": "Buy Stars ⭐",
        "wallet": "Wallet",
        "memland": "Memelandia🦄",
    },
}


# ------------------ ВСПОМОГАТЕЛЬНОЕ ------------------

def get_user_language(user_id: int) -> str:
    return user_lang.get(user_id, "ru")


def text_lang_confirm(lang: str) -> str:
    if lang == "en":
        return "Language: English ✅"
    elif lang == "uk":
        return "Мова: Українська ✅"
    else:
        return "Язык: Русский ✅"


def text_welcome(lang: str) -> str:
    if lang == "en":
        return "Hi! I’m TON Metric Bot. Choose an action:"
    elif lang == "uk":
        return "Привіт! Я TON Metric Bot. Оберіть дію:"
    else:
        return "Привет! Я TON Metric Bot. Выберите действие:"


def text_notifications_unavailable(lang: str) -> str:
    if lang == "en":
        return "Notifications are temporarily unavailable 🙈"
    elif lang == "uk":
        return "Сповіщення тимчасово недоступні 🙈"
    else:
        return "Уведомления временно недоступны 🙈"


def text_price_ok(lang: str, price: float) -> str:
    # текст одинаковый, только эмодзи можно менять при желании
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


def text_wallet_link(lang: str) -> str:
    if lang == "en":
        return "Open wallet: http://t.me/send?start=r-71wfg"
    elif lang == "uk":
        return "Відкрити гаманець: http://t.me/send?start=r-71wfg"
    else:
        return "Открыть кошелёк: http://t.me/send?start=r-71wfg"


def text_buy_stars(lang: str) -> str:
    if lang == "en":
        return "Open TON Stars: https://tonstars.io"
    elif lang == "uk":
        return "Відкрийте TON Stars: https://tonstars.io"
    else:
        return "Откройте TON Stars: https://tonstars.io"


# ------------------ МЕМЛЯНДИЯ ------------------

def get_memland_top5() -> str | None:
    """
    Пытаемся вытащить ТОП-5 Мемляндии из API.
    URL и структура JSON ты при желании подправишь.
    """
    try:
        r = requests.get(MEMLAND_API_URL, timeout=10)
        r.raise_for_status()
        data = r.json()

        # data может быть списком или словарём
        if isinstance(data, dict):
            rows = data.get("items") or data.get("data")
