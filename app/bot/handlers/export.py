from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, BufferedInputFile

from app.database import AsyncSessionLocal
from app.services.export import generate_csv_exports

router = Router()


@router.message(Command("export"))
async def cmd_export(message: Message):
    await message.answer("⏳ Формирую CSV-отчёты...")
    async with AsyncSessionLocal() as session:
        tx_bytes, goal_bytes = await generate_csv_exports(session)

    tx_file = BufferedInputFile(tx_bytes, filename="transactions.csv")
    goal_file = BufferedInputFile(goal_bytes, filename="goals.csv")

    await message.answer_document(tx_file, caption="📊 Все операции")
    await message.answer_document(goal_file, caption="🎯 Все цели")
