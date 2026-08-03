import os
from typing import AsyncGenerator
from sqlalchemy import event
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

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
        try:
            await conn.execute(__import__("sqlalchemy").text("ALTER TABLE transactions ADD COLUMN subcategory VARCHAR(255)"))
        except Exception:
            pass  # Column already exists

    # Auto-seed initial defaults if database is empty
    async with AsyncSessionLocal() as session:
        from decimal import Decimal
        from datetime import date, timedelta
        from sqlalchemy import select, func
        from app.models.db import Setting, Transaction, Goal

        # 1. Default Account Settings
        try:
            stmt_set = select(func.count(Setting.key))
            set_count = (await session.execute(stmt_set)).scalar()
            if set_count == 0:
                default_settings = [
                    Setting(key="starting_balance", value="150000.00"),
                    Setting(key="savings_balance", value="50000.00"),
                    Setting(key="savings_apy", value="14.0"),
                    Setting(key="savings_enabled", value="true"),
                    Setting(key="deposit_balance", value="200000.00"),
                    Setting(key="deposit_apy", value="16.5"),
                    Setting(key="deposit_months", value="12"),
                    Setting(key="deposit_enabled", value="true"),
                ]
                session.add_all(default_settings)

            # 2. Initial Sample Transactions
            stmt_tx = select(func.count(Transaction.id))
            tx_count = (await session.execute(stmt_tx)).scalar()
            if tx_count == 0:
                today = date.today()
                sample_txs = [
                    Transaction(author_telegram_id=1, type="income", amount=Decimal("150000.00"), category="Зарплата", note="Пополнение баланса и зарплата", date=today - timedelta(days=2), source="initial", confidence=1.0),
                    Transaction(author_telegram_id=1, type="expense", amount=Decimal("12400.00"), category="Продукты", note="Супермаркет Перекресток", date=today - timedelta(days=1), source="initial", confidence=1.0),
                    Transaction(author_telegram_id=1, type="expense", amount=Decimal("3500.00"), category="Кафе и рестораны", note="Ужин в семейном кафе", date=today, source="initial", confidence=1.0),
                    Transaction(author_telegram_id=1, type="expense", amount=Decimal("1990.00"), category="Подписки", note="Яндекс Плюс и Кинопоиск", date=today - timedelta(days=3), source="initial", confidence=1.0),
                    Transaction(author_telegram_id=1, type="expense", amount=Decimal("2800.00"), category="Транспорт", note="Заправка АЗС Лукойл", date=today - timedelta(days=4), source="initial", confidence=1.0),
                ]
                session.add_all(sample_txs)

            # 3. Initial Financial Goals
            stmt_g = select(func.count(Goal.id))
            g_count = (await session.execute(stmt_g)).scalar()
            if g_count == 0:
                sample_goals = [
                    Goal(title="Летний отпуск 🏖️", target_amount=Decimal("150000.00"), current_amount=Decimal("65000.00"), status="active"),
                    Goal(title="Подушка безопасности 🛡️", target_amount=Decimal("300000.00"), current_amount=Decimal("180000.00"), status="active")
                ]
                session.add_all(sample_goals)

            await session.commit()
        except Exception as e:
            await session.rollback()
            print(f"Init DB seed notice: {e}")
