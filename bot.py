import asyncio
import json
from aiogram import Bot, Dispatcher
from aiogram.types import Message, KeyboardButton, ReplyKeyboardMarkup, WebAppInfo
from aiogram.filters import CommandStart

TOKEN = "8648644673:AAE4-xVguaXoTSdaHkzGa3uL2bciuIc6wR8"

bot = Bot(token=TOKEN)
dp = Dispatcher()

web_app = WebAppInfo(
    url="https://p0werful3.github.io/telegram-marketplace-miniapp/"
)

keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🛍 Відкрити магазин", web_app=web_app)]
    ],
    resize_keyboard=True
)

@dp.message(CommandStart())
async def start(message: Message):
    await message.answer(
        "Вітаємо у Telegram-маркетплейсі!\nНатисни кнопку нижче, щоб відкрити магазин.",
        reply_markup=keyboard
    )

@dp.message(lambda message: message.web_app_data is not None)
async def handle_web_app_data(message: Message):
    try:
        data = json.loads(message.web_app_data.data)

        items = data.get("items", [])
        total = data.get("total", 0)

        if not items:
            await message.answer("Отримано порожнє замовлення.")
            return

        text = "🧾 <b>Нове замовлення</b>\n\n"
        text += f"👤 <b>Користувач:</b> {message.from_user.full_name}\n"
        text += f"🆔 <b>ID:</b> {message.from_user.id}\n\n"
        text += "<b>Товари:</b>\n"

        for i, item in enumerate(items, start=1):
            text += f"{i}. {item['name']} — {item['price']}$\n"

        text += f"\n💰 <b>Сума:</b> {total}$"

        await message.answer(text, parse_mode="HTML")

    except Exception as e:
        await message.answer(f"Помилка обробки замовлення: {e}")

async def main():
    print("Бот запущено...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())