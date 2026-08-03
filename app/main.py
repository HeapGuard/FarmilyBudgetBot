import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from aiogram import Bot, Dispatcher
from aiogram.types import Update

from app.config import settings
from app.database import init_db
from app.bot.bot import create_bot, create_dispatcher
from app.web.routes import router as web_router

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

bot: Bot = None
dp: Dispatcher = None
polling_task: asyncio.Task = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global bot, dp, polling_task

    # 1. Initialize Database
    logger.info("Initializing database...")
    await init_db()

    # 2. Setup Bot & Dispatcher if token present
    if settings.BOT_TOKEN:
        bot = create_bot()
        dp = create_dispatcher()

        try:
            if settings.MODE == "polling":
                logger.info("Starting Telegram Bot in POLLING mode...")
                await bot.delete_webhook(drop_pending_updates=True)
                polling_task = asyncio.create_task(dp.start_polling(bot))
            elif settings.MODE == "webhook":
                webhook_url = f"{settings.BASE_URL.rstrip('/')}{settings.WEBHOOK_PATH}"
                logger.info(f"Setting Telegram Webhook to {webhook_url}...")
                await bot.set_webhook(
                    url=webhook_url,
                    secret_token=settings.WEBHOOK_SECRET,
                    drop_pending_updates=True
                )
        except Exception as e:
            logger.error(f"⚠️ Ошибка авторизации Telegram Бота: {e}")
            logger.error("Проверь валидность BOT_TOKEN в файле .env (получи актуальный токен у @BotFather)!")

    yield

    # Shutdown
    if settings.MODE == "polling" and polling_task:
        polling_task.cancel()
        try:
            await polling_task
        except asyncio.CancelledError:
            pass

    if bot and bot.session:
        await bot.session.close()
    logger.info("Application shutdown complete.")


app = FastAPI(
    title="Family Budget Bot",
    description="Telegram Bot + Mini Web App for personal family budget tracking",
    lifespan=lifespan
)

# Mount static directory
app.mount("/static", StaticFiles(directory="app/web/static"), name="static")

# Include Web routes
app.include_router(web_router)


@app.post(settings.WEBHOOK_PATH)
async def telegram_webhook(request: Request):
    if settings.MODE != "webhook":
        raise HTTPException(status_code=404, detail="Webhook mode not active")

    secret_header = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if secret_header != settings.WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="Invalid webhook secret token")

    data = await request.json()
    update = Update.model_validate(data, context={"bot": bot})
    await dp.feed_update(bot=bot, update=update)
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=settings.DEBUG)
