import pytest
from decimal import Decimal
from app.database import AsyncSessionLocal, init_db
from app.services.accounts import get_accounts_info, set_setting_val


@pytest.mark.asyncio
async def test_accounts_info_and_settings():
    await init_db()

    async with AsyncSessionLocal() as session:
        # Set settings for accounts
        await set_setting_val(session, "starting_balance", "50000.00")
        await set_setting_val(session, "savings_balance", "100000.00")
        await set_setting_val(session, "savings_apy", "12.0")
        await set_setting_val(session, "savings_enabled", "true")
        await set_setting_val(session, "deposit_balance", "200000.00")
        await set_setting_val(session, "deposit_apy", "18.0")
        await set_setting_val(session, "deposit_months", "12")
        await set_setting_val(session, "deposit_enabled", "true")
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
        await set_setting_val(session, "deposit_enabled", "false")
        await session.commit()

    async with AsyncSessionLocal() as session:
        accounts, main_bal, total_capital, passive_inc = await get_accounts_info(session)
        deposit_acc = next(a for a in accounts if a.type == "deposit")
        assert deposit_acc.enabled is False
        assert total_capital == main_bal + Decimal("100000.00")
        assert passive_inc == Decimal("1000.00")


@pytest.mark.asyncio
async def test_account_transfers():
    await init_db()
    async with AsyncSessionLocal() as session:
        await set_setting_val(session, "starting_balance", "50000.00")
        await set_setting_val(session, "savings_balance", "10000.00")
        await session.commit()

    # Simulate transfer of 5000 from main to savings
    async with AsyncSessionLocal() as session:
        from app.services.accounts import get_setting_val
        start_bal = Decimal(await get_setting_val(session, "starting_balance", "0")) - Decimal("5000")
        sav_bal = Decimal(await get_setting_val(session, "savings_balance", "0")) + Decimal("5000")
        await set_setting_val(session, "starting_balance", str(start_bal))
        await set_setting_val(session, "savings_balance", str(sav_bal))
        await session.commit()

    async with AsyncSessionLocal() as session:
        accounts, main_bal, total_capital, _ = await get_accounts_info(session)
        sav_acc = next(a for a in accounts if a.type == "savings")
        assert sav_acc.balance == Decimal("15000.00")

