import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, Tuple
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

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
        if db_draft.expires_at.tzinfo is None:
            # handle naïve comparison
            if db_draft.expires_at < datetime.now(timezone.utc).replace(tzinfo=None):
                await session.execute(delete(OperationDraft).where(OperationDraft.id == draft_id))
                await session.commit()
                return None
        elif db_draft.expires_at < datetime.now(timezone.utc):
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
            if "накопител" in note_lower or "копилк" in note_lower:
                if "с накопител" in note_lower or "из накопител" in note_lower or "с копилк" in note_lower:
                    transfer_info = " с Накопительного счёта на Основной"
                else:
                    transfer_info = " на Накопительный счёт"
            elif "вклад" in note_lower:
                if "с вклада" in note_lower or "из вклада" in note_lower:
                    transfer_info = " с Вклада на Основной счёт"
                else:
                    transfer_info = " на Вклад"

        # Dynamically adjust account balances
        await adjust_account_balances(session, tx)

        budget_warning = None
        if draft.type == "expense" and draft.category:
            budget_warning = await check_budget_warning(session, draft.category, draft.amount)

        await session.execute(delete(OperationDraft).where(OperationDraft.id == draft.id))
        await session.commit()

        return tx, goal_name, transfer_info, budget_warning


async def adjust_account_balances(session: AsyncSession, tx: Transaction):
    from app.models.db import Account
    from sqlalchemy import select

    source_acc = None
    dest_acc = None

    if tx.type == "transfer":
        if tx.account_id:
            source_acc = await session.get(Account, tx.account_id)
        if tx.target_account_id:
            dest_acc = await session.get(Account, tx.target_account_id)

        # Fallback parsing note for transfer targets (for legacy bot inputs)
        note_lower = (tx.note or "").lower() + " " + (tx.category or "").lower()
        if not source_acc and not dest_acc:
            if "накопител" in note_lower or "копилк" in note_lower:
                sav_acc = (await session.execute(select(Account).where(Account.type == "savings", Account.is_active == True))).scalars().first()
                card_acc = (await session.execute(select(Account).where(Account.type == "card", Account.is_active == True))).scalars().first()
                if "с накопител" in note_lower or "из накопител" in note_lower or "с копилк" in note_lower:
                    source_acc = sav_acc
                    dest_acc = card_acc
                else:
                    source_acc = card_acc
                    dest_acc = sav_acc
            elif "вклад" in note_lower:
                dep_acc = (await session.execute(select(Account).where(Account.type == "deposit", Account.is_active == True))).scalars().first()
                card_acc = (await session.execute(select(Account).where(Account.type == "card", Account.is_active == True))).scalars().first()
                if "с вклада" in note_lower or "из вклада" in note_lower:
                    source_acc = dep_acc
                    dest_acc = card_acc
                else:
                    source_acc = card_acc
                    dest_acc = dep_acc

        # Default fallbacks
        if not source_acc:
            source_acc = (await session.execute(select(Account).where(Account.type == "card", Account.is_active == True))).scalars().first()
        if not dest_acc:
            dest_acc = (await session.execute(select(Account).where(Account.type == "savings", Account.is_active == True))).scalars().first()
    else:
        if tx.account_id:
            source_acc = await session.get(Account, tx.account_id)
        else:
            source_acc = (await session.execute(select(Account).where(Account.type == "card", Account.is_active == True))).scalars().first()

    if source_acc:
        tx.account_id = source_acc.id
        if tx.type == "expense":
            source_acc.balance -= tx.amount
        elif tx.type == "income":
            source_acc.balance += tx.amount
        elif tx.type == "transfer":
            source_acc.balance -= tx.amount
        session.add(source_acc)

    if tx.type == "transfer" and dest_acc:
        tx.target_account_id = dest_acc.id
        dest_acc.balance += tx.amount
        session.add(dest_acc)
