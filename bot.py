import logging
import os
import sqlite3
import time

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes
)
import cryptobot

# -------------------------------------------------------
# CONFIG
# -------------------------------------------------------
TOKEN = os.getenv("BOT_TOKEN")
CRYPTOBOT_API_KEY = os.getenv("CRYPTOBOT_TOKEN")

# -------------------------------------------------------
# DB
# -------------------------------------------------------
conn = sqlite3.connect("tickets.db", check_same_thread=False)
cur = conn.cursor()
cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    total_ton REAL DEFAULT 0,
    total_tickets INTEGER DEFAULT 0
)
""")
conn.commit()


async def ensure_user(user_id):
    cur.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    conn.commit()


# -------------------------------------------------------
# UI BUTTONS
# -------------------------------------------------------
def main_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Курс", callback_data="rate"),
            InlineKeyboardButton("График", callback_data="chart")
        ],
        [
            InlineKeyboardButton("Уведомления", callback_data="alerts")
        ],
        [
            InlineKeyboardButton("Кошелёк", callback_data="wallet")
        ],
        [
            InlineKeyboardButton("Мемляндия🦄", callback_data="memes")
        ],
        [
            InlineKeyboardButton("Купить тикеты 🎟️", callback_data="buy")
        ],
        [
            InlineKeyboardButton("Мои тикеты", callback_data="my"),
            InlineKeyboardButton("🏆", callback_data="leaders"),
            InlineKeyboardButton("Реф. ссылка", callback_data="ref")
        ]
    ])


# -------------------------------------------------------
# START
# -------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await ensure_user(update.effective_user.id)
    await update.message.reply_text("Добро пожаловать!", reply_markup=main_keyboard())


# -------------------------------------------------------
# GENERATE PAYMENT (не трогаю)
# -------------------------------------------------------
async def generate_invoice(user_id, ton_amount):
    pay = cryptobot.CryptoPay(CRYPTOBOT_API_KEY)
    invoice = pay.create_invoice(
        asset="TON",
        amount=str(ton_amount),
        description="Покупка тикетов TON Metric",
        hidden_message="Спасибо за поддержку пампа 🔥"
    )
    return invoice


# -------------------------------------------------------
# CALLBACK HANDLER
# -------------------------------------------------------
async def callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    await ensure_user(user.id)

    # -------------------------------------------------------
    # Покупка тикетов (не меняю)
    # -------------------------------------------------------
    if query.data == "buy":
        invoice = await generate_invoice(user.id, 1)
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Оплатить в CryptoBot", url=invoice.pay_url)],
            [InlineKeyboardButton("Проверить оплату", callback_data=f"check_{invoice.invoice_id}")]
        ])
        await query.message.reply_text(
            f"Счёт создан ✅\n\nСумма: 1 TON\nТикетов: 1\n\nПосле оплаты нажми «Проверить оплату».",
            reply_markup=kb
        )
        return

    # -------------------------------------------------------
    # Проверка оплаты (не трогаю)
    # -------------------------------------------------------
    if query.data.startswith("check_"):
        invoice_id = query.data.split("_")[1]
        pay = cryptobot.CryptoPay(CRYPTOBOT_API_KEY)
        info = pay.get_invoices(invoice_ids=[invoice_id])

        if not info or info[0].status != "paid":
            await query.message.reply_text("Не удалось проверить оплату 🥲")
            return

        # начисление
        cur.execute("""
            UPDATE users
            SET total_ton = total_ton + 1,
                total_tickets = total_tickets + 1
            WHERE user_id = ?
        """, (user.id,))
        conn.commit()

        await query.message.reply_text("Оплата получена ✅\nТебе начислено: 1 тикетов.")
        return

    # -------------------------------------------------------
    # МОИ ТИКЕТЫ (не трогаю)
    # -------------------------------------------------------
    if query.data == "my":
        cur.execute("SELECT total_tickets, total_ton FROM users WHERE user_id=?", (user.id,))
        row = cur.fetchone()
        tickets, ton = row
        await query.message.reply_text(
            f"Твои тикеты: {tickets}\nВсего куплено: {ton:.2f} TON"
        )
        return

    # -------------------------------------------------------
    # ЛИДЕРБОРД (ИМЕННО ЗДЕСЬ МОЁ ЕДИНСТВЕННОЕ ИЗМЕНЕНИЕ)
    # -------------------------------------------------------
    if query.data == "leaders":
        cur.execute("""
            SELECT user_id, total_tickets, total_ton
            FROM users
            WHERE total_tickets > 0
            ORDER BY total_tickets DESC
        """)
        rows = cur.fetchall()

        if not rows:
            await query.message.reply_text("Пока ещё никто не купил тикеты.")
            return

        text = "🏆 Лидерборд по тикетам:\n\n"

        for idx, (uid, tickets, ton) in enumerate(rows, start=1):
            # получаем данные юзера
            member = await context.bot.get_chat(uid)

            # выбираем красивое имя
            if member.username:
                name = f"@{member.username}"
            elif member.full_name:
                name = member.full_name
            else:
                name = f"ID {uid}"

            # кликабельная ссылка
            link = f"tg://user?id={uid}"

            # показываем тебя как (ты)
            suffix = " (ты)" if uid == query.from_user.id else ""

            text += f"{idx}. [{name}]({link}){suffix}\n" \
                    f"тикеты: {tickets}, всего куплено: {ton:.2f} TON\n\n"

        await query.message.reply_text(text, parse_mode="Markdown")
        return

    # -------------------------------------------------------
    # Реф. ссылка (не трогаю)
    # -------------------------------------------------------
    if query.data == "ref":
        ref = f"https://t.me/tonmetric_bot?start={user.id}"
        await query.message.reply_text(f"Твоя реф. ссылка:\n{ref}")
        return


# -------------------------------------------------------
# RUN
# -------------------------------------------------------
def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callbacks))

    print("DB: tables ensured")
    app.run_polling()


if __name__ == "__main__":
    main()
