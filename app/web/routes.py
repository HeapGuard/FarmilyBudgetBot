from datetime import date
from decimal import Decimal
from typing import Dict, Any, List
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, func, desc

from app.database import AsyncSessionLocal
from app.models.db import Transaction, Goal, Setting
from app.models.schemas import (
    MonthlySummarySchema, TransactionSchema, GoalSchema, CategoryTopSchema, AccountsUpdateSchema, BudgetUpdateSchema
)
from app.services.accounts import get_accounts_info, set_setting_val
from app.services.budgets import get_category_budgets_summary, set_category_budget, calculate_financial_runway
from app.web.auth import get_current_web_user

router = APIRouter()
templates = Jinja2Templates(directory="app/web/templates")


@router.get("/healthz")
async def healthcheck():
    return {"status": "ok"}


@router.get("/app", response_class=HTMLResponse)
async def serve_mini_app(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


@router.get("/api/summary", response_model=MonthlySummarySchema)
async def get_summary(user: dict = Depends(get_current_web_user)):
    today = date.today()
    first_day = today.replace(day=1)

    async with AsyncSessionLocal() as session:
        # Get Accounts breakdown & total capital
        accounts, main_bal, total_capital, total_passive_income = await get_accounts_info(session)
        runway_months = await calculate_financial_runway(session, total_capital)
        category_budgets = await get_category_budgets_summary(session)

        # Current month transactions
        stmt_month = select(Transaction).where(Transaction.date >= first_day).order_by(desc(Transaction.date), desc(Transaction.id))
        month_txs = list((await session.execute(stmt_month)).scalars().all())

        income_month = sum((tx.amount for tx in month_txs if tx.type == "income"), Decimal("0"))
        expense_month = sum((tx.amount for tx in month_txs if tx.type == "expense"), Decimal("0"))
        free_cash_flow = income_month - expense_month
        savings_rate = float((free_cash_flow / income_month * 100) if income_month > 0 else 0.0)

        # Top 3 expense categories
        cat_totals: Dict[str, Decimal] = {}
        for tx in month_txs:
            if tx.type == "expense" and tx.category:
                cat_totals[tx.category] = cat_totals.get(tx.category, Decimal("0")) + tx.amount

        sorted_cats = sorted(cat_totals.items(), key=lambda x: x[1], reverse=True)[:3]
        top_categories = []
        for cat, amt in sorted_cats:
            pct = float((amt / expense_month * 100) if expense_month > 0 else 0.0)
            top_categories.append(CategoryTopSchema(category=cat, amount=amt, percentage=pct))

        # Active goals
        stmt_goals = select(Goal).where(Goal.status == "active").order_by(Goal.id.asc())
        goals_db = list((await session.execute(stmt_goals)).scalars().all())
        goals_schema = []
        for g in goals_db:
            pct = float((g.current_amount / g.target_amount * 100) if g.target_amount > 0 else 100.0)
            g_item = GoalSchema.model_validate(g)
            g_item.progress_percentage = min(pct, 100.0)
            goals_schema.append(g_item)

        # Recent 20 transactions
        stmt_recent = select(Transaction).order_by(desc(Transaction.date), desc(Transaction.id)).limit(20)
        recent_db = list((await session.execute(stmt_recent)).scalars().all())
        recent_schema = [TransactionSchema.model_validate(tx) for tx in recent_db]

    return MonthlySummarySchema(
        balance=main_bal,
        total_capital=total_capital,
        total_passive_income_monthly=total_passive_income,
        financial_runway_months=runway_months,
        income_month=income_month,
        expense_month=expense_month,
        free_cash_flow=free_cash_flow,
        savings_rate=savings_rate,
        accounts=accounts,
        category_budgets=category_budgets,
        top_expense_categories=top_categories,
        active_goals=goals_schema,
        recent_transactions=recent_schema
    )


@router.post("/api/budgets")
async def update_budget(data: BudgetUpdateSchema, user: dict = Depends(get_current_web_user)):
    async with AsyncSessionLocal() as session:
        await set_category_budget(session, data.category, data.limit)
        await session.commit()
    return {"status": "ok"}



@router.post("/api/accounts")
async def update_accounts(data: AccountsUpdateSchema, user: dict = Depends(get_current_web_user)):
    async with AsyncSessionLocal() as session:
        if data.main_balance is not None:
            await set_setting_val(session, "starting_balance", str(data.main_balance))
        if data.savings_balance is not None:
            await set_setting_val(session, "savings_balance", str(data.savings_balance))
        if data.savings_apy is not None:
            await set_setting_val(session, "savings_apy", str(data.savings_apy))
        if data.savings_enabled is not None:
            await set_setting_val(session, "savings_enabled", "true" if data.savings_enabled else "false")
        if data.deposit_balance is not None:
            await set_setting_val(session, "deposit_balance", str(data.deposit_balance))
        if data.deposit_apy is not None:
            await set_setting_val(session, "deposit_apy", str(data.deposit_apy))
        if data.deposit_months is not None:
            await set_setting_val(session, "deposit_months", str(data.deposit_months))
        if data.deposit_enabled is not None:
            await set_setting_val(session, "deposit_enabled", "true" if data.deposit_enabled else "false")
        await session.commit()
    return {"status": "ok"}



@router.get("/api/transactions", response_model=List[TransactionSchema])
async def get_transactions(user: dict = Depends(get_current_web_user)):
    async with AsyncSessionLocal() as session:
        stmt = select(Transaction).order_by(desc(Transaction.date), desc(Transaction.id)).limit(50)
        txs = list((await session.execute(stmt)).scalars().all())
        return [TransactionSchema.model_validate(tx) for tx in txs]


@router.get("/api/goals", response_model=List[GoalSchema])
async def get_goals(user: dict = Depends(get_current_web_user)):
    async with AsyncSessionLocal() as session:
        stmt = select(Goal).order_by(Goal.id.asc())
        goals_db = list((await session.execute(stmt)).scalars().all())
        res = []
        for g in goals_db:
            pct = float((g.current_amount / g.target_amount * 100) if g.target_amount > 0 else 100.0)
            g_item = GoalSchema.model_validate(g)
            g_item.progress_percentage = min(pct, 100.0)
            res.append(g_item)
        return res

