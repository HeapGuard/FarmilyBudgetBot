import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from aiogram import Bot, Dispatcher
from aiogram.types import Update

from app.config import settings
from app.database import init_db
from app.bot.bot import create_bot, create_dispatcher
from app.web.routes import router as web_router
from app.services.cron import start_cron_scheduler

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

bot: Bot = None
dp: Dispatcher = None
polling_task: asyncio.Task = None
cron_task: asyncio.Task = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global bot, dp, polling_task, cron_task

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
                
                # Start cron scheduler for reminders and reports
                logger.info("Starting cron scheduler for automated tasks...")
                cron_task = asyncio.create_task(start_cron_scheduler(bot))
                
            elif settings.MODE == "webhook":
                webhook_url = f"{settings.BASE_URL.rstrip('/')}{settings.WEBHOOK_PATH}"
                logger.info(f"Setting Telegram Webhook to {webhook_url}...")
                await bot.set_webhook(
                    url=webhook_url,
                    secret_token=settings.WEBHOOK_SECRET,
                    drop_pending_updates=True
                )
                
                # Start cron scheduler for reminders and reports
                logger.info("Starting cron scheduler for automated tasks...")
                cron_task = asyncio.create_task(start_cron_scheduler(bot))
        except Exception as e:
            logger.error(f"⚠️ Ошибка авторизации Telegram Бота: {e}")
            logger.error("Проверь валидность BOT_TOKEN в файле .env (получи актуальный токен у @BotFather)!")

    yield

    # Shutdown
    if cron_task:
        cron_task.cancel()
        try:
            await cron_task
        except asyncio.CancelledError:
            pass

    if settings.MODE == "polling" and polling_task:
        polling_task.cancel()
        try:
            await polling_task
        except asyncio.CancelledError:
            pass

    if bot and bot.session:
        await bot.session.close()
    logger.info("Application shutdown complete.")


# Hide API docs in production
app = FastAPI(
    title="Family Budget Bot",
    description="Telegram Bot + Mini Web App for personal family budget tracking",
    lifespan=lifespan,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    openapi_url="/openapi.json" if settings.DEBUG else None,
)

# CORS — restrict to known origins only
allowed_origins = [settings.BASE_URL]
if settings.DEBUG:
    allowed_origins.extend(["http://localhost:8000", "http://127.0.0.1:8000"])

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
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
