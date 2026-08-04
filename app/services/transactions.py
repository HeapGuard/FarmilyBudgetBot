import json
from datetime import datetime
from decimal import Decimal
from typing import Optional, Tuple
from sqlalchemy import select, delete

from app.database import AsyncSessionLocal
from app.models.db import OperationDraft, Transaction, Goal, GoalContribution
from app.models.schemas import OperationDraftSchema
from app.services.accounts import get_setting_val, set_setting_val
from app.services.budgets import check_budget_warning


async def save_draft_to_db(draft: OperationDraftSchema) -> None:
    """Saves or updates an operation draft in DB."""
    async with AsyncSessionLocal() as session:
        await session.execute(delete(OperationDraft).where(OperationDraft.id == draft.id))
        db_draft = OperationDraft(
            id=draft.id,
            payload_json=draft.model_dump_json(),
            author_telegram_id=draft.author_telegram_id,
            created_at=draft.created_at,
            expires_at=draft.expires_at
        )
        session.add(db_draft)
        await session.commit()


async def get_draft_from_db(draft_id: str) -> Optional[OperationDraftSchema]:
    """Retrieves an operation draft from DB if not expired."""
    async with AsyncSessionLocal() as session:
        stmt = select(OperationDraft).where(OperationDraft.id == draft_id)
        res = await session.execute(stmt)
        db_draft = res.scalar_one_or_none()
        if not db_draft:
            return None
        if db_draft.expires_at < datetime.utcnow():
            await session.execute(delete(OperationDraft).where(OperationDraft.id == draft_id))
            await session.commit()
            return None
        data = json.loads(db_draft.payload_json)
        return OperationDraftSchema(**data)


async def confirm_draft(draft: OperationDraftSchema) -> Tuple[Transaction, str, str, Optional[str]]:
    """
    Confirms an operation draft: creates Transaction, updates Goals/Accounts if applicable,
    and removes the draft.
    Returns (Transaction, goal_name_suffix, transfer_info_suffix, budget_warning).
    """
    async with AsyncSessionLocal() as session:
        tx = Transaction(
            author_telegram_id=draft.author_telegram_id,
            type=draft.type,
            amount=draft.amount,
            currency=draft.currency,
            category=draft.category,
            note=draft.note,
            date=draft.date,
            source=draft.source,
            confidence=draft.confidence
        )
        session.add(tx)
        await session.flush()

        goal_name = ""
        transfer_info = ""

        if draft.type == "goal_contribution":
            stmt_g = select(Goal).where(Goal.status == "active")
            res_g = await session.execute(stmt_g)
            active_goals = list(res_g.scalars().all())

            target_goal = None
            if len(active_goals) == 1:
                target_goal = active_goals[0]
            elif len(active_goals) > 1 and draft.note:
                for g in active_goals:
                    if g.title.lower() in draft.note.lower():
                        target_goal = g
                        break
                if not target_goal:
                    target_goal = active_goals[0]

            if target_goal:
                target_goal.current_amount += draft.amount
                if target_goal.current_amount >= target_goal.target_amount:
                    target_goal.status = "done"
                gc = GoalContribution(
                    goal_id=target_goal.id,
                    transaction_id=tx.id,
                    amount=draft.amount
                )
                session.add(gc)
                goal_name = f" в цель «{target_goal.title}»"

        elif draft.type == "transfer":
            note_lower = (draft.note or "").lower() + " " + (draft.category or "").lower()
            raw_start = await get_setting_val(session, "starting_balance", "0.00")
            start_bal = Decimal(raw_start)

            if "накопител" in note_lower or "копилк" in note_lower:
                sav_bal = Decimal(await get_setting_val(session, "savings_balance", "0.00"))
                if "с накопител" in note_lower or "из накопител" in note_lower or "с копилк" in note_lower:
                    sav_bal = max(Decimal("0.00"), sav_bal - draft.amount)
                    start_bal += draft.amount
                    transfer_info = " с Накопительного счёта на Основной"
                else:
                    sav_bal += draft.amount
                    start_bal -= draft.amount
                    transfer_info = " на Накопительный счёт"
                await set_setting_val(session, "savings_balance", str(sav_bal))
                await set_setting_val(session, "starting_balance", str(start_bal))
            elif "вклад" in note_lower:
                dep_bal = Decimal(await get_setting_val(session, "deposit_balance", "0.00"))
                if "с вклада" in note_lower or "из вклада" in note_lower:
                    dep_bal = max(Decimal("0.00"), dep_bal - draft.amount)
                    start_bal += draft.amount
                    transfer_info = " с Вклада на Основной счёт"
                else:
                    dep_bal += draft.amount
                    start_bal -= draft.amount
                    transfer_info = " на Вклад"
                await set_setting_val(session, "deposit_balance", str(dep_bal))
                await set_setting_val(session, "starting_balance", str(start_bal))

        budget_warning = None
        if draft.type == "expense" and draft.category:
            budget_warning = await check_budget_warning(session, draft.category, draft.amount)

        await session.execute(delete(OperationDraft).where(OperationDraft.id == draft.id))
        await session.commit()

        return tx, goal_name, transfer_info, budget_warning
