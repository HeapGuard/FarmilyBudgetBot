import os
import logging
from typing import AsyncGenerator
from sqlalchemy import event
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text, select, func, update

from app.config import settings

logger = logging.getLogger(__name__)

# Ensure target directory exists for sqlite file
if settings.DATABASE_URL.startswith("sqlite+aiosqlite:///"):
    db_path = settings.DATABASE_URL.replace("sqlite+aiosqlite:///", "")
    dir_name = os.path.dirname(db_path)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    future=True
)


# Enable SQLite WAL mode on connect
@event.listens_for(engine.sync_engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()


AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
        # Auto-migrate missing columns for SQLite
        for query in [
            "ALTER TABLE transactions ADD COLUMN subcategory VARCHAR(255)",
            "ALTER TABLE users ADD COLUMN timezone VARCHAR(50) DEFAULT 'Europe/Moscow'",
            "ALTER TABLE users ADD COLUMN last_reminder_date DATE",
            "ALTER TABLE users ADD COLUMN last_payday_reminder_date DATE",
            "ALTER TABLE transactions ADD COLUMN account_id INTEGER",
            "ALTER TABLE transactions ADD COLUMN target_account_id INTEGER",
            "ALTER TABLE users ADD COLUMN last_sub_check_date DATE",
            "ALTER TABLE users ADD COLUMN personal_starting_balance NUMERIC(15,2) DEFAULT 0.00"
        ]:
            try:
                await conn.execute(text(query))
            except Exception:
                pass

    # Seed accounts if empty
    async with AsyncSessionLocal() as session:
        from app.models.db import Account, Transaction
        from app.services.accounts import get_setting_val
        from decimal import Decimal

        acc_stmt = select(func.count(Account.id))
        acc_count = (await session.execute(acc_stmt)).scalar()
        if acc_count == 0:
            logger.info("⚙️ Seeding default accounts database...")
            # 1. Main balance calculation
            raw_start = await get_setting_val(session, "starting_balance", "0.00")
            start_bal = Decimal(raw_start)

            stmt_inc = select(func.coalesce(func.sum(Transaction.amount), 0)).where(Transaction.type == "income")
            total_inc = Decimal(str((await session.execute(stmt_inc)).scalar()))

            stmt_exp = select(func.coalesce(func.sum(Transaction.amount), 0)).where(Transaction.type == "expense")
            total_exp = Decimal(str((await session.execute(stmt_exp)).scalar()))

            main_bal = start_bal + total_inc - total_exp

            # Create default card
            main_card = Account(
                name="Карта Т-Банк",
                type="card",
                balance=main_bal,
                is_active=True
            )
            session.add(main_card)
            await session.flush()  # get main_card.id

            # Update all existing transactions to use this card
            await session.execute(
                update(Transaction).values(account_id=main_card.id)
            )

            # 2. Savings account settings
            savings_enabled = (await get_setting_val(session, "savings_enabled", "true")).lower() == "true"
            savings_bal = Decimal(await get_setting_val(session, "savings_balance", "0.00"))
            savings_apy_val = float(await get_setting_val(session, "savings_apy", "0.0"))
            if savings_bal > 0 or savings_enabled:
                savings_acc = Account(
                    name="Накопительный счет",
                    type="savings",
                    balance=savings_bal,
                    apy=savings_apy_val,
                    is_active=savings_enabled
                )
                session.add(savings_acc)

            # 3. Deposit account settings
            deposit_enabled = (await get_setting_val(session, "deposit_enabled", "true")).lower() == "true"
            deposit_bal = Decimal(await get_setting_val(session, "deposit_balance", "0.00"))
            deposit_apy_val = float(await get_setting_val(session, "deposit_apy", "0.0"))
            deposit_months_val = int(await get_setting_val(session, "deposit_months", "12"))
            if deposit_bal > 0 or deposit_enabled:
                deposit_acc = Account(
                    name="Вклад",
                    type="deposit",
                    balance=deposit_bal,
                    apy=deposit_apy_val,
                    months=deposit_months_val,
                    is_active=deposit_enabled
                )
                session.add(deposit_acc)

            await session.commit()
            logger.info("⚙️ Default accounts seeded successfully!")
