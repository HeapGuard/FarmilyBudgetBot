from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from app.database import AsyncSessionLocal
from app.services.budgets import get_category_budgets_summary, set_category_budget
from app.services.categories import EXPENSE_CATEGORIES
from app.bot.keyboards import get_main_reply_keyboard

router = Router()


class BudgetSetupStates(StatesGroup):
    waiting_for_category = State()
    waiting_for_limit = State()


def get_categories_budget_keyboard() -> InlineKeyboardMarkup:
    buttons = []
    row = []
    for idx, cat in enumerate(EXPENSE_CATEGORIES):
        row.append(InlineKeyboardButton(text=cat, callback_data=f"setb_cat_{idx}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="btn_main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.message(Command("budgets"))
async def cmd_budgets(message: Message):
    async with AsyncSessionLocal() as session:
        budgets = await get_category_budgets_summary(session)

    if not budgets:
        text = (
            "📊 <b>Бюджеты по категориям не настроены.</b>\n\n"
            "Установи лимиты трат на месяц (например, 15 000 ₽ на Кафе и рестораны), "
            "чтобы получать предупреждения при перерасходе."
        )
    else:
        text_lines = ["📊 <b>Лимиты бюджетов на месяц:</b>\n"]
        for b in budgets:
            status = "🟢" if b.percentage < 80 else ("🟡" if b.percentage <= 100 else "🔴")
            text_lines.append(
                f"{status} <b>{b.category}:</b> {b.spent:,.0f} ₽ из {b.limit:,.0f} ₽ ({b.percentage:.0f}%)".replace(",", " ")
            )
        text = "\n".join(text_lines)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Настроить лимит категории", callback_data="btn_add_budget")],
        [InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="btn_main_menu")]
    ])
    await message.answer(text, reply_markup=kb)


@router.callback_query(F.data == "btn_add_budget")
async def cb_add_budget(callback: CallbackQuery):
    await callback.message.answer(
        "Выбери категорию для установки лимита на месяц:",
        reply_markup=get_categories_budget_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data.startswith("setb_cat_"))
async def cb_pick_cat(callback: CallbackQuery, state: FSMContext):
    idx = int(callback.data.split("setb_cat_")[1])
    cat = EXPENSE_CATEGORIES[idx]
    await state.update_data(target_category=cat)
    await state.set_state(BudgetSetupStates.waiting_for_limit)
    await callback.message.answer(f"Введи ежемесячный лимит трат для категории «<b>{cat}</b>» в рублях (например, 15000):")
    await callback.answer()


@router.message(BudgetSetupStates.waiting_for_limit)
async def proc_limit(message: Message, state: FSMContext):
    from decimal import Decimal
    try:
        val = Decimal(message.text.strip().replace(",", ".").replace(" ", ""))
        if val <= 0:
            await message.answer("Лимит должен быть больше 0.")
            return
        data = await state.get_data()
        cat = data.get("target_category", "Прочее")
        async with AsyncSessionLocal() as session:
            await set_category_budget(session, cat, val)
            await session.commit()
        await state.clear()
        await message.answer(f"✅ Лимит для категории «<b>{cat}</b>» сохранён: {val:,.0f} ₽/мес.".replace(",", " "), reply_markup=get_main_reply_keyboard())
    except Exception:
        await message.answer("Пожалуйста, введи число, например: 15000")
