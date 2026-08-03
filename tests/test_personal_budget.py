import pytest
from decimal import Decimal
from datetime import date
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.database import AsyncSessionLocal, init_db
from app.models.db import Transaction

client = TestClient(app)


@pytest.mark.asyncio
async def test_personal_vs_family_scope():
    await init_db()

    async with AsyncSessionLocal() as session:
        # Add transaction for User 1
        t1 = Transaction(
            author_telegram_id=1001,
            type="expense",
            amount=Decimal("1500.00"),
            category="Продукты",
            note="Покупка пользователя 1",
            date=date.today(),
            source="test"
        )
        # Add transaction for User 2
        t2 = Transaction(
            author_telegram_id=2002,
            type="expense",
            amount=Decimal("3000.00"),
            category="Транспорт",
            note="Покупка пользователя 2",
            date=date.today(),
            source="test"
        )
        session.add_all([t1, t2])
        await session.commit()

    # Test summary in family scope
    res_fam = client.get("/api/summary?scope=family")
    assert res_fam.status_code == 200
    data_fam = res_fam.json()
    assert Decimal(str(data_fam["expense_month"])) >= Decimal("4500.00")

    # Test summary in personal scope
    res_pers = client.get("/api/summary?scope=personal")
    assert res_pers.status_code == 200
    data_pers = res_pers.json()
    # In debug mode default user id is 1001 or 1, so only their transactions count
    assert Decimal(str(data_pers["expense_month"])) < Decimal(str(data_fam["expense_month"]))

    # Test profile endpoint
    res_prof = client.get("/api/profile")
    assert res_prof.status_code == 200
    prof = res_prof.json()
    assert "personal_expense_month" in prof
    assert "family_share_pct" in prof
