from datetime import date
from decimal import Decimal
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.db import Goal
from app.services.goals import required_monthly, projected_value, format_goal_progress

router = Router()


class GoalNewStates(StatesGroup):
    waiting_for_title = State()
    waiting_for_target = State()
    waiting_for_current = State()
    waiting_for_months = State()
    waiting_for_apy = State()


@router.message(Command("goals"))
async def cmd_goals(message: Message):
    async with AsyncSessionLocal() as session:
        stmt = select(Goal).where(Goal.status == "active").order_by(Goal.id.asc())
        res = await session.execute(stmt)
        goals = list(res.scalars().all())

    if not goals:
        await message.answer("У вас пока нет активных целей. Создай первую командой /goal_new!")
        return

    text_blocks = []
    for g in goals:
        months = None
        if g.deadline:
            months = (g.deadline - date.today()).days // 30
        text_blocks.append(format_goal_progress(g.title, g.target_amount, g.current_amount, months, g.apy or 0.0))

    await message.answer("\n\n---\n\n".join(text_blocks))


@router.callback_query(F.data == "btn_goals")
async def cb_goals(callback: CallbackQuery):
    async with AsyncSessionLocal() as session:
        stmt = select(Goal).where(Goal.status == "active").order_by(Goal.id.asc())
        res = await session.execute(stmt)
        goals = list(res.scalars().all())

    if not goals:
        await callback.message.answer("У вас пока нет активных целей. Создай первую командой /goal_new!")
        await callback.answer()
        return

    text_blocks = []
    for g in goals:
        months = None
        if g.deadline:
            months = (g.deadline - date.today()).days // 30
        text_blocks.append(format_goal_progress(g.title, g.target_amount, g.current_amount, months, g.apy or 0.0))

    await callback.message.answer("\n\n---\n\n".join(text_blocks))
    await callback.answer()


@router.message(Command("goal_new"))
async def cmd_goal_new(message: Message, state: FSMContext):
    await state.set_state(GoalNewStates.waiting_for_title)
    await message.answer("🎯 <b>Создание новой цели</b>\n\nШаг 1 из 5: Введи название цели (например: Отпуск, Техника, Ремонт):")


@router.message(GoalNewStates.waiting_for_title)
async def process_goal_title(message: Message, state: FSMContext):
    title = message.text.strip()
    if not title or len(title) > 100:
        await message.answer("Пожалуйста, введи понятное название цели (до 100 символов).")
        return

    await state.update_data(title=title)
    await state.set_state(GoalNewStates.waiting_for_target)
    await message.answer(f"Шаг 2 из 5: Введи целевую сумму для «{title}» в рублях (например: 300000):")


@router.message(GoalNewStates.waiting_for_target)
async def process_goal_target(message: Message, state: FSMContext):
    try:
        val = Decimal(message.text.strip().replace(",", ".").replace(" ", ""))
        if val <= 0:
            await message.answer("Целевая сумма должна быть больше 0. Попробуй ещё раз:")
            return
        await state.update_data(target_amount=str(val))
        await state.set_state(GoalNewStates.waiting_for_current)
        await message.answer("Шаг 3 из 5: Сколько уже накоплено? (введи 0, если начинаешь с нуля):")
    except Exception:
        await message.answer("Пожалуйста, введи число, например: 300000")


@router.message(GoalNewStates.waiting_for_current)
async def process_goal_current(message: Message, state: FSMContext):
    try:
        val = Decimal(message.text.strip().replace(",", ".").replace(" ", ""))
        if val < 0:
            await message.answer("Сумма накопленного не может быть отрицательной:")
            return
        await state.update_data(current_amount=str(val))
        await state.set_state(GoalNewStates.waiting_for_months)
        await message.answer("Шаг 4 из 5: На сколько месяцев рассчитываешь цель? (например: 8 или 12):")
    except Exception:
        await message.answer("Пожалуйста, введи число, например: 50000")


@router.message(GoalNewStates.waiting_for_months)
async def process_goal_months(message: Message, state: FSMContext):
    try:
        months = int(message.text.strip())
        if months <= 0 or months > 360:
            await message.answer("Срок должен быть от 1 до 360 месяцев:")
            return
        await state.update_data(months=months)
        await state.set_state(GoalNewStates.waiting_for_apy)
        await message.answer("Шаг 5 из 5: Годовая ставка в процентах (если хранишь на вкладе/накопительном счёте). Если нет — введи 0:")
    except Exception:
        await message.answer("Пожалуйста, введи целое число месяцев, например: 12")


@router.message(GoalNewStates.waiting_for_apy)
async def process_goal_apy(message: Message, state: FSMContext):
    try:
        val_str = message.text.strip().replace(",", ".").replace("%", "").replace(" ", "")
        apy = float(val_str)
        if apy < 0:
            apy = 0.0

        data = await state.get_data()
        title = data["title"]
        target = Decimal(data["target_amount"])
        current = Decimal(data["current_amount"])
        months = data["months"]

        req_monthly = required_monthly(current, target, months, apy)
        proj_val = projected_value(current, req_monthly or Decimal("0"), months, apy)

        today = date.today()
        deadline = date(today.year + (today.month + months - 1) // 12, (today.month + months - 1) % 12 + 1, min(today.day, 28))

        async with AsyncSessionLocal() as session:
            g = Goal(
                title=title,
                target_amount=target,
                current_amount=current,
                currency="RUB",
                deadline=deadline,
                apy=apy,
                monthly_contribution_plan=req_monthly,
                status="active"
            )
            session.add(g)
            await session.commit()

        await state.clear()

        req_str = f"{req_monthly:,.0f} ₽/мес".replace(",", " ") if req_monthly else "0 ₽"
        proj_str = f"{proj_val:,.0f} ₽".replace(",", " ") if proj_val else "—"

        res_text = (
            f"🎉 <b>Цель «{title}» успешно создана!</b>\n\n"
            f"🎯 Цель: {target:,.0f} ₽\n".replace(",", " ") +
            f"💰 Уже есть: {current:,.0f} ₽\n".replace(",", " ") +
            f"⏳ Срок: {months} месяцев\n"
            f"📈 Процентная ставка: {apy}%\n"
            f"📌 Требуемый ежемесячный взнос: <b>{req_str}</b>\n"
            f"🔮 Прогноз с учётом процентов: {proj_str}"
        )
        await message.answer(res_text)

    except Exception:
        await message.answer("Пожалуйста, введи число процентов, например: 16 или 0")
