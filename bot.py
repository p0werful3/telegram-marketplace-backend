import asyncio
import os
from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import Message, KeyboardButton, ReplyKeyboardMarkup, WebAppInfo
from aiohttp import web, ClientSession

TOKEN = os.getenv("BOT_TOKEN", "8648644673:AAE4-xVguaXoTSdaHkzGa3uL2bciuIc6wR8")
API_URL = os.getenv("API_URL", "https://telegram-marketplace-api.onrender.com")
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://p0werful3.github.io/telegram-marketplace-miniapp/?v=331")

bot = Bot(token=TOKEN)
dp = Dispatcher()

web_app = WebAppInfo(url=WEBAPP_URL)
keyboard = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="🛍 Відкрити маркетплейс", web_app=web_app)]],
    resize_keyboard=True,
)


async def sync_telegram_user(message: Message) -> None:
    username = (message.from_user.username or "").strip()
    payload = {
        "telegram_id": str(message.from_user.id),
        "username": username,
        "full_name": message.from_user.full_name,
    }
    try:
        async with ClientSession() as session:
            async with session.post(f"{API_URL}/telegram/start-sync", json=payload, timeout=10) as response:
                await response.text()
    except Exception as exc:
        print(f"Telegram sync error: {exc}")


@dp.message(CommandStart())
async def start_handler(message: Message):
    await sync_telegram_user(message)

    username_hint = f"{message.from_user.username} (без @)" if message.from_user.username else "username (без @)"
    text = (
        "Ласкаво просимо до Telegram Marketplace!\n\n"
        "Тут можна відкрити мініапку та отримувати красиві повідомлення про нові запити на покупку.\n\n"
        f"Для входу через логін вводь username так: {username_hint}"
    )
    await message.answer(text, reply_markup=keyboard)


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
