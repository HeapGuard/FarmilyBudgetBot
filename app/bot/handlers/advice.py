from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery

from app.database import AsyncSessionLocal
from app.models.db import AdviceLog
from app.services.advice import get_advice

router = Router()


@router.message(Command("advice"))
async def cmd_advice(message: Message):
    async with AsyncSessionLocal() as session:
        advice_text = await get_advice(session)
        # Log advice in advice_logs
        log = AdviceLog(
            author_telegram_id=message.from_user.id,
            advice_text=advice_text
        )
        session.add(log)
        await session.commit()

    await message.answer(advice_text)


@router.callback_query(F.data == "btn_advice")
async def cb_advice(callback: CallbackQuery):
    async with AsyncSessionLocal() as session:
        advice_text = await get_advice(session)
        log = AdviceLog(
            author_telegram_id=callback.from_user.id,
            advice_text=advice_text
        )
        session.add(log)
        await session.commit()

    await callback.message.answer(advice_text)
    await callback.answer()
