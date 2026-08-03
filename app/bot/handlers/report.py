from datetime import date
from decimal import Decimal
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from sqlalchemy import select, func, desc

from app.database import AsyncSessionLocal
from app.models.db import Transaction

router = Router()


async def build_monthly_report_text() -> str:
    today = date.today()
    first_day = today.replace(day=1)
    month_names = [
        "", "январь", "февраль", "март", "апрель", "май", "июнь",
        "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь"
    ]
    cur_month_name = month_names[today.month]

    async with AsyncSessionLocal() as session:
        stmt = select(Transaction).where(Transaction.date >= first_day).order_by(desc(Transaction.date), desc(Transaction.id))
        res = await session.execute(stmt)
        txs = list(res.scalars().all())

        income = sum((tx.amount for tx in txs if tx.type == "income"), Decimal("0"))
        expense = sum((tx.amount for tx in txs if tx.type == "expense"), Decimal("0"))
        free = income - expense
        savings_rate = (free / income * 100) if income > 0 else Decimal("0")

        cat_map = {}
        for tx in txs:
            if tx.type == "expense" and tx.category:
                cat_map[tx.category] = cat_map.get(tx.category, Decimal("0")) + tx.amount

        sorted_cats = sorted(cat_map.items(), key=lambda x: x[1], reverse=True)[:5]
        recent_5 = txs[:5]

    cats_text = "\n".join([f"  • {cat}: {amt:,.0f} ₽".replace(",", " ") for cat, amt in sorted_cats]) if sorted_cats else "  • Нет расходов"

    recent_text_list = []
    type_emoji = {"expense": "➖", "income": "➕", "transfer": "🔄", "goal_contribution": "🎯"}
    for tx in recent_5:
        em = type_emoji.get(tx.type, "•")
        cat = f" ({tx.category})" if tx.category else ""
        recent_text_list.append(f"  {em} {tx.date.strftime('%d.%m')} {tx.amount:,.0f} ₽ — {tx.note or 'Без описания'}{cat}".replace(",", " "))
    recent_text = "\n".join(recent_text_list) if recent_text_list else "  • Нет операций"

    report = (
        f"📊 <b>Отчёт за {cur_month_name.capitalize()} {today.year}:</b>\n\n"
        f"📈 <b>Доходы:</b> {income:,.0f} ₽\n".replace(",", " ") +
        f"📉 <b>Расходы:</b> {expense:,.0f} ₽\n".replace(",", " ") +
        f"💰 <b>Свободно:</b> {free:,.0f} ₽\n".replace(",", " ") +
        f"📊 <b>Норма сбережения:</b> {savings_rate:.1f}%\n\n"
        f"🔝 <b>Топ-5 категорий расходов:</b>\n{cats_text}\n\n"
        f"🕒 <b>Последние операции:</b>\n{recent_text}"
    )
    return report


@router.message(Command("report"))
async def cmd_report(message: Message):
    text = await build_monthly_report_text()
    await message.answer(text)


@router.callback_query(F.data == "btn_report")
async def cb_report(callback: CallbackQuery):
    text = await build_monthly_report_text()
    await callback.message.answer(text)
    await callback.answer()
