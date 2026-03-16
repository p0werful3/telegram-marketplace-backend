import asyncio
import os
from urllib.request import Request, urlopen
import json

from aiogram import Bot, Dispatcher
from aiogram.types import Message, KeyboardButton, ReplyKeyboardMarkup, WebAppInfo
from aiogram.filters import CommandStart
from aiohttp import web

TOKEN = os.getenv("BOT_TOKEN") or "8648644673:AAE4-xVguaXoTSdaHkzGa3uL2bciuIc6wR8"
WEBAPP_URL = os.getenv("WEBAPP_URL") or "https://p0werful3.github.io/telegram-marketplace-miniapp/?v=278"
API_URL = os.getenv("API_URL") or "https://telegram-marketplace-api.onrender.com"

bot = Bot(token=TOKEN)
dp = Dispatcher()

web_app = WebAppInfo(url=WEBAPP_URL)

keyboard = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="🛍 Відкрити маркетплейс", web_app=web_app)]],
    resize_keyboard=True
)


def sync_telegram_user(message: Message) -> None:
    payload = {
        "telegram_id": str(message.from_user.id),
        "username": (message.from_user.username or f"tg_{message.from_user.id}").strip(),
        "full_name": (message.from_user.full_name or "").strip() or None,
        "init_data": None,
    }
    try:
        request = Request(
            f"{API_URL}/auth/telegram",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=10) as response:
            print(f"Telegram auth sync status: {getattr(response, 'status', 'ok')}")
    except Exception as error:
        print(f"Telegram auth sync error: {error}")


@dp.message(CommandStart())
async def start_handler(message: Message):
    await asyncio.to_thread(sync_telegram_user, message)
    await message.answer(
        "Ласкаво просимо до Telegram Marketplace!\n\nТут можна відкрити мініапку та отримувати повідомлення про нові запити на покупку.",
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
