from decimal import Decimal
from typing import Dict, Any, List, Tuple
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import Setting, Transaction
from app.models.schemas import AccountInfoSchema


async def get_setting_val(session: AsyncSession, key: str, default: str) -> str:
    stmt = select(Setting).where(Setting.key == key)
    res = await session.execute(stmt)
    s_obj = res.scalar_one_or_none()
    return s_obj.value if s_obj else default


async def set_setting_val(session: AsyncSession, key: str, value: str):
    stmt = select(Setting).where(Setting.key == key)
    res = await session.execute(stmt)
    s_obj = res.scalar_one_or_none()
    if not s_obj:
        s_obj = Setting(key=key, value=value)
        session.add(s_obj)
    else:
        s_obj.value = value


async def get_accounts_info(session: AsyncSession) -> Tuple[List[AccountInfoSchema], Decimal, Decimal, Decimal]:
    """
    Returns (list_of_accounts, main_balance, total_capital, total_passive_income_monthly).
    Main balance = starting_balance + all_time_income - all_time_expense.
    Savings balance = savings_balance (with optional APY interest calculation).
    Deposit balance = deposit_balance (with optional APY interest and term calculation).
    """
    # 1. Main balance calculation
    raw_start = await get_setting_val(session, "starting_balance", "0.00")
    start_bal = Decimal(raw_start)

    from sqlalchemy import func
    stmt_inc = select(func.coalesce(func.sum(Transaction.amount), 0)).where(Transaction.type == "income")
    total_inc = Decimal(str((await session.execute(stmt_inc)).scalar()))

    stmt_exp = select(func.coalesce(func.sum(Transaction.amount), 0)).where(Transaction.type == "expense")
    total_exp = Decimal(str((await session.execute(stmt_exp)).scalar()))

    main_bal = start_bal + total_inc - total_exp

    # 2. Savings account settings
    savings_enabled = (await get_setting_val(session, "savings_enabled", "true")).lower() == "true"
    savings_bal = Decimal(await get_setting_val(session, "savings_balance", "0.00"))
    savings_apy_val = float(await get_setting_val(session, "savings_apy", "0.0"))
    savings_monthly_interest = (savings_bal * Decimal(str(savings_apy_val)) / Decimal("100") / Decimal("12")) if (savings_enabled and savings_apy_val > 0) else Decimal("0.00")

    # 3. Deposit account settings
    deposit_enabled = (await get_setting_val(session, "deposit_enabled", "true")).lower() == "true"
    deposit_bal = Decimal(await get_setting_val(session, "deposit_balance", "0.00"))
    deposit_apy_val = float(await get_setting_val(session, "deposit_apy", "0.0"))
    deposit_months_val = int(await get_setting_val(session, "deposit_months", "12"))
    deposit_interest = (deposit_bal * Decimal(str(deposit_apy_val)) / Decimal("100") * Decimal(str(deposit_months_val)) / Decimal("12")) if (deposit_enabled and deposit_apy_val > 0) else Decimal("0.00")
    deposit_monthly_interest = (deposit_interest / Decimal(str(deposit_months_val))) if (deposit_enabled and deposit_months_val > 0) else Decimal("0.00")
    deposit_projected_total = deposit_bal + deposit_interest

    accounts = [
        AccountInfoSchema(
            name="Основной счёт",
            type="main",
            balance=main_bal,
            enabled=True,
        ),
        AccountInfoSchema(
            name="Накопительный счёт",
            type="savings",
            balance=savings_bal,
            apy=savings_apy_val,
            monthly_interest=savings_monthly_interest,
            enabled=savings_enabled,
        ),
        AccountInfoSchema(
            name="Вклад",
            type="deposit",
            balance=deposit_bal,
            apy=deposit_apy_val,
            months=deposit_months_val,
            projected_total=deposit_projected_total,
            enabled=deposit_enabled,
        ),
    ]

    total_capital = main_bal + (savings_bal if savings_enabled else Decimal("0.00")) + (deposit_bal if deposit_enabled else Decimal("0.00"))
    total_passive_income_monthly = savings_monthly_interest + deposit_monthly_interest

    return accounts, main_bal, total_capital, total_passive_income_monthly

