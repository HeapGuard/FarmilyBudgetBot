from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional, List, Dict, Any
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import Subscription, Transaction
from app.models.schemas import SubscriptionCreateSchema, SubscriptionUpdateSchema


def compute_next_billing_date(billing_day: int, period: str, relative_to: Optional[date] = None) -> date:
    today = relative_to or date.today()
    target_day = min(max(1, billing_day), 28)
    
    if period == "yearly":
        next_date = date(today.year, today.month, target_day)
        if next_date <= today:
            next_date = date(today.year + 1, today.month, target_day)
        return next_date
    elif period == "quarterly":
        # Every 3 months
        next_date = date(today.year, today.month, target_day)
        if next_date <= today:
            month = today.month + 3
            year = today.year
            if month > 12:
                month -= 12
                year += 1
            next_date = date(year, month, target_day)
        return next_date
    else:  # monthly
        next_date = date(today.year, today.month, target_day)
        if next_date <= today:
            month = today.month + 1
            year = today.year
            if month > 12:
                month = 1
                year += 1
            next_date = date(year, month, target_day)
        return next_date


async def get_all_subscriptions(session: AsyncSession) -> List[Subscription]:
    result = await session.execute(select(Subscription).order_by(Subscription.billing_day.asc()))
    return list(result.scalars().all())


async def get_active_subscriptions(session: AsyncSession) -> List[Subscription]:
    result = await session.execute(
        select(Subscription).where(Subscription.is_active == True).order_by(Subscription.billing_day.asc())
    )
    return list(result.scalars().all())


async def create_subscription(session: AsyncSession, data: SubscriptionCreateSchema) -> Subscription:
    next_billing = compute_next_billing_date(data.billing_day, data.period)
    sub = Subscription(
        name=data.name.strip(),
        amount=data.amount,
        currency=data.currency,
        period=data.period,
        billing_day=data.billing_day,
        category=data.category,
        is_active=True,
        next_billing=next_billing,
        created_at=datetime.now(timezone.utc)
    )
    session.add(sub)
    await session.commit()
    await session.refresh(sub)
    return sub


async def update_subscription(session: AsyncSession, sub_id: int, data: SubscriptionUpdateSchema) -> Optional[Subscription]:
    sub = await session.get(Subscription, sub_id)
    if not sub:
        return None

    if data.name is not None:
        sub.name = data.name.strip()
    if data.amount is not None:
        sub.amount = data.amount
    if data.period is not None:
        sub.period = data.period
    if data.billing_day is not None:
        sub.billing_day = data.billing_day
    if data.category is not None:
        sub.category = data.category
    if data.is_active is not None:
        sub.is_active = data.is_active

    sub.next_billing = compute_next_billing_date(sub.billing_day, sub.period)
    await session.commit()
    await session.refresh(sub)
    return sub


async def delete_subscription(session: AsyncSession, sub_id: int) -> bool:
    sub = await session.get(Subscription, sub_id)
    if not sub:
        return False
    await session.delete(sub)
    await session.commit()
    return True


def calculate_subscriptions_summary(subscriptions: List[Subscription]) -> Dict[str, Any]:
    active_subs = [s for s in subscriptions if s.is_active]
    monthly_total = Decimal("0.00")
    yearly_total = Decimal("0.00")

    for s in active_subs:
        amount = Decimal(str(s.amount))
        if s.period == "yearly":
            yearly_total += amount
            monthly_total += (amount / Decimal("12")).quantize(Decimal("0.01"))
        elif s.period == "quarterly":
            yearly_total += amount * Decimal("4")
            monthly_total += (amount / Decimal("3")).quantize(Decimal("0.01"))
        else:  # monthly
            monthly_total += amount
            yearly_total += amount * Decimal("12")

    return {
        "count": len(active_subs),
        "total_monthly": monthly_total,
        "total_yearly": yearly_total,
        "subscriptions": active_subs
    }


async def get_due_reminders(session: AsyncSession, days_ahead: int = 2) -> List[Subscription]:
    today = date.today()
    target_date = today + timedelta(days=days_ahead)
    
    result = await session.execute(
        select(Subscription).where(
            Subscription.is_active == True,
            Subscription.next_billing <= target_date,
            Subscription.next_billing >= today
        )
    )
    return list(result.scalars().all())


async def auto_detect_subscriptions(session: AsyncSession) -> List[Dict[str, Any]]:
    from app.services.accounts import get_setting_val
    import json
    blacklist_raw = await get_setting_val(session, "sub_blacklist", "[]")
    try:
        blacklist = json.loads(blacklist_raw)
        if not isinstance(blacklist, list):
            blacklist = []
    except Exception:
        blacklist = []
    blacklist = [item.strip().lower() for item in blacklist]

    ninety_days_ago = date.today() - timedelta(days=90)
    stmt = select(Transaction).where(
        Transaction.type == "expense",
        Transaction.date >= ninety_days_ago
    )
    result = await session.execute(stmt)
    txs = list(result.scalars().all())

    # Group by note or category
    candidates: Dict[str, List[Transaction]] = {}
    for tx in txs:
        key = (tx.note or tx.category or "Расход").strip().lower()
        if key in blacklist:
            continue
        if key not in candidates:
            candidates[key] = []
        candidates[key].append(tx)

    detected = []
    for key, tx_group in candidates.items():
        if len(tx_group) >= 2:
            amounts = [tx.amount for tx in tx_group]
            # If amounts are similar/identical
            if max(amounts) == min(amounts):
                sample = tx_group[0]
                detected.append({
                    "name": sample.note or sample.category or "Регулярный платеж",
                    "amount": sample.amount,
                    "count": len(tx_group),
                    "suggested_billing_day": sample.date.day,
                    "category": sample.category or "Подписки"
                })

    return detected
