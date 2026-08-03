import pytest
from decimal import Decimal
from datetime import date
from app.database import AsyncSessionLocal, init_db
from app.services.qr_decoder import parse_fns_qr_string
from app.services.budgets import (
    set_category_budget,
    get_category_budgets,
    check_budget_warning,
    calculate_financial_runway
)


def test_fns_qr_parsing():
    qr_str = "t=20260803T153000&s=1250.50&fn=9999078900012345&i=12345&fp=678901234&n=1"
    amount, receipt_date, note = parse_fns_qr_string(qr_str)
    assert amount == Decimal("1250.50")
    assert receipt_date == date(2026, 8, 3)
    assert "Покупка по чеку" in note


@pytest.mark.asyncio
async def test_category_budgets_and_warnings():
    await init_db()
    async with AsyncSessionLocal() as session:
        await set_category_budget(session, "Кафе и рестораны", Decimal("10000.00"))
        await session.commit()

    async with AsyncSessionLocal() as session:
        budgets = await get_category_budgets(session)
        assert budgets.get("Кафе и рестораны") == Decimal("10000.00")

        # Test warning when adding 8500 (85%)
        warning = await check_budget_warning(session, "Кафе и рестораны", Decimal("8500.00"))
        assert warning is not None
        assert "85%" in warning or "Внимание" in warning


@pytest.mark.asyncio
async def test_financial_runway_calc():
    await init_db()
    async with AsyncSessionLocal() as session:
        runway = await calculate_financial_runway(session, Decimal("300000.00"))
        assert isinstance(runway, float)
        assert runway >= 0.0
