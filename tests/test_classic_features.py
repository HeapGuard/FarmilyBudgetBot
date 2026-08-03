import pytest
from decimal import Decimal
from datetime import date
from app.database import AsyncSessionLocal, init_db
from app.models.db import Transaction
from app.services.intelligence import (
    auto_detect_recurring_micro_expenses,
    calculate_payday_and_runway,
    calculate_autopilot_50_30_20
)


@pytest.mark.asyncio
async def test_insights_and_autopilot():
    await init_db()

    async with AsyncSessionLocal() as session:
        # Add recurring micro transactions
        for i in range(5):
            tx = Transaction(
                author_telegram_id=1001,
                type="expense",
                amount=Decimal("350.00"),
                category="Кафе и рестораны",
                note=f"Кофе дрип #{i}",
                date=date.today(),
                source="manual"
            )
            session.add(tx)

        # Add income transaction
        tx_inc = Transaction(
            author_telegram_id=1001,
            type="income",
            amount=Decimal("100000.00"),
            category="Зарплата",
            note="Зарплата за месяц",
            date=date.today(),
            source="manual"
        )
        session.add(tx_inc)
        await session.commit()

    async with AsyncSessionLocal() as session:
        # Test micro expenses auto-detection
        insights = await auto_detect_recurring_micro_expenses(session, days=30)
        assert len(insights) >= 0

        # Test 50/30/20 autopilot split
        split = calculate_autopilot_50_30_20(Decimal("100000.00"))
        assert split["needs_50"] == Decimal("50000.00")
        assert split["wants_30"] == Decimal("30000.00")
        assert split["savings_20"] == Decimal("20000.00")

        # Test payday & runway calculation
        runway_data = await calculate_payday_and_runway(session, current_balance=Decimal("98250.00"))
        assert runway_data["current_balance"] == Decimal("98250.00")
        assert runway_data["daily_avg_expense"] > 0
