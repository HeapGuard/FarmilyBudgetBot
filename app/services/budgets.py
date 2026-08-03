from datetime import date, timedelta
from decimal import Decimal
from typing import Dict, List, Tuple, Optional
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import Setting, Transaction
from app.models.schemas import CategoryBudgetSchema


async def get_category_budgets(session: AsyncSession) -> Dict[str, Decimal]:
    """
    Returns dict of {category_name: limit_amount} for configured budgets.
    """
    stmt = select(Setting).where(Setting.key.like("budget_cat_%"))
    res = await session.execute(stmt)
    settings_list = res.scalars().all()
    budgets = {}
    for s in settings_list:
        cat_name = s.key.replace("budget_cat_", "")
        try:
            budgets[cat_name] = Decimal(s.value)
        except Exception:
            pass
    return budgets


async def set_category_budget(session: AsyncSession, category: str, limit: Decimal):
    key = f"budget_cat_{category}"
    stmt = select(Setting).where(Setting.key == key)
    res = await session.execute(stmt)
    s_obj = res.scalar_one_or_none()
    if not s_obj:
        s_obj = Setting(key=key, value=str(limit))
        session.add(s_obj)
    else:
        s_obj.value = str(limit)


async def get_category_budgets_summary(session: AsyncSession) -> List[CategoryBudgetSchema]:
    """
    Returns CategoryBudgetSchema list with current month spending vs limit.
    """
    budgets = await get_category_budgets(session)
    if not budgets:
        return []

    first_day = date.today().replace(day=1)
    stmt = select(Transaction.category, func.sum(Transaction.amount)).where(
        Transaction.type == "expense",
        Transaction.date >= first_day
    ).group_by(Transaction.category)

    res = await session.execute(stmt)
    spent_by_cat = {cat: Decimal(str(total)) for cat, total in res.all() if cat}

    result = []
    for cat, limit in budgets.items():
        spent = spent_by_cat.get(cat, Decimal("0.00"))
        pct = float((spent / limit * 100) if limit > 0 else 0.0)
        result.append(CategoryBudgetSchema(
            category=cat,
            limit=limit,
            spent=spent,
            percentage=round(pct, 1)
        ))
    return result


async def check_budget_warning(session: AsyncSession, category: str, amount: Decimal) -> Optional[str]:
    """
    Checks if spending 'amount' in 'category' triggers >80% or >100% budget alert.
    Returns warning text if triggered, else None.
    """
    if not category:
        return None

    key = f"budget_cat_{category}"
    stmt = select(Setting).where(Setting.key == key)
    res = await session.execute(stmt)
    s_obj = res.scalar_one_or_none()
    if not s_obj:
        return None

    try:
        limit = Decimal(s_obj.value)
        if limit <= 0:
            return None
    except Exception:
        return None

    first_day = date.today().replace(day=1)
    stmt_spent = select(func.coalesce(func.sum(Transaction.amount), 0)).where(
        Transaction.type == "expense",
        Transaction.category == category,
        Transaction.date >= first_day
    )
    spent_existing = Decimal(str((await session.execute(stmt_spent)).scalar()))
    total_after = spent_existing + amount

    pct = float(total_after / limit * 100)

    if total_after > limit:
        return f"⚠️ <b>Превышен бюджет категории «{category}»!</b>\nЛимит: {limit:,.0f} ₽, Итого с операцией: {total_after:,.0f} ₽ ({pct:.0f}%)".replace(",", " ")
    elif pct >= 80.0:
        return f"⚠️ <b>Внимание: потрачено {pct:.0f}% бюджета категории «{category}»!</b>\nЛимит: {limit:,.0f} ₽, Расход: {total_after:,.0f} ₽".replace(",", " ")

    return None


async def calculate_financial_runway(session: AsyncSession, total_capital: Decimal) -> float:
    """
    Calculates how many months of expenses total_capital can cover,
    based on average monthly expenses over the last 90 days.
    """
    ninety_days_ago = date.today() - timedelta(days=90)
    stmt_exp = select(func.coalesce(func.sum(Transaction.amount), 0)).where(
        Transaction.type == "expense",
        Transaction.date >= ninety_days_ago
    )
    total_exp_90 = Decimal(str((await session.execute(stmt_exp)).scalar()))

    # Average monthly expense (90 days = 3 months)
    avg_monthly_expense = total_exp_90 / Decimal("3") if total_exp_90 > 0 else Decimal("0.00")

    if avg_monthly_expense <= 0:
        return 99.0

    runway = float(total_capital / avg_monthly_expense)
    return round(runway, 1)
