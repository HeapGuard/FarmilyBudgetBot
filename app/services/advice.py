import json
import httpx
from datetime import date, timedelta
from decimal import Decimal
from typing import List, Dict, Any, Optional
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.db import Transaction, Goal
from app.services.goals import required_monthly


class AdviceItem:
    def __init__(self, title: str, action: str, effect: str, importance: str):
        self.title = title
        self.action = action
        self.effect = effect
        self.importance = importance

    def to_formatted_text(self) -> str:
        return (
            f"💡 <b>{self.title}</b>\n"
            f"• <b>Что сделать:</b> {self.action}\n"
            f"• <b>Ожидаемый эффект:</b> {self.effect}\n"
            f"• <b>Почему это важно:</b> {self.importance}"
        )


async def generate_deterministic_advice(session: AsyncSession) -> List[AdviceItem]:
    today = date.today()
    thirty_days_ago = today - timedelta(days=30)
    sixty_days_ago = today - timedelta(days=60)

    stmt_last = select(Transaction).where(Transaction.date >= thirty_days_ago)
    res_last = await session.execute(stmt_last)
    last_txs = list(res_last.scalars().all())

    stmt_prev = select(Transaction).where(
        Transaction.date >= sixty_days_ago,
        Transaction.date < thirty_days_ago
    )
    res_prev = await session.execute(stmt_prev)
    prev_txs = list(res_prev.scalars().all())

    if len(last_txs) < 3:
        return [
            AdviceItem(
                title="Накопление статистики",
                action="Продолжайте вносить доходы и расходы в течение пары недель.",
                effect="Бот сможет точнее рассчитывать нормальный темп трат.",
                importance="Для хороших финансовых рекомендаций требуется история операций."
            )
        ]

    income_last = sum((tx.amount for tx in last_txs if tx.type == "income"), Decimal("0"))
    expense_last = sum((tx.amount for tx in last_txs if tx.type == "expense"), Decimal("0"))

    income_prev = sum((tx.amount for tx in prev_txs if tx.type == "income"), Decimal("0"))
    expense_prev = sum((tx.amount for tx in prev_txs if tx.type == "expense"), Decimal("0"))

    free_cash_flow = income_last - expense_last
    savings_rate = (free_cash_flow / income_last) if income_last > 0 else Decimal("0")

    cat_expenses_last: Dict[str, Decimal] = {}
    for tx in last_txs:
        if tx.type == "expense" and tx.category:
            cat_expenses_last[tx.category] = cat_expenses_last.get(tx.category, Decimal("0")) + tx.amount

    cat_expenses_prev: Dict[str, Decimal] = {}
    for tx in prev_txs:
        if tx.type == "expense" and tx.category:
            cat_expenses_prev[tx.category] = cat_expenses_prev.get(tx.category, Decimal("0")) + tx.amount

    stmt_goals = select(Goal).where(Goal.status == "active")
    res_goals = await session.execute(stmt_goals)
    active_goals = list(res_goals.scalars().all())

    advice_list: List[AdviceItem] = []

    if savings_rate < Decimal("0.10") and income_last > 0:
        five_percent = income_last * Decimal("0.05")
        advice_list.append(AdviceItem(
            title="Формирование привычки накопления",
            action=f"Настройте автоперевод {five_percent:,.0f} ₽ (5% от дохода) на отдельный накопительный счёт сразу в день поступления денег.".replace(",", " "),
            effect=f"За год удалось бы сохранить более {five_percent * 12:,.0f} ₽ без ощутимого ограничения текущих трат.".replace(",", " "),
            importance="Первоочередное откладывание небольшого процента гарантирует постоянный рост накоплений."
        ))

    subscriptions_total = cat_expenses_last.get("Подписки", Decimal("0"))
    if subscriptions_total > Decimal("500"):
        advice_list.append(AdviceItem(
            title="Оптимизация цифровых подписок",
            action="Проверьте список всех платных сервисов и объедините семейные подписки.",
            effect=f"Освобождение до {subscriptions_total * Decimal('0.3'):,.0f} ₽ ежемесячно.".replace(",", " "),
            importance="Неиспользуемые подписки незаметно снижают свободный бюджет."
        ))

    for cat, amt_last in cat_expenses_last.items():
        if cat in ["Жильё", "ЖКХ", "Переводы"]:
            continue
        amt_prev = cat_expenses_prev.get(cat, Decimal("0"))
        if amt_prev > Decimal("1000") and amt_last > amt_prev * Decimal("1.20"):
            growth_pct = ((amt_last - amt_prev) / amt_prev) * 100
            save_est = amt_last * Decimal("0.15")
            advice_list.append(AdviceItem(
                title=f"Контроль категории «{cat}»",
                action=f"Попробуйте сократить расходы на {cat} на 10-15% в следующем месяце.",
                effect=f"Сбережение около {save_est:,.0f} ₽ в месяц.".replace(",", " "),
                importance=f"За последний месяц категории выросли на {growth_pct:.0f}% по сравнению с прошлым периодом."
            ))
            if len(advice_list) >= 4:
                break

    total_req_monthly = Decimal("0")
    for g in active_goals:
        if g.deadline:
            months = (g.deadline - today).days // 30
            if months > 0:
                req = required_monthly(g.current_amount, g.target_amount, months, g.apy or 0.0)
                if req:
                    total_req_monthly += req

    if total_req_monthly > free_cash_flow and total_req_monthly > 0:
        advice_list.append(AdviceItem(
            title="Балансировка целей накопления",
            action="Рассмотрите продление срока одной из целей или небольшое уменьшение ежемесячного взноса.",
            effect="Снижение финансовой нагрузки и предотвращение дефицита средств.",
            importance="Сумма планируемых взносов на цели превышает текущий свободный остаток за месяц."
        ))

    has_emergency_fund = any("подушка" in g.title.lower() or "резерв" in g.title.lower() for g in active_goals)
    if not has_emergency_fund and expense_last > 0:
        target_emergency = expense_last * 3
        advice_list.append(AdviceItem(
            title="Создание подушки безопасности",
            action="Создайте цель «Подушка безопасности» с ориентиром на 3 месяца расходов.",
            effect=f"Формирование финансового резерва порядка {target_emergency:,.0f} ₽.".replace(",", " "),
            importance="Резервный фонд защищает семью от непредвиденных жизненных ситуаций."
        ))

    if len(advice_list) < 3:
        advice_list.append(AdviceItem(
            title="Регулярный финансовый аудит",
            action="Вместе просматривайте отчёт за месяц каждое 1-е число.",
            effect="Единое понимание семейных приоритетов и планов.",
            importance="Совместное планирование укрепляет финансовую стабильность пары."
        ))

    return advice_list[:5]


async def get_advice(session: AsyncSession) -> str:
    items = await generate_deterministic_advice(session)
    formatted_items = "\n\n".join([item.to_formatted_text() for item in items])
    header = "📊 <b>Персональные финансовые советы:</b>\n\n"

    if settings.LLM_PROVIDER in ["ollama", "openrouter"]:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                system_prompt = "Ты — дружелюбный финансовый помощник. Переформулируй предоставленный текст красиво на русском языке с использованием HTML-тегов <b>, <i>, <code>, сохраняя структуру 💡, заголовки, списки, все числа и факты без изменений."
                if settings.LLM_PROVIDER == "ollama":
                    url = f"{settings.OLLAMA_BASE_URL.rstrip('/')}/v1/chat/completions"
                    headers = {"Content-Type": "application/json"}
                    payload = {
                        "model": settings.OLLAMA_MODEL,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": formatted_items}
                        ]
                    }
                else:
                    if settings.OPENROUTER_API_KEY:
                        url = "https://openrouter.ai/api/v1/chat/completions"
                        headers = {
                            "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
                            "Content-Type": "application/json"
                        }
                        payload = {
                            "model": settings.OPENROUTER_MODEL,
                            "messages": [
                                {"role": "system", "content": system_prompt},
                                {"role": "user", "content": formatted_items}
                            ]
                        }
                resp = await client.post(url, headers=headers, json=payload)
                if resp.status_code == 200:
                    text = resp.json()["choices"][0]["message"]["content"]
                    if text and len(text) > 50:
                        return header + text.strip()
        except Exception:
            pass

    return header + formatted_items
