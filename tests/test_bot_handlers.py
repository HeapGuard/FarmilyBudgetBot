import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import date
from decimal import Decimal

from app.database import init_db
from app.bot.handlers.start import cmd_start, cmd_help, cmd_privacy
from app.bot.handlers.add import cmd_add
from app.bot.handlers.export import cmd_export
from app.bot.handlers.insights import cmd_insights


@pytest.mark.asyncio
async def test_cmd_start_and_help():
    await init_db()
    msg = MagicMock()
    msg.from_user.id = 12345
    msg.from_user.username = "testuser"
    msg.from_user.first_name = "Test"
    msg.from_user.last_name = None
    msg.answer = AsyncMock()

    await cmd_start(msg)
    assert msg.answer.called

    msg.answer.reset_mock()
    await cmd_help(msg)
    assert msg.answer.called

    msg.answer.reset_mock()
    await cmd_privacy(msg)
    assert msg.answer.called


@pytest.mark.asyncio
async def test_cmd_add():
    msg = MagicMock()
    msg.answer = AsyncMock()

    await cmd_add(msg)
    assert msg.answer.called


@pytest.mark.asyncio
async def test_cmd_export():
    await init_db()
    msg = MagicMock()
    msg.from_user.id = 12345
    msg.answer = AsyncMock()
    msg.answer_document = AsyncMock()

    await cmd_export(msg)
    assert msg.answer_document.called


@pytest.mark.asyncio
async def test_cmd_insights():
    await init_db()
    msg = MagicMock()
    msg.answer = AsyncMock()

    from app.database import AsyncSessionLocal
    async with AsyncSessionLocal() as session:
        await cmd_insights(msg, session=session)
    assert msg.answer.called
