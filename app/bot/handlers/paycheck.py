from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.intelligence import calculate_payday_and_runway

router = Router()


@router.message(Command("paycheck", "payday", "salary"))
async def cmd_paycheck(message: Message, session: AsyncSession):
    """
    Команда /paycheck — прогноз «дотянуть до зарплаты»
    Показывает сколько дней хватит денег и когда следующая зарплата
    """
    # Get current balance from last transactions
    from sqlalchemy import select, func, desc
    from app.models.db import Transaction
    
    stmt = select(func.sum(Transaction.amount)).where(
        Transaction.type == "income"
    )
    res = await session.execute(stmt)
    total_income = res.scalar() or 0
    
    stmt = select(func.sum(Transaction.amount)).where(
        Transaction.type == "expense"
    )
    res = await session.execute(stmt)
    total_expense = res.scalar() or 0
    
    current_balance = total_income - total_expense
    
    if current_balance <= 0:
        text = (
            "⚠️ **Внимание!**\n\n"
            "Ваш баланс отрицательный или нулевой.\n"
            "Пора добавить доходы или сократить расходы!"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить доход", callback_data="btn_add_income")]
        ])
        await message.answer(text, reply_markup=kb, parse_mode="Markdown")
        return
    
    # Calculate runway and payday
    data = await calculate_payday_and_runway(session, current_balance)
    
    emoji_warning = "⚠️" if data["is_warning"] else "✅"
    
    lines = [
        f"{emoji_warning} **Прогноз до зарплаты**\n",
        f"💳 **Текущий баланс:** {data['current_balance']:,.0f} ₽",
        f"📊 **Средний расход/день:** {data['daily_avg_expense']:,.0f} ₽\n",
        f"📅 **Дней до зарплаты:** ~{data['days_to_payday']}",
        f"💰 **Хватит на:** {data['runway_days']:.1f} дней\n"
    ]
    
    if data["is_warning"]:
        deficit_days = data["days_to_payday"] - data["runway_days"]
        daily_cut = data['current_balance'] / data['days_to_payday'] if data['days_to_payday'] > 0 else 0
        needed_cut = data['daily_avg_expense'] - daily_cut
        
        lines.append("─────────────────")
        lines.append(f"❗ **При текущем темпе трат денег НЕ хватит!**")
        lines.append(f"Нужно снизить расходы на ~{needed_cut:,.0f} ₽/день")
    else:
        buffer_days = data["runway_days"] - data["days_to_payday"]
        lines.append("─────────────────")
        lines.append(f"✅ Запас прочности: +{buffer_days:.0f} дней")
        lines.append("Финансы под контролем!")
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Отчёт", callback_data="btn_report")],
        [InlineKeyboardButton(text="💡 Советы по экономии", callback_data="btn_advice")]
    ])
    
    await message.answer("\n".join(lines), reply_markup=kb, parse_mode="Markdown")
