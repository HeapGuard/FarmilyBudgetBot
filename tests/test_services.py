import pytest
from datetime import datetime, date, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from app.database import init_db
from app.models.schemas import OperationDraftSchema
from app.services.transactions import save_draft_to_db, get_draft_from_db, confirm_draft
from app.services.notifications import notify_partner_about_transaction


@pytest.mark.asyncio
async def test_draft_save_and_get():
    await init_db()
    draft = OperationDraftSchema(
        id="test_draft_1",
        author_telegram_id=12345,
        author_name="Test",
        type="expense",
        amount=Decimal("1500.00"),
        category="Продукты",
        note="Супермаркет",
        date=date.today(),
        created_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(hours=1)
    )

    await save_draft_to_db(draft)
    fetched = await get_draft_from_db("test_draft_1")
    assert fetched is not None
    assert fetched.id == "test_draft_1"
    assert fetched.amount == Decimal("1500.00")
    assert fetched.category == "Продукты"


@pytest.mark.asyncio
async def test_draft_confirm_flow():
    await init_db()
    draft = OperationDraftSchema(
        id="test_draft_2",
        author_telegram_id=12345,
        author_name="Test",
        type="expense",
        amount=Decimal("250.00"),
        category="Кофе",
        note="Утренний эспрессо",
        date=date.today(),
        created_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(hours=1)
    )

    await save_draft_to_db(draft)
    tx, goal_name, transfer_info, budget_warning = await confirm_draft(draft)

    assert tx.id is not None
    assert tx.amount == Decimal("250.00")
    assert tx.category == "Кофе"

    # Verify draft was deleted after confirmation
    fetched = await get_draft_from_db("test_draft_2")
    assert fetched is None


@pytest.mark.asyncio
async def test_notify_partner_high_expense():
    bot = MagicMock()
    bot.send_message = AsyncMock()

    draft = OperationDraftSchema(
        id="test_draft_large",
        author_telegram_id=1001,
        author_name="Анна",
        type="expense",
        amount=Decimal("7500.00"),
        category="Покупки",
        date=date.today(),
        created_at=datetime.utcnow(),
        expires_at=datetime.utcnow()
    )

    from app.config import settings
    settings.RAW_ALLOWED_TELEGRAM_IDS = "1001,2002"

    await notify_partner_about_transaction(bot, draft)
    bot.send_message.assert_called_once()
    args, kwargs = bot.send_message.call_args
    assert args[0] == 2002
    assert "Анна" in args[1]
    assert "7 500" in args[1]
