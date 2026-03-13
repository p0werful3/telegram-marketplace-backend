import asyncio
from aiogram import Bot, Dispatcher
from aiogram.types import Message, KeyboardButton, ReplyKeyboardMarkup, WebAppInfo
from aiogram.filters import CommandStart

TOKEN = "8648644673:AAE4-xVguaXoTSdaHkzGa3uL2bciuIc6wR8"

bot = Bot(token=TOKEN)
dp = Dispatcher()

web_app = WebAppInfo(
    url="https://p0werful3.github.io/telegram-marketplace-miniapp/?v=150"
)

keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🛍 Відкрити маркетплейс", web_app=web_app)]
    ],
    resize_keyboard=True,
    input_field_placeholder="Натисніть кнопку нижче"
)

@dp.message(CommandStart())
async def start_handler(message: Message):
    await message.answer(
        "Ласкаво просимо до Telegram Marketplace!\n\n"
        "Натисніть кнопку нижче, щоб відкрити Mini App.",
        reply_markup=keyboard
    )

async def main():
    print("Бот запущений...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())








