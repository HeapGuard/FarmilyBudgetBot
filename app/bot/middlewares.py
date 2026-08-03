import time
from collections import defaultdict
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from app.config import settings


class AccessMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        user_id = None
        if isinstance(event, Message) and event.from_user:
            user_id = event.from_user.id
        elif isinstance(event, CallbackQuery) and event.from_user:
            user_id = event.from_user.id

        if not settings.ALLOWED_TELEGRAM_IDS or user_id in settings.ALLOWED_TELEGRAM_IDS:
            return await handler(event, data)

        # Reject unauthorized access
        if isinstance(event, Message):
            await event.answer("Доступ запрещён.")
        elif isinstance(event, CallbackQuery):
            await event.answer("Доступ запрещён.", show_alert=True)
        return None


class RateLimitMiddleware(BaseMiddleware):
    """
    Simple in-memory rate limiter.
    Limits each user to MAX_REQUESTS messages per WINDOW_SECONDS.
    """
    MAX_REQUESTS = 30  # max messages per window
    WINDOW_SECONDS = 60  # window size in seconds

    def __init__(self):
        super().__init__()
        # user_id -> list of timestamps
        self._user_requests: Dict[int, list] = defaultdict(list)

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        user_id = None
        if isinstance(event, Message) and event.from_user:
            user_id = event.from_user.id
        elif isinstance(event, CallbackQuery) and event.from_user:
            user_id = event.from_user.id

        if user_id is not None:
            now = time.monotonic()
            # Clean expired entries
            self._user_requests[user_id] = [
                t for t in self._user_requests[user_id]
                if now - t < self.WINDOW_SECONDS
            ]

            if len(self._user_requests[user_id]) >= self.MAX_REQUESTS:
                if isinstance(event, Message):
                    await event.answer("⏳ Слишком много запросов. Подождите минуту.")
                elif isinstance(event, CallbackQuery):
                    await event.answer("⏳ Слишком много запросов.", show_alert=True)
                return None

            self._user_requests[user_id].append(now)

        return await handler(event, data)
