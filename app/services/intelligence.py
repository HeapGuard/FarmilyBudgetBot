from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional, List, Dict, Any
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import Transaction, User


async def auto_detect_recurring_micro_expenses(session: AsyncSession, days: int = 30) -> List[Dict[str, Any]]:
    start_date = date.today() - timedelta(days=days)
    stmt = select(Transaction).where(
        Transaction.type == "expense",
        Transaction.date >= start_date
    )
    res = await session.execute(stmt)
    txs = list(res.scalars().all())

    # Group micro-expenses (< 1000 RUB, e.g., coffee, snacks)
    grouped: Dict[str, List[Decimal]] = {}
    for tx in txs:
        note_clean = (tx.note or tx.category or "Трата").strip()
        if note_clean not in grouped:
            grouped[note_clean] = []
        grouped[note_clean].append(tx.amount)

    insights = []
    for name, amounts in grouped.items():
        if len(amounts) >= 4:
            total_spent = sum(amounts)
            monthly_est = (total_spent / Decimal(str(days))) * Decimal("30")
            insights.append({
                "name": name,
                "count": len(amounts),
                "total_spent": total_spent,
                "monthly_estimate": monthly_est.quantize(Decimal("0.00")),
                "message": f"«{name}» ({len(amounts)} раз за {days} дней) обходится вам в ~{monthly_est:,.0f} ₽/мес"
            })
    return sorted(insights, key=lambda x: x["monthly_estimate"], reverse=True)


async def check_outlier_transaction(session: AsyncSession, category: Optional[str], amount: Decimal) -> Optional[Dict[str, Any]]:
    if not category:
        return None

    ninety_days_ago = date.today() - timedelta(days=90)
    stmt = select(func.avg(Transaction.amount), func.count(Transaction.id)).where(
        Transaction.type == "expense",
        Transaction.category == category,
        Transaction.date >= ninety_days_ago
    )
    res = await session.execute(stmt)
    row = res.first()
    if not row or not row[0] or row[1] < 3:
        return None

    avg_check = Decimal(str(row[0]))
    if amount > (avg_check * Decimal("2.0")):
        ratio = float(amount / avg_check) if avg_check > 0 else 2.0
        return {
            "category": category,
            "amount": amount,
            "avg_check": avg_check.quantize(Decimal("0.01")),
            "ratio": round(ratio, 1),
            "message": f"⚠️ Аномальный расход в категории «{category}»: {amount:,.0f} ₽. Ваш средний чек: ~{avg_check:,.0f} ₽ (в {ratio:.1f}x раз больше)."
        }
    return None


async def calculate_payday_and_runway(session: AsyncSession, current_balance: Decimal) -> Dict[str, Any]:
    today = date.today()
    thirty_days_ago = today - timedelta(days=30)
    
    # Calculate average daily expense over last 30 days
    stmt = select(func.sum(Transaction.amount)).where(
        Transaction.type == "expense",
        Transaction.date >= thirty_days_ago
    )
    res = await session.execute(stmt)
    total_30d_spent = res.scalar() or Decimal("0.00")
    daily_avg = (total_30d_spent / Decimal("30")).quantize(Decimal("0.01"))

    runway_days = float((current_balance / daily_avg).quantize(Decimal("0.1"))) if daily_avg > 0 else 999.0

    # Auto-detect payday (search for income transactions in last 60 days)
    sixty_days_ago = today - timedelta(days=60)
    stmt_inc = select(Transaction).where(
        Transaction.type == "income",
        Transaction.date >= sixty_days_ago
    ).order_by(Transaction.date.desc())
    res_inc = await session.execute(stmt_inc)
    incomes = list(res_inc.scalars().all())

    income_days = [inc.date.day for inc in incomes]
    next_payday_days_left = 15  # Default estimate

    if income_days:
        # Find nearest upcoming income day of month
        possible_dates = []
        for d in set(income_days):
            day_clamped = min(d, 28)
            try:
                candidate = date(today.year, today.month, day_clamped)
                if candidate <= today:
                    m = today.month + 1 if today.month < 12 else 1
                    y = today.year if today.month < 12 else today.year + 1
                    candidate = date(y, m, day_clamped)
                possible_dates.append(candidate)
            except ValueError:
                pass
        if possible_dates:
            nearest = min(possible_dates)
            next_payday_days_left = (nearest - today).days

    is_warning = runway_days < next_payday_days_left

    return {
        "current_balance": current_balance,
        "daily_avg_expense": daily_avg,
        "runway_days": runway_days,
        "days_to_payday": next_payday_days_left,
        "is_warning": is_warning,
        "message": (
            f"⚠️ При текущем темпе трат ({daily_avg:,.0f} ₽/день) денег хватит на {runway_days:.1f} дней, "
            f"а до зарплаты — ~{next_payday_days_left} дней."
            if is_warning else
            f"📅 До зарплаты ~{next_payday_days_left} дней. Денег хватит на ~{runway_days:.1f} дней ✅"
        )
    }


def calculate_autopilot_50_30_20(income_amount: Decimal) -> Dict[str, Any]:
    needs_50 = (income_amount * Decimal("0.50")).quantize(Decimal("0.01"))
    wants_30 = (income_amount * Decimal("0.30")).quantize(Decimal("0.01"))
    savings_20 = (income_amount * Decimal("0.20")).quantize(Decimal("0.01"))

    return {
        "income": income_amount,
        "needs_50": needs_50,
        "wants_30": wants_30,
        "savings_20": savings_20,
        "message": (
            f"💰 Поступил доход {income_amount:,.0f} ₽.\n"
            f"Рекомендация 50/30/20:\n"
            f"• 🛠 Расходы (50%): {needs_50:,.0f} ₽\n"
            f"• 🎯 Свободные (30%): {wants_30:,.0f} ₽\n"
            f"• 📈 Накопления (20%): {savings_20:,.0f} ₽\n"
            f"Отложить {savings_20:,.0f} ₽ в накопления?"
        )
    }


async def calculate_personal_inflation(session: AsyncSession, author_id: Optional[int] = None) -> Dict[str, Any]:
    today = date.today()
    curr_first = today.replace(day=1)

    # Previous month first and last day
    if curr_first.month == 1:
        prev_first = curr_first.replace(year=curr_first.year - 1, month=12)
    else:
        prev_first = curr_first.replace(month=curr_first.month - 1)

    prev_last = curr_first - timedelta(days=1)

    # Fetch previous month category sums
    stmt_prev = select(Transaction.category, func.sum(Transaction.amount)).where(
        Transaction.type == "expense",
        Transaction.date >= prev_first,
        Transaction.date <= prev_last
    )
    if author_id:
        stmt_prev = stmt_prev.where(Transaction.author_telegram_id == author_id)
    stmt_prev = stmt_prev.group_by(Transaction.category)

    res_prev = await session.execute(stmt_prev)
    prev_by_cat = {row[0] or "Без категории": Decimal(str(row[1])) for row in res_prev.all()}

    # Fetch current month category sums
    stmt_curr = select(Transaction.category, func.sum(Transaction.amount)).where(
        Transaction.type == "expense",
        Transaction.date >= curr_first
    )
    if author_id:
        stmt_curr = stmt_curr.where(Transaction.author_telegram_id == author_id)
    stmt_curr = stmt_curr.group_by(Transaction.category)

    res_curr = await session.execute(stmt_curr)
    curr_by_cat = {row[0] or "Без категории": Decimal(str(row[1])) for row in res_curr.all()}

    total_prev = sum(prev_by_cat.values())
    total_curr = sum(curr_by_cat.values())

    categories_diff = []
    all_cats = set(prev_by_cat.keys()) | set(curr_by_cat.keys())
    for cat in all_cats:
        p_val = prev_by_cat.get(cat, Decimal("0.00"))
        c_val = curr_by_cat.get(cat, Decimal("0.00"))
        if p_val > 0:
            diff_pct = float(((c_val - p_val) / p_val) * Decimal("100"))
        else:
            diff_pct = 100.0 if c_val > 0 else 0.0
        categories_diff.append({
            "category": cat,
            "prev_amount": float(p_val),
            "curr_amount": float(c_val),
            "diff_pct": round(diff_pct, 1)
        })

    overall_inflation = float(((total_curr - total_prev) / total_prev) * Decimal("100")) if total_prev > 0 else 0.0

    return {
        "prev_month_total": float(total_prev),
        "curr_month_total": float(total_curr),
        "overall_inflation_pct": round(overall_inflation, 1),
        "categories": sorted(categories_diff, key=lambda x: x["curr_amount"], reverse=True)
    }


async def get_author_spending_breakdown(session: AsyncSession, days: int = 30) -> List[Dict[str, Any]]:
    start_date = date.today() - timedelta(days=days)
    stmt = select(
        Transaction.author_telegram_id,
        func.sum(Transaction.amount)
    ).where(
        Transaction.type == "expense",
        Transaction.date >= start_date
    ).group_by(Transaction.author_telegram_id)
    
    res = await session.execute(stmt)
    rows = res.all()
    
    total = sum(r[1] for r in rows) if rows else Decimal("0.00")
    breakdown = []

    # Get user names from DB
    stmt_users = select(User)
    u_res = await session.execute(stmt_users)
    user_map = {u.telegram_id: u.first_name or u.username or str(u.telegram_id) for u in u_res.scalars().all()}

    for author_id, amount in rows:
        pct = float((amount / total) * Decimal("100")) if total > 0 else 0.0
        name = user_map.get(author_id, f"Пользователь {author_id}")
        breakdown.append({
            "author_id": author_id,
            "author_name": name,
            "amount": float(amount),
            "percentage": round(pct, 1)
        })
    return breakdown


async def get_expense_trends(session: AsyncSession, period_days: int = 90, author_id: Optional[int] = None) -> Dict[str, Any]:
    start_date = date.today() - timedelta(days=period_days)
    stmt = select(
        Transaction.date,
        func.sum(Transaction.amount)
    ).where(
        Transaction.type == "expense",
        Transaction.date >= start_date
    )
    if author_id:
        stmt = stmt.where(Transaction.author_telegram_id == author_id)
    stmt = stmt.group_by(Transaction.date).order_by(Transaction.date.asc())

    res = await session.execute(stmt)
    rows = res.all()

    dates = [r[0].strftime("%Y-%m-%d") for r in rows]
    amounts = [float(r[1]) for r in rows]

    return {
        "dates": dates,
        "amounts": amounts,
        "period_days": period_days
    }
