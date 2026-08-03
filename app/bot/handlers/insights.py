from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.intelligence import auto_detect_recurring_micro_expenses

router = Router()


@router.message(Command("insights", "micro"))
async def cmd_insights(message: Message, session: AsyncSession):
    """
    Команда /insights — показывает инсайты по микро-расходам
    Анализирует последние 30 дней и находит повторяющиеся мелкие траты
    """
    insights = await auto_detect_recurring_micro_expenses(session, days=30)
    
    if not insights:
        text = (
            "🔍 **Анализ микро-расходов**\n\n"
            "За последние 30 дней не найдено повторяющихся мелких расходов.\n"
            "Это отличный знак — ваши траты стабильны!"
        )
        await message.answer(text, parse_mode="Markdown")
        return
    
    lines = ["📊 **Ваши микро-расходы (за 30 дней):**\n"]
    lines.append(f"Найдено {len(insights)} категорий с повторяющимися тратами:\n")
    
    for i, insight in enumerate(insights[:10], 1):
        lines.append(
            f"{i}. **{insight['name']}**\n"
            f"   • {insight['count']} раз(а) на сумму {insight['total_spent']:,.0f} ₽\n"
            f"   • 📈 В месяц: ~{insight['monthly_estimate']:,.0f} ₽\n"
        )
    
    if len(insights) > 10:
        lines.append(f"\n... и ещё {len(insights) - 10} категорий")
    
    total_monthly = sum(i['monthly_estimate'] for i in insights)
    lines.append("\n─────────────────")
    lines.append(f"💸 **Итого микро-расходы:** ~{total_monthly:,.0f} ₽/мес")
    lines.append("\n💡 *Совет:* Даже небольшие ежедневные траты могут существенно влиять на бюджет!")
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Полный отчёт", callback_data="btn_report")]
    ])
    
    await message.answer("\n".join(lines), reply_markup=kb, parse_mode="Markdown")


@router.callback_query(F.data == "btn_insights")
async def cb_insights(callback: CallbackQuery, session: AsyncSession):
    """Показать инсайты из кнопки"""
    await callback.answer()
    
    insights = await auto_detect_recurring_micro_expenses(session, days=30)
    
    if not insights:
        await callback.message.answer(
            "🔍 За последние 30 дней не найдено повторяющихся мелких расходов.",
            parse_mode="Markdown"
        )
        return
    
    lines = ["📊 **Микро-расходы:**\n"]
    for insight in insights[:5]:
        lines.append(f"• {insight['name']}: ~{insight['monthly_estimate']:,.0f} ₽/мес")
    
    await callback.message.answer("\n".join(lines), parse_mode="Markdown")
