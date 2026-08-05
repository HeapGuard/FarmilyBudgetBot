from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.redis import RedisStorage

from app.config import settings
from app.bot.middlewares import AccessMiddleware, RateLimitMiddleware
from app.bot.handlers import setup_routers


def create_bot() -> Bot:
    return Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )


def create_dispatcher() -> Dispatcher:
    if settings.REDIS_URL:
        storage = RedisStorage.from_url(settings.REDIS_URL)
    else:
        storage = MemoryStorage()
        
    dp = Dispatcher(storage=storage)
    # Access check first, then rate limiting (only authorized users consume slots)
    dp.message.outer_middleware(AccessMiddleware())
    dp.message.outer_middleware(RateLimitMiddleware())
    dp.callback_query.outer_middleware(AccessMiddleware())
    dp.callback_query.outer_middleware(RateLimitMiddleware())
    dp.include_router(setup_routers())
    return dp
