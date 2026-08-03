import pytest
from decimal import Decimal
from datetime import date
from app.database import AsyncSessionLocal, init_db
from app.models.schemas import SubscriptionCreateSchema, SubscriptionUpdateSchema
from app.services.subscriptions import (
    create_subscription,
    get_all_subscriptions,
    get_active_subscriptions,
    update_subscription,
    delete_subscription,
    calculate_subscriptions_summary,
    compute_next_billing_date
)


@pytest.mark.asyncio
async def test_subscription_crud():
    await init_db()

    async with AsyncSessionLocal() as session:
        # 1. Create subscription
        sub = await create_subscription(
            session,
            SubscriptionCreateSchema(
                name="Яндекс Плюс",
                amount=Decimal("299.00"),
                period="monthly",
                billing_day=15,
                category="Подписки"
            )
        )
        assert sub.id is not None
        assert sub.name == "Яндекс Плюс"
        assert sub.amount == Decimal("299.00")

    async with AsyncSessionLocal() as session:
        # 2. Get active subscriptions
        subs = await get_active_subscriptions(session)
        assert len(subs) >= 1
        found = next(s for s in subs if s.name == "Яндекс Плюс")
        assert found.billing_day == 15

        # 3. Calculate summary
        summary = calculate_subscriptions_summary(subs)
        assert summary["total_monthly"] >= Decimal("299.00")
        assert summary["total_yearly"] >= Decimal("3588.00")

    async with AsyncSessionLocal() as session:
        # 4. Update subscription
        subs = await get_all_subscriptions(session)
        target = next(s for s in subs if s.name == "Яндекс Плюс")
        updated = await update_subscription(
            session,
            target.id,
            SubscriptionUpdateSchema(amount=Decimal("399.00"))
        )
        assert updated.amount == Decimal("399.00")

    async with AsyncSessionLocal() as session:
        # 5. Delete subscription
        subs = await get_all_subscriptions(session)
        target = next(s for s in subs if s.name == "Яндекс Плюс")
        ok = await delete_subscription(session, target.id)
        assert ok is True


def test_next_billing_date():
    today = date(2026, 8, 3)
    next_date = compute_next_billing_date(15, "monthly", relative_to=today)
    assert next_date == date(2026, 8, 15)

    next_past_day = compute_next_billing_date(2, "monthly", relative_to=today)
    assert next_past_day == date(2026, 9, 2)
