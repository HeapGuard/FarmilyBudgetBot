import csv
import io
from typing import Tuple
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.db import Transaction, Goal


async def generate_csv_exports(session: AsyncSession) -> Tuple[bytes, bytes]:
    """
    Generates CSV export bytes for transactions and goals.
    Returns (transactions_csv_bytes, goals_csv_bytes).
    """
    # 1. Export Transactions
    tx_stmt = select(Transaction).order_by(Transaction.date.desc(), Transaction.id.desc())
    tx_res = await session.execute(tx_stmt)
    transactions = tx_res.scalars().all()

    tx_output = io.StringIO()
    tx_writer = csv.writer(tx_output)
    tx_writer.writerow(["id", "author_telegram_id", "type", "amount", "currency", "category", "note", "date", "source", "created_at"])
    for tx in transactions:
        tx_writer.writerow([
            tx.id,
            tx.author_telegram_id,
            tx.type,
            str(tx.amount),
            tx.currency,
            tx.category or "",
            tx.note or "",
            tx.date.isoformat(),
            tx.source,
            tx.created_at.isoformat()
        ])

    # 2. Export Goals
    goal_stmt = select(Goal).order_by(Goal.id.asc())
    goal_res = await session.execute(goal_stmt)
    goals = goal_res.scalars().all()

    goal_output = io.StringIO()
    goal_writer = csv.writer(goal_output)
    goal_writer.writerow(["id", "title", "target_amount", "current_amount", "currency", "deadline", "apy", "monthly_contribution_plan", "status", "created_at"])
    for g in goals:
        goal_writer.writerow([
            g.id,
            g.title,
            str(g.target_amount),
            str(g.current_amount),
            g.currency,
            g.deadline.isoformat() if g.deadline else "",
            g.apy if g.apy is not None else "",
            str(g.monthly_contribution_plan) if g.monthly_contribution_plan else "",
            g.status,
            g.created_at.isoformat()
        ])

    tx_bytes = tx_output.getvalue().encode("utf-8-sig")
    goal_bytes = goal_output.getvalue().encode("utf-8-sig")

    return tx_bytes, goal_bytes
