import pytest
from decimal import Decimal
from datetime import date, timedelta
from app.database import AsyncSessionLocal, init_db
from app.models.db import Transaction
from app.services.categories import get_subcategory
from app.services.intelligence import (
    calculate_autopilot_50_30_20,
    check_outlier_transaction,
    calculate_payday_and_runway,
    get_expense_trends
)


def test_autopilot_50_30_20():
    res = calculate_autopilot_50_30_20(Decimal("100000.00"))
    assert res["needs_50"] == Decimal("50000.00")
    assert res["wants_30"] == Decimal("30000.00")
    assert res["savings_20"] == Decimal("20000.00")


def test_subcategories():
    sub1 = get_subcategory("Продукты", "купил продукты в Пятёрочке")
    assert sub1 == "Супермаркеты"

    sub2 = get_subcategory("Кафе и рестораны", "выпил латте в кофейне")
    assert sub2 == "Кофейни"

    sub3 = get_subcategory("Транспорт", "яндекс такси до дома")
    assert sub3 == "Такси"


@pytest.mark.asyncio
async def test_intelligence_service():
    await init_db()

    async with AsyncSessionLocal() as session:
        # Create normal transactions in Cafe
        for _ in range(5):
            session.add(Transaction(
                author_telegram_id=12345,
                type="expense",
                amount=Decimal("500.00"),
                category="Кафе и рестораны",
                date=date.today(),
                source="test"
            ))
        await session.commit()

    async with AsyncSessionLocal() as session:
        # Check outlier
        outlier = await check_outlier_transaction(session, "Кафе и рестораны", Decimal("5000.00"))
        assert outlier is not None
        assert outlier["ratio"] >= 2.0

        # Check normal transaction (not outlier)
        normal = await check_outlier_transaction(session, "Кафе и рестораны", Decimal("600.00"))
        assert normal is None

        # Check runway & payday
        runway = await calculate_payday_and_runway(session, Decimal("50000.00"))
        assert runway["current_balance"] == Decimal("50000.00")
        assert runway["runway_days"] > 0

        # Check trends
        trends = await get_expense_trends(session, 30)
        assert len(trends["dates"]) > 0
        assert sum(trends["amounts"]) > 0
