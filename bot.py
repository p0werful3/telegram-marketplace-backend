import asyncio
import os
from aiogram import Bot, Dispatcher
from aiogram.types import Message, KeyboardButton, ReplyKeyboardMarkup, WebAppInfo
from aiogram.filters import CommandStart
from aiohttp import web

TOKEN = "8648644673:AAE4-xVguaXoTSdaHkzGa3uL2bciuIc6wR8"

bot = Bot(token=TOKEN)
dp = Dispatcher()

web_app = WebAppInfo(
    url="https://p0werful3.github.io/telegram-marketplace-miniapp/?v=266"
)

keyboard = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="🛍 Відкрити маркетплейс", web_app=web_app)]],
    resize_keyboard=True
)

@dp.message(CommandStart())
async def start_handler(message: Message):
    await message.answer(
        "Ласкаво просимо до Telegram Marketplace!",
        reply_markup=keyboard
    )

async def handle(request):
    return web.Response(text="Bot is running")

async def main():
    asyncio.create_task(dp.start_polling(bot))

    app = web.Application()
    app.router.add_get("/", handle)

    port = int(os.environ.get("PORT", 10000))
    runner = web.AppRunner(app)
    await runner.setup()

    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())
