import pytest
from decimal import Decimal
from app.database import AsyncSessionLocal, init_db
from app.services.accounts import get_accounts_info, set_setting_val


@pytest.mark.asyncio
async def test_accounts_info_and_settings():
    await init_db()

    async with AsyncSessionLocal() as session:
        from app.models.db import Account
        from sqlalchemy import delete
        await session.execute(delete(Account))
        
        # Set settings for accounts
        main_acc = Account(name="Основной", type="card", balance=Decimal("50000.00"), is_active=True)
        savings_acc = Account(name="Накопительный", type="savings", balance=Decimal("100000.00"), apy=Decimal("12.0"), is_active=True)
        deposit_acc = Account(name="Вклад", type="deposit", balance=Decimal("200000.00"), apy=Decimal("18.0"), months=12, is_active=True)
        session.add_all([main_acc, savings_acc, deposit_acc])
        await session.commit()

    async with AsyncSessionLocal() as session:
        accounts, main_bal, total_capital, passive_inc = await get_accounts_info(session)

        savings_acc = next(a for a in accounts if a.type == "savings")
        assert savings_acc.balance == Decimal("100000.00")
        assert savings_acc.apy == 12.0
        assert savings_acc.enabled is True
        assert savings_acc.monthly_interest == Decimal("1000.00")

        deposit_acc = next(a for a in accounts if a.type == "deposit")
        assert deposit_acc.balance == Decimal("200000.00")
        assert deposit_acc.enabled is True

        assert total_capital == main_bal + Decimal("100000.00") + Decimal("200000.00")
        # 1,000 (savings) + 3,000 (deposit per month) = 4,000
        assert passive_inc == Decimal("4000.00")

    # Disable deposit account
    async with AsyncSessionLocal() as session:
        from sqlalchemy import select
        stmt = select(Account).where(Account.type == "deposit")
        dep_db = (await session.execute(stmt)).scalars().first()
        dep_db.is_active = False
        await session.commit()

    async with AsyncSessionLocal() as session:
        accounts, main_bal, total_capital, passive_inc = await get_accounts_info(session)
        deposit_acc = next((a for a in accounts if a.type == "deposit"), None)
        assert deposit_acc is None
        assert total_capital == main_bal + Decimal("100000.00")
        assert passive_inc == Decimal("1000.00")


@pytest.mark.asyncio
async def test_account_transfers():
    await init_db()
    async with AsyncSessionLocal() as session:
        from app.models.db import Account
        from sqlalchemy import delete
        await session.execute(delete(Account))
        
        main_acc = Account(name="Основной", type="card", balance=Decimal("50000.00"), is_active=True)
        savings_acc = Account(name="Накопительный", type="savings", balance=Decimal("10000.00"), is_active=True)
        session.add_all([main_acc, savings_acc])
        await session.commit()

    # Simulate transfer of 5000 from main to savings
    async with AsyncSessionLocal() as session:
        from sqlalchemy import select
        from app.models.db import Account
        stmt1 = select(Account).where(Account.type == "card")
        stmt2 = select(Account).where(Account.type == "savings")
        main_acc = (await session.execute(stmt1)).scalars().first()
        savings_acc = (await session.execute(stmt2)).scalars().first()
        
        main_acc.balance -= Decimal("5000")
        savings_acc.balance += Decimal("5000")
        await session.commit()

    async with AsyncSessionLocal() as session:
        accounts, main_bal, total_capital, _ = await get_accounts_info(session)
        sav_acc = next(a for a in accounts if a.type == "savings")
        assert sav_acc.balance == Decimal("15000.00")

