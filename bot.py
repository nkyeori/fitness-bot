import logging
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, timedelta
import os, json

# ===== НАЛАШТУВАННЯ =====
API_TOKEN = os.getenv("API_TOKEN")  # !!! збережи у PythonAnywhere Env Variables
MONO_URL = os.getenv("MONO_URL")    # посилання на оплату

# Google Sheets (читаємо JSON із змінної середовища)
creds_json = json.loads(os.getenv("GOOGLE_CREDS"))
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive"
]
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_json, scope)
client = gspread.authorize(creds)

# !!! ВАЖЛИВО: використовуємо open_by_key замість open("назва")
spreadsheet = client.open_by_key(os.getenv("GOOGLE_SHEET_KEY")) 
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


@dp.message_handler(lambda msg: "name" not in user_data)
async def get_name(message: types.Message):
    user_data["name"] = message.text
    await message.answer("Чудово ✅ Тепер введи свій номер телефону:")


@dp.message_handler(lambda msg: msg.text.isdigit() and "phone" not in user_data)
async def get_phone(message: types.Message):
    user_data["phone"] = message.text

    # Пакети послуг
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add("🍎 Харчування", "💪 Тренування", "🔥 All In")

    await message.answer("Вибери пакет послуг:", reply_markup=keyboard)


@dp.message_handler(lambda msg: msg.text in ["🍎 Харчування", "💪 Тренування", "🔥 All In"])
async def get_package(message: types.Message):
    user_data["package"] = message.text
    user_id = message.from_user.id

    # Запис у Google Sheets
    sheet.append_row([
        user_data["name"],
        user_data["phone"],
        user_data["package"],
        str(datetime.now().date()),
        str(user_id)
    ])

    # Повідомлення про безкоштовний тиждень
    await message.answer(
        f"Реєстрація завершена ✅\n"
        f"Тепер у тебе є 7 днів безкоштовного пробного періоду 🎁\n"
        f"Я нагадаю про оплату на 8-й день 😉"
    )

    # Плануємо повідомлення на 8-й день
    run_date = datetime.now() + timedelta(days=7)

    async def send_payment():
        keyboard = types.InlineKeyboardMarkup().add(
            types.InlineKeyboardButton("💳 Придбати пакет", url=MONO_URL)
        )
        await bot.send_message(
            user_id,
            "Твій безкоштовний тиждень завершився 🎉\n"
            "Щоб продовжити тренування — обери пакет і оплати:",
            reply_markup=keyboard
        )

    scheduler.add_job(send_payment, "date", run_date=run_date)

    # Очищаємо тимчасові дані
    user_data.clear()


# ===== ПІДТВЕРДЖЕННЯ ОПЛАТИ =====
PRIVATE_CHANNEL_LINK = "https://t.me/+I-uJW1moLLVkNmMy"  # заміни на своє посилання

@dp.message_handler(lambda msg: msg.text.lower() == "оплатив")
async def confirm_payment(message: types.Message):
    await message.answer(
        "Дякую за оплату 🙏\n\n"
        "Ось твоє посилання на приватний канал 👇\n"
        f"{PRIVATE_CHANNEL_LINK}"
    )


# ===== СТАРТ БОТА =====
if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
