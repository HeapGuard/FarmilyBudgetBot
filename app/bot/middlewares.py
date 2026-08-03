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
