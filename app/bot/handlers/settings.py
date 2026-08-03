from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from sqlalchemy import delete

from app.database import AsyncSessionLocal
from app.models.db import (
    Transaction, Goal, GoalContribution, OperationDraft, AdviceLog, Setting
)
from app.bot.keyboards import (
    get_delete_all_confirmation_1_keyboard,
    get_delete_all_confirmation_2_keyboard
)

router = Router()


@router.message(Command("delete_all"))
async def cmd_delete_all(message: Message):
    await message.answer(
        "⚠️ **ПРЕДУПРЕЖДЕНИЕ!**\n\n"
        "Вы хотите полностью удалить всю историю доходов, расходов, целей и настроек.\n"
        "Это действие невозможно отменить.\n\n"
        "Вы уверены?",
        reply_markup=get_delete_all_confirmation_1_keyboard()
    )


@router.callback_query(F.data == "confirm_delete_1")
async def cb_confirm_delete_1(callback: CallbackQuery):
    await callback.message.edit_text(
        "🚨 **ПОСЛЕДНЕЕ ПОДТВЕРЖДЕНИЕ!**\n\n"
        "Все операции и цели будут удалены безвозвратно.",
        reply_markup=get_delete_all_confirmation_2_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "confirm_delete_2")
async def cb_confirm_delete_2(callback: CallbackQuery):
    async with AsyncSessionLocal() as session:
        await session.execute(delete(GoalContribution))
        await session.execute(delete(Goal))
        await session.execute(delete(Transaction))
        await session.execute(delete(OperationDraft))
        await session.execute(delete(AdviceLog))
        await session.execute(delete(Setting))
        await session.commit()

    await callback.message.edit_text("💥 Все данные успешно удалены. Пользователи сохранены.")
    await callback.answer("Данные очищены!")


@router.callback_query(F.data == "cancel_delete")
async def cb_cancel_delete(callback: CallbackQuery):
    await callback.message.edit_text("❌ Удаление данных отменено.")
    await callback.answer()
