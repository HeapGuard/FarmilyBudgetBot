from decimal import Decimal
from typing import Dict, Any, List, Tuple
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import date, timedelta

from app.models.db import Setting, Transaction, Account
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


async def get_user_streak(session: AsyncSession) -> int:
    streak_val = int(await get_setting_val(session, "streak_count", "0"))
    last_date_str = await get_setting_val(session, "streak_last_date", "")
    if last_date_str:
        try:
            last_date = date.fromisoformat(last_date_str)
            today = date.today()
            if (today - last_date).days > 1:
                streak_val = 0
                await set_setting_val(session, "streak_count", "0")
                await session.commit()
        except ValueError:
            pass
    return streak_val


async def record_user_activity(session: AsyncSession) -> int:
    """Updates user active streak and returns new streak count."""
    today = date.today()
    today_str = today.isoformat()

    last_date_str = await get_setting_val(session, "streak_last_date", "")
    current_streak = int(await get_setting_val(session, "streak_count", "0"))

    if last_date_str == today_str:
        return current_streak

    if last_date_str:
        try:
            last_date = date.fromisoformat(last_date_str)
            if (today - last_date).days == 1:
                current_streak += 1
            else:
                current_streak = 1
        except ValueError:
            current_streak = 1
    else:
        current_streak = 1

    await set_setting_val(session, "streak_count", str(current_streak))
    await set_setting_val(session, "streak_last_date", today_str)
    await session.commit()
    return current_streak


async def get_accounts_info(session: AsyncSession) -> Tuple[List[AccountInfoSchema], Decimal, Decimal, Decimal]:
    """
    Returns (list_of_accounts, main_balance, total_capital, total_passive_income_monthly).
    """
    # Fetch active accounts
    stmt = select(Account).where(Account.is_active == True).order_by(Account.id.asc())
    accounts_db = list((await session.execute(stmt)).scalars().all())

    card_bal = Decimal("0.00")
    total_capital = Decimal("0.00")
    total_passive_income = Decimal("0.00")

    accounts = []
    for acc in accounts_db:
        total_capital += acc.balance
        
        apy_val = acc.apy or 0.0
        months_val = acc.months or 12
        monthly_interest = Decimal("0.00")
        projected_total = acc.balance

        if acc.type == "savings":
            monthly_interest = (acc.balance * Decimal(str(apy_val)) / Decimal("100") / Decimal("12")) if apy_val > 0 else Decimal("0.00")
            total_passive_income += monthly_interest
        elif acc.type == "deposit":
            interest = (acc.balance * Decimal(str(apy_val)) / Decimal("100") * Decimal(str(months_val)) / Decimal("12")) if apy_val > 0 else Decimal("0.00")
            monthly_interest = (interest / Decimal(str(months_val))) if months_val > 0 else Decimal("0.00")
            projected_total = acc.balance + interest
            total_passive_income += monthly_interest
        else: # type == "card" or "main"
            card_bal += acc.balance

        accounts.append(
            AccountInfoSchema(
                id=acc.id,
                name=acc.name,
                type=acc.type,
                bank_name=acc.bank_name,
                balance=acc.balance,
                apy=apy_val,
                months=months_val if acc.type == "deposit" else None,
                monthly_interest=monthly_interest if acc.type in ("savings", "deposit") else None,
                projected_total=projected_total if acc.type == "deposit" else None,
                enabled=acc.is_active
            )
        )

    main_bal = card_bal if card_bal > 0 or not accounts else total_capital
    return accounts, main_bal, total_capital, total_passive_income

