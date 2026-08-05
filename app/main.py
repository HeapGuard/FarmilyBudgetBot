import asyncio
import logging
import time
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
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
            # Set the menu button dynamically to the current BASE_URL
            web_app_url = f"{settings.BASE_URL.rstrip('/')}/app"
            from aiogram.types import MenuButtonWebApp, WebAppInfo
            await bot.set_chat_menu_button(
                menu_button=MenuButtonWebApp(
                    text="Бюджет",
                    web_app=WebAppInfo(url=web_app_url)
                )
            )
            logger.info(f"Bot Menu Button updated to: {web_app_url}")
        except Exception as e:
            logger.warning(f"Failed to set bot menu button: {e}")

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

@app.middleware("http")
async def add_no_cache_headers(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/app") or request.url.path.startswith("/static"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


@app.middleware("http")
async def structured_request_logging_middleware(request: Request, call_next):
    request_id = str(uuid.uuid4())[:8]
    start_time = time.perf_counter()
    request.state.request_id = request_id

    response = await call_next(request)

    duration_ms = (time.perf_counter() - start_time) * 1000
    response.headers["X-Request-ID"] = request_id
    logger.info(
        f"[{request_id}] {request.method} {request.url.path} "
        f"-> status={response.status_code} duration={duration_ms:.2f}ms"
    )
    return response

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    request_id = getattr(request.state, "request_id", "unknown")
    logger.warning(f"[{request_id}] HTTP {exc.status_code} on {request.url.path}: {exc.detail}")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": "HTTPException",
            "detail": exc.detail,
            "status_code": exc.status_code,
            "request_id": request_id
        }
    )


@app.exception_handler(Exception)
async def global_unhandled_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", "unknown")
    logger.error(f"[{request_id}] Unhandled error on {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "InternalServerError",
            "detail": "An internal server error occurred." if not settings.DEBUG else str(exc),
            "request_id": request_id
        }
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
