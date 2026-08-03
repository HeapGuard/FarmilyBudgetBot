from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy.ext.asyncio import AsyncSession
from decimal import Decimal

from app.services.intelligence import calculate_autopilot_50_30_20

router = Router()


@router.message(Command("autopilot", "503020", "autop"))
async def cmd_autopilot(message: Message, session: AsyncSession):
    """
    Команда /autopilot — правило 50/30/20 для распределения дохода
    Анализирует последние поступления и предлагает план распределения
    """
    from sqlalchemy import select, func, desc
    from app.models.db import Transaction
    
    # Get last income transaction
    stmt = select(Transaction).where(
        Transaction.type == "income"
    ).order_by(desc(Transaction.date), desc(Transaction.id)).limit(1)
    
    res = await session.execute(stmt)
    last_income_tx = res.scalar_one_or_none()
    
    if not last_income_tx:
        text = (
            "🤖 **Autopilot 50/30/20**\n\n"
            "Не найдено доходов в истории.\n"
            "Добавьте доход, чтобы получить рекомендацию по распределению!"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить доход", callback_data="btn_add_income")]
        ])
        await message.answer(text, reply_markup=kb, parse_mode="Markdown")
        return
    
    income_amount = last_income_tx.amount
    income_date = last_income_tx.date
    income_note = last_income_tx.note or "Доход"
    
    # Calculate 50/30/20 split
    split = calculate_autopilot_50_30_20(income_amount)
    
    lines = [
        f"🤖 **Autopilot: Правило 50/30/20**\n",
        f"💰 **Последний доход:** {income_amount:,.0f} ₽ ({income_note})\n",
        f"📅 **Дата:** {income_date.strftime('%d.%m.%Y')}\n",
        "\n─────────────────\n",
        f"📊 **Рекомендуемое распределение:**\n",
        f"\n",
        f"🛠 **50% — Обязательные расходы:** {split['needs_50']:,.0f} ₽\n",
        f"   • Продукты, ЖКХ, транспорт, связь\n",
        f"\n",
        f"🎯 **30% — Желания:** {split['wants_30']:,.0f} ₽\n",
        f"   • Развлечения, рестораны, хобби\n",
        f"\n",
        f"📈 **20% — Накопления:** {split['savings_20']:,.0f} ₽\n",
        f"   • Подушка безопасности, инвестиции, цели\n",
        "\n─────────────────\n",
        f"💡 *Совет:* Настройте автоперевод {split['savings_20']:,.0f} ₽ на накопительный счёт в день зарплаты!"
    ]
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎯 Создать цель накопления", callback_data="btn_goals")],
        [InlineKeyboardButton(text="📊 Отчёт", callback_data="btn_report")]
    ])
    
    await message.answer("\n".join(lines), reply_markup=kb, parse_mode="Markdown")
