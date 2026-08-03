from datetime import date
from decimal import Decimal
from typing import Dict, Any, List, Optional, Literal

from fastapi import APIRouter, Request, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from sqlalchemy import select, func, desc, delete

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

# --- Request Schemas with strict validation ---

MAX_UPLOAD_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB max for QR images


class ChatRequestSchema(BaseModel):
    question: str = Field(min_length=1, max_length=500)


class OperationCreateSchema(BaseModel):
    type: Literal["expense", "income", "transfer"]
    amount: Decimal = Field(gt=0, le=10_000_000)
    category: Optional[str] = Field(default="Прочее", max_length=100)
    note: Optional[str] = Field(default="", max_length=500)
    target_account: Optional[Literal["savings", "deposit", "main_from_savings"]] = None


# --- Routes ---

@router.get("/healthz")
async def healthcheck():
    return {"status": "ok"}


@router.get("/app", response_class=HTMLResponse)
async def serve_mini_app(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


@router.get("/api/summary", response_model=MonthlySummarySchema)
async def get_summary(scope: str = Query("family"), user: dict = Depends(get_current_web_user)):
    user_id = user.get("id")
    today = date.today()
    first_day = today.replace(day=1)

    async with AsyncSessionLocal() as session:
        # Get Accounts breakdown & total capital (shared family data)
        accounts, main_bal, total_capital, total_passive_income = await get_accounts_info(session)
        runway_months = await calculate_financial_runway(session, total_capital)
        category_budgets = await get_category_budgets_summary(session)

        # Current month transactions (filtered by scope)
        stmt_month = select(Transaction).where(Transaction.date >= first_day)
        if scope == "personal" and user_id:
            stmt_month = stmt_month.where(Transaction.author_telegram_id == user_id)
        stmt_month = stmt_month.order_by(desc(Transaction.date), desc(Transaction.id))

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

        # Active goals (shared family goals)
        stmt_goals = select(Goal).where(Goal.status == "active").order_by(Goal.id.asc())
        goals_db = list((await session.execute(stmt_goals)).scalars().all())
        goals_schema = []
        for g in goals_db:
            pct = float((g.current_amount / g.target_amount * 100) if g.target_amount > 0 else 100.0)
            g_item = GoalSchema.model_validate(g)
            g_item.progress_percentage = min(pct, 100.0)
            goals_schema.append(g_item)

        # Recent 20 transactions
        stmt_recent = select(Transaction)
        if scope == "personal" and user_id:
            stmt_recent = stmt_recent.where(Transaction.author_telegram_id == user_id)
        stmt_recent = stmt_recent.order_by(desc(Transaction.date), desc(Transaction.id)).limit(20)

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
            stmt_inc = select(func.coalesce(func.sum(Transaction.amount), 0)).where(Transaction.type == "income")
            total_inc = Decimal(str((await session.execute(stmt_inc)).scalar()))
            stmt_exp = select(func.coalesce(func.sum(Transaction.amount), 0)).where(Transaction.type == "expense")
            total_exp = Decimal(str((await session.execute(stmt_exp)).scalar()))
            adjusted_start = data.main_balance - total_inc + total_exp
            await set_setting_val(session, "starting_balance", str(adjusted_start))
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


@router.post("/api/chat")
async def chat_ai(data: ChatRequestSchema, user: dict = Depends(get_current_web_user)):
    from app.services.advice import ask_financial_ai
    user_id = user.get("id")
    async with AsyncSessionLocal() as session:
        answer = await ask_financial_ai(session, data.question, user_id=user_id)
    return {"answer": answer}


@router.post("/api/operations")
async def create_operation(data: OperationCreateSchema, user: dict = Depends(get_current_web_user)):
    user_id = user.get("id", 1)
    async with AsyncSessionLocal() as session:
        tx = Transaction(
            author_telegram_id=user_id,
            type=data.type,
            amount=data.amount,
            currency="RUB",
            category=data.category or "Прочее",
            note=data.note or "",
            date=date.today(),
            source="web",
            confidence=1.0
        )
        session.add(tx)
        await session.flush()

        if data.type == "transfer":
            from app.services.accounts import get_setting_val
            raw_start = await get_setting_val(session, "starting_balance", "0.00")
            start_bal = Decimal(raw_start)

            if data.target_account == "savings":
                sav_bal = Decimal(await get_setting_val(session, "savings_balance", "0.00")) + data.amount
                start_bal -= data.amount
                await set_setting_val(session, "savings_balance", str(sav_bal))
                await set_setting_val(session, "starting_balance", str(start_bal))
            elif data.target_account == "deposit":
                dep_bal = Decimal(await get_setting_val(session, "deposit_balance", "0.00")) + data.amount
                start_bal -= data.amount
                await set_setting_val(session, "deposit_balance", str(dep_bal))
                await set_setting_val(session, "starting_balance", str(start_bal))
            elif data.target_account == "main_from_savings":
                sav_bal = Decimal(await get_setting_val(session, "savings_balance", "0.00"))
                sav_bal = max(Decimal("0.00"), sav_bal - data.amount)
                start_bal += data.amount
                await set_setting_val(session, "savings_balance", str(sav_bal))
                await set_setting_val(session, "starting_balance", str(start_bal))

        await session.commit()
    return {"status": "ok"}


@router.delete("/api/operations/{operation_id}")
async def delete_operation(operation_id: int, user: dict = Depends(get_current_web_user)):
    """Delete an operation from the family budget."""
    async with AsyncSessionLocal() as session:
        stmt = select(Transaction).where(Transaction.id == operation_id)
        result = await session.execute(stmt)
        tx = result.scalar_one_or_none()

        if not tx:
            raise HTTPException(status_code=404, detail="Operation not found")

        await session.execute(delete(Transaction).where(Transaction.id == operation_id))
        await session.commit()
    return {"status": "ok"}


@router.post("/api/scan_qr")
async def scan_qr_receipt(file: UploadFile = File(...), user: dict = Depends(get_current_web_user)):
    # Validate file size
    contents = await file.read()
    if len(contents) > MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(status_code=413, detail="File too large. Maximum 10 MB.")

    from app.services.qr_decoder import decode_qr_from_bytes, parse_fns_qr_string
    qr_text = decode_qr_from_bytes(contents)

    if not qr_text:
        return {"success": False, "message": "Не удалось распознать QR-код на снимке"}

    amount, receipt_date, note = parse_fns_qr_string(qr_text)
    if not amount:
        return {"success": False, "message": "QR-код найден, но не содержит данных о сумме чека ФНС"}

    return {
        "success": True,
        "amount": float(amount),
        "date": receipt_date.isoformat() if receipt_date else date.today().isoformat(),
        "note": note or "Покупка по чеку"
    }


@router.get("/api/transactions", response_model=List[TransactionSchema])
async def get_transactions(scope: str = Query("family"), user: dict = Depends(get_current_web_user)):
    user_id = user.get("id")
    async with AsyncSessionLocal() as session:
        stmt = select(Transaction)
        if scope == "personal" and user_id:
            stmt = stmt.where(Transaction.author_telegram_id == user_id)
        stmt = stmt.order_by(desc(Transaction.date), desc(Transaction.id)).limit(50)
        txs = list((await session.execute(stmt)).scalars().all())
        return [TransactionSchema.model_validate(tx) for tx in txs]


@router.get("/api/profile")
async def get_user_profile(user: dict = Depends(get_current_web_user)):
    from app.services.accounts import get_user_streak
    user_id = user.get("id", 1)
    first_name = user.get("first_name", "Пользователь")
    last_name = user.get("last_name", "")
    username = user.get("username", "")
    photo_url = user.get("photo_url", "")
    today = date.today()
    first_day = today.replace(day=1)

    async with AsyncSessionLocal() as session:
        streak_count = await get_user_streak(session)

        # Calculate user's personal monthly stats
        stmt_user = select(Transaction).where(
            Transaction.author_telegram_id == user_id,
            Transaction.date >= first_day
        )
        user_txs = list((await session.execute(stmt_user)).scalars().all())

        user_inc = sum((tx.amount for tx in user_txs if tx.type == "income"), Decimal("0"))
        user_exp = sum((tx.amount for tx in user_txs if tx.type == "expense"), Decimal("0"))
        user_free = user_inc - user_exp
        user_savings_rate = float((user_free / user_inc * 100) if user_inc > 0 else 0.0)

        # Calculate family total to find user's share %
        stmt_fam = select(Transaction).where(Transaction.date >= first_day)
        fam_txs = list((await session.execute(stmt_fam)).scalars().all())
        fam_exp = sum((tx.amount for tx in fam_txs if tx.type == "expense"), Decimal("0"))
        share_pct = float((user_exp / fam_exp * 100) if fam_exp > 0 else 50.0)

        return {
            "telegram_id": user_id,
            "first_name": first_name,
            "last_name": last_name,
            "username": username,
            "photo_url": photo_url,
            "streak_count": streak_count,
            "personal_income_month": float(user_inc),
            "personal_expense_month": float(user_exp),
            "personal_savings_rate": user_savings_rate,
            "family_share_pct": share_pct
        }


@router.get("/api/user-settings")
async def get_user_settings(user: dict = Depends(get_current_web_user)):
    from app.services.accounts import get_setting_val
    async with AsyncSessionLocal() as session:
        return {
            "payday_schedule": await get_setting_val(session, "payday_schedule", "2_monthly"),
            "payday_day_1": int(await get_setting_val(session, "payday_day_1", "10")),
            "payday_day_2": int(await get_setting_val(session, "payday_day_2", "25")),
            "payday_amount": float(await get_setting_val(session, "payday_amount", "75000")),
            "payday_type": await get_setting_val(session, "payday_type", "fixed"),
            "budget_ratio_essential": int(await get_setting_val(session, "budget_ratio_essential", "50")),
            "budget_ratio_personal": int(await get_setting_val(session, "budget_ratio_personal", "30")),
            "budget_ratio_savings": int(await get_setting_val(session, "budget_ratio_savings", "20")),
        }


@router.post("/api/user-settings")
async def save_user_settings(data: dict, user: dict = Depends(get_current_web_user)):
    from app.services.accounts import set_setting_val
    async with AsyncSessionLocal() as session:
        if "payday_schedule" in data:
            await set_setting_val(session, "payday_schedule", str(data["payday_schedule"]))
        if "payday_day_1" in data:
            await set_setting_val(session, "payday_day_1", str(data["payday_day_1"]))
        if "payday_day_2" in data:
            await set_setting_val(session, "payday_day_2", str(data["payday_day_2"]))
        if "payday_amount" in data:
            await set_setting_val(session, "payday_amount", str(data["payday_amount"]))
        if "payday_type" in data:
            await set_setting_val(session, "payday_type", str(data["payday_type"]))
        if "budget_ratio_essential" in data:
            await set_setting_val(session, "budget_ratio_essential", str(data["budget_ratio_essential"]))
        if "budget_ratio_personal" in data:
            await set_setting_val(session, "budget_ratio_personal", str(data["budget_ratio_personal"]))
        if "budget_ratio_savings" in data:
            await set_setting_val(session, "budget_ratio_savings", str(data["budget_ratio_savings"]))
        await session.commit()
    return {"status": "ok"}


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


# --- Subscriptions API ---

@router.get("/api/subscriptions")
async def get_subscriptions(user: dict = Depends(get_current_web_user)):
    from app.services.subscriptions import get_all_subscriptions, calculate_subscriptions_summary
    async with AsyncSessionLocal() as session:
        subs = await get_all_subscriptions(session)
        summary = calculate_subscriptions_summary(subs)
        return {
            "subscriptions": [
                {
                    "id": s.id,
                    "name": s.name,
                    "amount": float(s.amount),
                    "currency": s.currency,
                    "period": s.period,
                    "billing_day": s.billing_day,
                    "category": s.category,
                    "is_active": s.is_active,
                    "next_billing": s.next_billing.isoformat() if s.next_billing else None
                }
                for s in subs
            ],
            "total_monthly": float(summary["total_monthly"]),
            "total_yearly": float(summary["total_yearly"]),
            "active_count": summary["count"]
        }


@router.post("/api/subscriptions")
async def create_new_subscription(data: Dict[str, Any], user: dict = Depends(get_current_web_user)):
    from app.models.schemas import SubscriptionCreateSchema
    from app.services.subscriptions import create_subscription
    sub_schema = SubscriptionCreateSchema(
        name=data.get("name", "Подписка"),
        amount=Decimal(str(data.get("amount", 0))),
        period=data.get("period", "monthly"),
        billing_day=int(data.get("billing_day", 1)),
        category=data.get("category", "Подписки")
    )
    async with AsyncSessionLocal() as session:
        sub = await create_subscription(session, sub_schema)
        return {"status": "ok", "id": sub.id}


@router.delete("/api/subscriptions/{sub_id}")
async def remove_subscription(sub_id: int, user: dict = Depends(get_current_web_user)):
    from app.services.subscriptions import delete_subscription
    async with AsyncSessionLocal() as session:
        ok = await delete_subscription(session, sub_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Subscription not found")
        return {"status": "ok"}


@router.get("/api/subscriptions/autodetect")
async def autodetect_subs(user: dict = Depends(get_current_web_user)):
    from app.services.subscriptions import auto_detect_subscriptions
    async with AsyncSessionLocal() as session:
        detected = await auto_detect_subscriptions(session)
        return {"detected": detected}


# --- Analytics API ---

@router.get("/api/analytics/trends")
async def get_trends(period: int = 90, scope: str = Query("family"), user: dict = Depends(get_current_web_user)):
    from app.services.intelligence import get_expense_trends
    author_id = user.get("id") if scope == "personal" else None
    async with AsyncSessionLocal() as session:
        return await get_expense_trends(session, period_days=period, author_id=author_id)


@router.get("/api/analytics/compare")
async def get_compare(scope: str = Query("family"), user: dict = Depends(get_current_web_user)):
    from app.services.intelligence import calculate_personal_inflation
    author_id = user.get("id") if scope == "personal" else None
    async with AsyncSessionLocal() as session:
        return await calculate_personal_inflation(session, author_id=author_id)


@router.get("/api/analytics/authors")
async def get_authors(period: int = 30, user: dict = Depends(get_current_web_user)):
    from app.services.intelligence import get_author_spending_breakdown
    async with AsyncSessionLocal() as session:
        return await get_author_spending_breakdown(session, days=period)


# --- Goals Management API ---

class GoalCreateSchema(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    target_amount: Decimal = Field(gt=0)
    current_amount: Decimal = Field(ge=0, default=Decimal("0.00"))
    months: Optional[int] = Field(default=None, ge=1, le=120)
    apy: Optional[float] = Field(default=0.0, ge=0.0)


@router.post("/api/goals")
async def create_goal_endpoint(data: GoalCreateSchema, user: dict = Depends(get_current_web_user)):
    async with AsyncSessionLocal() as session:
        deadline_date = date.today() + timedelta(days=data.months * 30) if data.months else None
        g = Goal(
            title=data.title.strip(),
            target_amount=data.target_amount,
            current_amount=data.current_amount,
            deadline=deadline_date,
            apy=data.apy,
            status="active"
        )
        session.add(g)
        await session.commit()
        await session.refresh(g)
        return {"status": "ok", "id": g.id}


@router.post("/api/goals/{goal_id}/contribute")
async def contribute_to_goal(goal_id: int, data: Dict[str, Any], user: dict = Depends(get_current_web_user)):
    user_id = user.get("id", 1)
    amount = Decimal(str(data.get("amount", 0)))
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Сумма должна быть больше 0")

    async with AsyncSessionLocal() as session:
        g = await session.get(Goal, goal_id)
        if not g:
            raise HTTPException(status_code=404, detail="Цель не найдена")

        g.current_amount += amount
        if g.current_amount >= g.target_amount:
            g.status = "done"

        # Record contribution transaction
        tx = Transaction(
            author_telegram_id=user_id,
            type="goal_contribution",
            amount=amount,
            category="Накопления",
            note=f"Взнос в цель «{g.title}»",
            date=date.today(),
            source="web"
        )
        session.add(tx)
        await session.flush()

        from app.models.db import GoalContribution
        contrib = GoalContribution(
            goal_id=g.id,
            transaction_id=tx.id,
            amount=amount
        )
        session.add(contrib)
        await session.commit()
        return {"status": "ok", "current_amount": float(g.current_amount)}


@router.delete("/api/goals/{goal_id}")
async def delete_goal_endpoint(goal_id: int, user: dict = Depends(get_current_web_user)):
    async with AsyncSessionLocal() as session:
        g = await session.get(Goal, goal_id)
        if not g:
            raise HTTPException(status_code=404, detail="Цель не найдена")
        await session.delete(g)
        await session.commit()
        return {"status": "ok"}


# --- Operation Management API ---

class OperationUpdateSchema(BaseModel):
    amount: Optional[Decimal] = Field(default=None, gt=0)
    category: Optional[str] = None
    note: Optional[str] = None
    date: Optional[date] = None


@router.put("/api/operations/{operation_id}")
async def update_operation(operation_id: int, data: OperationUpdateSchema, user: dict = Depends(get_current_web_user)):
    async with AsyncSessionLocal() as session:
        tx = await session.get(Transaction, operation_id)
        if not tx:
            raise HTTPException(status_code=404, detail="Операция не найдена")

        if data.amount is not None:
            tx.amount = data.amount
        if data.category is not None:
            tx.category = data.category
        if data.note is not None:
            tx.note = data.note
        if data.date is not None:
            tx.date = data.date

        await session.commit()
        return {"status": "ok"}
