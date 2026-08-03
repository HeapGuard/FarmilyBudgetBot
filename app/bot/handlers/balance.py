from datetime import date
from decimal import Decimal
from typing import Tuple
from aiogram import Router, F
from aiogram.filters import Command, CommandObject
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select, func

from app.database import AsyncSessionLocal
from app.models.db import Setting, Transaction
from app.services.accounts import get_accounts_info, set_setting_val
from app.bot.keyboards import get_accounts_keyboard, get_main_reply_keyboard

router = Router()


class SetBalanceStates(StatesGroup):
    waiting_for_amount = State()


class AccountSetupStates(StatesGroup):
    waiting_for_main_bal = State()
    waiting_for_savings_bal = State()
    waiting_for_savings_apy = State()
    waiting_for_deposit_bal = State()
    waiting_for_deposit_apy = State()
    waiting_for_deposit_months = State()


async def calculate_current_balance(session) -> Tuple[Decimal, Decimal, Decimal]:
    accounts, main_bal, total_capital, _ = await get_accounts_info(session)

    first_day = date.today().replace(day=1)
    stmt_m_inc = select(func.coalesce(func.sum(Transaction.amount), 0)).where(
        Transaction.type == "income", Transaction.date >= first_day
    )
    res_m_inc = await session.execute(stmt_m_inc)
    month_income = Decimal(str(res_m_inc.scalar()))

    stmt_m_exp = select(func.coalesce(func.sum(Transaction.amount), 0)).where(
        Transaction.type == "expense", Transaction.date >= first_day
    )
    res_m_exp = await session.execute(stmt_m_exp)
    month_expense = Decimal(str(res_m_exp.scalar()))

    return main_bal, month_income, month_expense


@router.message(Command("balance"))
async def cmd_balance(message: Message):
    async with AsyncSessionLocal() as session:
        accounts, main_bal, total_capital, total_passive_income = await get_accounts_info(session)
        _, m_inc, m_exp = await calculate_current_balance(session)

    text_lines = [
        f"💰 <b>Общий капитал семьи:</b> {total_capital:,.0f} ₽\n".replace(",", " "),
        f"💳 <b>Основной счёт (Карта/Нал):</b> {main_bal:,.0f} ₽".replace(",", " "),
    ]

    sav = next((a for a in accounts if a.type == "savings"), None)
    if sav and sav.enabled:
        sav_str = f"📈 <b>Накопительный счёт:</b> {sav.balance:,.0f} ₽".replace(",", " ")
        if sav.apy > 0:
            sav_str += f" ({sav.apy}% APY, ~+{sav.monthly_interest:,.0f} ₽/мес)".replace(",", " ")
        text_lines.append(sav_str)

    dep = next((a for a in accounts if a.type == "deposit"), None)
    if dep and dep.enabled:
        dep_str = f"🔒 <b>Вклад:</b> {dep.balance:,.0f} ₽".replace(",", " ")
        if dep.apy > 0:
            dep_str += f" ({dep.apy}% на {dep.months} мес, итог ~{dep.projected_total:,.0f} ₽)".replace(",", " ")
        text_lines.append(dep_str)

    if total_passive_income > 0:
        text_lines.append(f"💸 <b>Пассивный доход по процентам:</b> ~+{total_passive_income:,.0f} ₽/мес".replace(",", " "))

    text_lines.extend([
        f"\n📈 Доходы за месяц: {m_inc:,.0f} ₽".replace(",", " "),
        f"📉 Расходы за месяц: {m_exp:,.0f} ₽".replace(",", " ")
    ])

    await message.answer("\n".join(text_lines), reply_markup=get_main_reply_keyboard())


@router.message(Command("accounts"))
async def cmd_accounts(message: Message):
    async with AsyncSessionLocal() as session:
        accounts, main_bal, total_capital, _ = await get_accounts_info(session)

    sav_acc = accounts[1]
    dep_acc = accounts[2]

    sav_txt = f"{sav_acc.balance:,.0f} ₽ ({sav_acc.apy}% APY)" if sav_acc.enabled else "⚪ Не используется"
    dep_txt = f"{dep_acc.balance:,.0f} ₽ ({dep_acc.apy}%, {dep_acc.months} мес)" if dep_acc.enabled else "⚪ Не используется"

    text = (
        "🏦 <b>Управление счетами и накоплениями:</b>\n\n"
        f"1️⃣ <b>Основной счёт:</b> {main_bal:,.0f} ₽\n"
        f"2️⃣ <b>Накопительный счёт:</b> {sav_txt}\n"
        f"3️⃣ <b>Вклад:</b> {dep_txt}\n\n"
        "Выбери счёт для настройки или отключи неиспользуемые:"
    ).replace(",", " ")
    await message.answer(text, reply_markup=get_accounts_keyboard(sav_acc.enabled, dep_acc.enabled))


@router.callback_query(F.data == "btn_accounts")
async def cb_accounts(callback: CallbackQuery):
    async with AsyncSessionLocal() as session:
        accounts, main_bal, total_capital, _ = await get_accounts_info(session)

    sav_acc = accounts[1]
    dep_acc = accounts[2]

    sav_txt = f"{sav_acc.balance:,.0f} ₽ ({sav_acc.apy}% APY)" if sav_acc.enabled else "⚪ Не используется"
    dep_txt = f"{dep_acc.balance:,.0f} ₽ ({dep_acc.apy}%, {dep_acc.months} мес)" if dep_acc.enabled else "⚪ Не используется"

    text = (
        "🏦 <b>Управление счетами и накоплениями:</b>\n\n"
        f"1️⃣ <b>Основной счёт:</b> {main_bal:,.0f} ₽\n"
        f"2️⃣ <b>Накопительный счёт:</b> {sav_txt}\n"
        f"3️⃣ <b>Вклад:</b> {dep_txt}\n\n"
        "Выбери счёт для настройки или отключи неиспользуемые:"
    ).replace(",", " ")
    await callback.message.answer(text, reply_markup=get_accounts_keyboard(sav_acc.enabled, dep_acc.enabled))
    await callback.answer()


@router.callback_query(F.data == "toggle_acc_savings")
async def cb_toggle_acc_savings(callback: CallbackQuery):
    async with AsyncSessionLocal() as session:
        accounts, _, _, _ = await get_accounts_info(session)
        sav_acc = accounts[1]
        new_val = "false" if sav_acc.enabled else "true"
        await set_setting_val(session, "savings_enabled", new_val)
        await session.commit()
    await cb_accounts(callback)


@router.callback_query(F.data == "toggle_acc_deposit")
async def cb_toggle_acc_deposit(callback: CallbackQuery):
    async with AsyncSessionLocal() as session:
        accounts, _, _, _ = await get_accounts_info(session)
        dep_acc = accounts[2]
        new_val = "false" if dep_acc.enabled else "true"
        await set_setting_val(session, "deposit_enabled", new_val)
        await session.commit()
    await cb_accounts(callback)



@router.callback_query(F.data == "edit_acc_main")
async def cb_edit_acc_main(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AccountSetupStates.waiting_for_main_bal)
    await callback.message.answer("Пришли начальный баланс основного счёта в рублях (например, 50000):")
    await callback.answer()


@router.message(AccountSetupStates.waiting_for_main_bal)
async def proc_main_bal(message: Message, state: FSMContext):
    try:
        val = Decimal(message.text.strip().replace(",", ".").replace(" ", ""))
        if val < 0:
            await message.answer("Баланс не может быть отрицательным.")
            return
        async with AsyncSessionLocal() as session:
            await set_setting_val(session, "starting_balance", str(val))
            await session.commit()
        await state.clear()
        await message.answer(f"✅ Баланс основного счёта сохранён: {val:,.0f} ₽".replace(",", " "), reply_markup=get_main_reply_keyboard())
    except Exception:
        await message.answer("Пожалуйста, введи число, например: 50000")


@router.callback_query(F.data == "edit_acc_savings")
async def cb_edit_acc_savings(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AccountSetupStates.waiting_for_savings_bal)
    await callback.message.answer("1/2: Введи баланс накопительного счёта в рублях (например, 100000):")
    await callback.answer()


@router.message(AccountSetupStates.waiting_for_savings_bal)
async def proc_savings_bal(message: Message, state: FSMContext):
    try:
        val = Decimal(message.text.strip().replace(",", ".").replace(" ", ""))
        if val < 0:
            await message.answer("Баланс не может быть отрицательным.")
            return
        await state.update_data(savings_bal=str(val))
        await state.set_state(AccountSetupStates.waiting_for_savings_apy)
        await message.answer("2/2: Введи годовую процентную ставку накопительного счёта в % APY (например, 16.5):")
    except Exception:
        await message.answer("Пожалуйста, введи число, например: 100000")


@router.message(AccountSetupStates.waiting_for_savings_apy)
async def proc_savings_apy(message: Message, state: FSMContext):
    try:
        apy_val = float(message.text.strip().replace(",", ".").replace(" ", ""))
        if apy_val < 0 or apy_val > 100:
            await message.answer("Ставка должна быть от 0 до 100%.")
            return
        data = await state.get_data()
        sav_bal = data.get("savings_bal", "0")
        async with AsyncSessionLocal() as session:
            await set_setting_val(session, "savings_balance", sav_bal)
            await set_setting_val(session, "savings_apy", str(apy_val))
            await session.commit()
        await state.clear()
        await message.answer(f"✅ Накопительный счёт сохранён! Баланс: {Decimal(sav_bal):,.0f} ₽, Ставка: {apy_val}% APY".replace(",", " "), reply_markup=get_main_reply_keyboard())
    except Exception:
        await message.answer("Пожалуйста, введи процентную ставку, например: 16.5")


@router.callback_query(F.data == "edit_acc_deposit")
async def cb_edit_acc_deposit(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AccountSetupStates.waiting_for_deposit_bal)
    await callback.message.answer("1/3: Введи баланс вклада в рублях (например, 300000):")
    await callback.answer()


@router.message(AccountSetupStates.waiting_for_deposit_bal)
async def proc_deposit_bal(message: Message, state: FSMContext):
    try:
        val = Decimal(message.text.strip().replace(",", ".").replace(" ", ""))
        if val < 0:
            await message.answer("Баланс не может быть отрицательным.")
            return
        await state.update_data(deposit_bal=str(val))
        await state.set_state(AccountSetupStates.waiting_for_deposit_apy)
        await message.answer("2/3: Введи годовую процентную ставку вклада в % APY (например, 18.0):")
    except Exception:
        await message.answer("Пожалуйста, введи число, например: 300000")


@router.message(AccountSetupStates.waiting_for_deposit_apy)
async def proc_deposit_apy(message: Message, state: FSMContext):
    try:
        apy_val = float(message.text.strip().replace(",", ".").replace(" ", ""))
        if apy_val < 0 or apy_val > 100:
            await message.answer("Ставка должна быть от 0 до 100%.")
            return
        await state.update_data(deposit_apy=str(apy_val))
        await state.set_state(AccountSetupStates.waiting_for_deposit_months)
        await message.answer("3/3: Введи срок вклада в месяцах (например, 12):")
    except Exception:
        await message.answer("Пожалуйста, введи процентную ставку, например: 18.0")


@router.message(AccountSetupStates.waiting_for_deposit_months)
async def proc_deposit_months(message: Message, state: FSMContext):
    try:
        months_val = int(message.text.strip())
        if months_val <= 0 or months_val > 120:
            await message.answer("Срок должен быть от 1 до 120 месяцев.")
            return
        data = await state.get_data()
        dep_bal = data.get("deposit_bal", "0")
        dep_apy = data.get("deposit_apy", "0")
        async with AsyncSessionLocal() as session:
            await set_setting_val(session, "deposit_balance", dep_bal)
            await set_setting_val(session, "deposit_apy", dep_apy)
            await set_setting_val(session, "deposit_months", str(months_val))
            await session.commit()
        await state.clear()
        await message.answer(
            f"✅ Вклад сохранён! Сумма: {Decimal(dep_bal):,.0f} ₽, Ставка: {dep_apy}%, Срок: {months_val} мес.".replace(",", " "),
            reply_markup=get_main_reply_keyboard()
        )
    except Exception:
        await message.answer("Пожалуйста, введи целое число месяцев, например: 12")


@router.message(Command("set_balance"))
async def cmd_set_balance(message: Message, command: CommandObject, state: FSMContext):
    if command.args:
        try:
            raw_val = command.args.replace(",", ".").replace(" ", "")
            val = Decimal(raw_val)
            if val < 0:
                await message.answer("Стартовый баланс не может быть отрицательным.")
                return
            async with AsyncSessionLocal() as session:
                await set_setting_val(session, "starting_balance", str(val))
                await session.commit()
            await message.answer(f"✅ Стартовый баланс сохранён: {val:,.0f} ₽".replace(",", " "), reply_markup=get_main_reply_keyboard())
            return
        except Exception:
            pass

    await state.set_state(SetBalanceStates.waiting_for_amount)
    await message.answer("Пришли стартовый баланс основного счёта в рублях, например: 50000")


@router.message(SetBalanceStates.waiting_for_amount)
async def process_set_balance(message: Message, state: FSMContext):
    try:
        raw_val = message.text.strip().replace(",", ".").replace(" ", "")
        val = Decimal(raw_val)
        if val < 0:
            await message.answer("Стартовый баланс не может быть отрицательным. Попробуй ещё раз.")
            return
        async with AsyncSessionLocal() as session:
            await set_setting_val(session, "starting_balance", str(val))
            await session.commit()
        await state.clear()
        await message.answer(f"✅ Стартовый баланс сохранён: {val:,.0f} ₽".replace(",", " "), reply_markup=get_main_reply_keyboard())
    except Exception:
        await message.answer("Пожалуйста, введи только число, например: 50000")

