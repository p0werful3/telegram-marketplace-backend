import asyncio
import os
from aiohttp import web

MODE = os.getenv("BOT_MODE", "webhook")


async def handle(request):
    return web.json_response({
        "status": "ok",
        "mode": MODE,
        "message": "Polling bot is disabled. Telegram updates should go to /telegram/webhook on the API service.",
    })


async def main():
    app = web.Application()
    app.router.add_get("/", handle)
    app.router.add_get("/health", handle)

    port = int(os.environ.get("PORT", 10000))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

    print("Webhook mode enabled. Polling is disabled in bot.py.")
    print("Use the API service endpoint /telegram/webhook and Telegram setWebhook.")

    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    asyncio.run(main())
