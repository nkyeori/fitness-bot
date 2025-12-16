import logging
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, timedelta
import os, json

# ===== НАЛАШТУВАННЯ =====
API_TOKEN = os.getenv("API_TOKEN")   # ⚠️ Читаємо токен з Config Vars
MONO_URL = os.getenv("MONO_URL")     # ⚠️ Читаємо посилання на оплату з Config Vars
GOOGLE_CREDS = os.getenv("GOOGLE_CREDS")  # ⚠️ Твої JSON креденшіали

if not API_TOKEN:
    raise ValueError("❌ Не знайдено API_TOKEN у Config Vars!")
if not MONO_URL:
    raise ValueError("❌ Не знайдено MONO_URL у Config Vars!")
if not GOOGLE_CREDS:
    raise ValueError("❌ Не знайдено GOOGLE_CREDS у Config Vars!")

# Google Sheets
creds_json = json.loads(GOOGLE_CREDS)
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive"
]
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_json, scope)
client = gspread.authorize(creds)

# ⚠️ заміни ID на свій з Google Sheets
spreadsheet = client.open_by_key("1NafZ0VmtlMzUvV5vujoiK4x3y0PEop7wJIzYXAlfS5E")
sheet = spreadsheet.sheet1

# Логування
logging.basicConfig(level=logging.INFO)

# Бот і диспетчер
bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

# Планувальник
scheduler = AsyncIOScheduler()
scheduler.start()

# Тимчасові дані користувача
user_data = {}

# ===== ОБРОБНИКИ =====
@dp.message_handler(commands=['start'])
async def start_command(message: types.Message):
    user_data.clear()
    await message.answer("Привіт 👋 Я твій фітнес-бот!\n\nВведи своє ім'я:")

@dp.message_handler(lambda msg: msg.text and "name" not in user_data)
async def get_name(message: types.Message):
    user_data["name"] = message.text
    await message.answer("Чудово ✅ Тепер введи свій номер телефону:")

@dp.message_handler(lambda msg: msg.text and msg.text.isdigit() and "phone" not in user_data)
async def get_phone(message: types.Message):
    user_data["phone"] = message.text
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add("🍎 Харчування", "💪 Тренування", "🔥 All In")
    await message.answer("Вибери пакет послуг:", reply_markup=keyboard)

@dp.message_handler(lambda msg: msg.text in ["🍎 Харчування", "💪 Тренування", "🔥 All In"])
async def get_package(message: types.Message):
    user_data["package"] = message.text
    user_id = message.from_user.id

    # --- Базові ціни ---
    base_prices = {
        "🍎 Харчування": 1500,
        "💪 Тренування": 1500,
        "🔥 All In": 2500
    }
    base_price = base_prices[user_data["package"]]

    # --- Рахуємо кількість клієнтів з оплатою ---
    all_rows = sheet.get_all_records()
    paid_clients = sum(1 for row in all_rows if str(row.get("Оплачено", "")).lower() in ["так", "yes", "paid"])

    # --- Призначаємо ціну ---
    final_price = base_price
    if paid_clients < 15:   # перші 15 оплат отримують знижку
        final_price = int(base_price * 0.8)

    # --- Запис у таблицю (поки "Оплачено" пусте) ---
    sheet.append_row([
        user_data["name"],
        user_data["phone"],
        user_data["package"],
        str(datetime.now().date()),
        str(user_id),
        str(final_price),
        ""  # колонка "Оплачено" (порожня на старті)
    ])

    # Повідомлення про пробний період
    await message.answer(
        "Реєстрація завершена ✅\n"
        "Тепер у тебе є 7 днів безкоштовного пробного періоду 🎁\n"
        "Я нагадаю про оплату на 8-й день 😉"
    )
    await message.answer("⏳ Очікуй повідомлення від тренера 📩")

    # --- Нагадування про оплату ---
    run_date = datetime.now() + timedelta(days=7)

    async def send_first_payment():
        keyboard = types.InlineKeyboardMarkup().add(
            types.InlineKeyboardButton("💳 Придбати пакет", url=f"{MONO_URL}?amount={final_price*100}")
        )

        if final_price < base_price:
            text = (
                "🎉 Вітаю! Ви серед перших клієнтів і отримали персональну знижку -20%!\n\n"
                f"Тепер вартість твого пакета складає: {final_price} грн (замість {base_price} грн).\n\n"
                "Щоб продовжити тренування — натисни кнопку нижче 👇"
            )
        else:
            text = (
                "Твій безкоштовний тиждень завершився 🎉\n"
                f"Вартість твого пакета: {final_price} грн\n\n"
                "Щоб продовжити тренування — натисни кнопку нижче 👇"
            )

        await bot.send_message(user_id, text, reply_markup=keyboard)

    scheduler.add_job(send_first_payment, "date", run_date=run_date)

    # --- Далі регулярні нагадування кожні 4 тижні ---
    async def send_regular_reminder():
        keyboard = types.InlineKeyboardMarkup().add(
            types.InlineKeyboardButton("💳 Оплатити підписку", url=f"{MONO_URL}?amount={final_price*100}")
        )
        await bot.send_message(
            user_id,
            f"⚠️ Нагадую, що твоя підписка завершується завтра.\n"
            f"Вартість продовження: {final_price} грн",
            reply_markup=keyboard
        )

    scheduler.add_job(send_regular_reminder, "date", run_date=datetime.now() + timedelta(days=27))
    scheduler.add_job(send_regular_reminder, "interval", weeks=4, start_date=datetime.now() + timedelta(days=27))

    user_data.clear()

# ===== СТАТУС ОПЛАТИ =====
PRIVATE_CHANNEL_LINK = os.getenv("PRIVATE_CHANNEL_LINK") or "https://t.me/+твій_канал"

@dp.message_handler(lambda msg: msg.text.lower() == "оплатив")
async def confirm_payment(message: types.Message):
    user_id = str(message.from_user.id)

    # Отримуємо всі рядки з таблиці
    all_rows = sheet.get_all_values()

    # Шукаємо рядок користувача
    for i, row in enumerate(all_rows, start=1):  # start=1 бо перший рядок може бути заголовком
        if user_id in row:
            # Припустимо, що колонка "Оплачено" знаходиться в 7-му стовпці (G)
            sheet.update_cell(i, 7, "Так")

            await message.answer(
                "✅ Оплату підтверджено!\n\n"
                "Ось твоє посилання на приватний канал 👇\n"
                f"{PRIVATE_CHANNEL_LINK}"
            )
            return

    # Якщо користувача не знайшло
    await message.answer("❌ Тебе ще немає в базі. Пройди реєстрацію перед оплатою!")


# ===== СТАРТ БОТА =====
if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
